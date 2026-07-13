"""Aplica los efectos declarados por el narrador (contrato JSON) a la DB.

Cada efecto se valida antes de aplicarse. Fallos individuales no rompen
el resto: se registran y se sigue. El LLM no tiene autoridad sobre PG,
slots ni recursos de PJs — esos campos no existen en el contrato.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.content import MONSTRUOS

from .models import (NPC, Campaign, Character, Message, PendingConsequence,
                     Quest)

XP_NARRATIVO_TOPE_POR_NIVEL = 50   # tope: 50 × nivel_promedio por evento
ACTITUDES = {"amistoso", "neutral", "desconfiado", "hostil"}


def _en_cobre(m: dict | None) -> int:
    """Valor total de una bolsa {mo,mp,mc} en cobre (1 mo = 10 mp = 100 mc)."""
    m = m or {}
    return int(m.get("mo", 0)) * 100 + int(m.get("mp", 0)) * 10 + int(m.get("mc", 0))


def _desde_cobre(cp: int) -> dict:
    """Reparte un total de cobre en oro/plata/cobre (cambio óptimo)."""
    cp = max(0, int(cp))
    return {"mo": cp // 100, "mp": (cp % 100) // 10, "mc": cp % 10}


def _bolsa_a_texto(m: dict) -> str:
    return f"{m.get('mo', 0)} mo, {m.get('mp', 0)} mp, {m.get('mc', 0)} mc"


async def aplicar_efectos(db: AsyncSession, camp: Campaign,
                          efectos: dict,
                          actor: Character | None = None) -> dict:
    """Devuelve un log de qué se aplicó y qué se rechazó."""
    log = {"aplicados": [], "rechazados": [], "inicia_combate": None}
    if not efectos:
        return log

    # Cambio de lugar: los NPCs de la escena anterior se quedan atrás. Se limpia
    # ANTES de introducir los NPCs nuevos (nuevos_npcs), así los del lugar nuevo
    # sí quedan en escena. Evita que la escena se llene de gente que ya no está.
    _ub = efectos.get("nueva_ubicacion")
    if isinstance(_ub, str) and _ub.strip() \
            and _ub.strip()[:200] != camp.ubicacion_actual:
        res = await db.execute(select(NPC).where(
            NPC.campaign_id == camp.id, NPC.en_escena == True))  # noqa: E712
        salieron = res.scalars().all()
        for n in salieron:
            n.en_escena = False
        if salieron:
            log["aplicados"].append(("escena_reiniciada_por_ubicacion",
                                     len(salieron)))

    for npc_data in efectos.get("nuevos_npcs") or []:
        if not isinstance(npc_data, dict) or not npc_data.get("nombre"):
            log["rechazados"].append(("nuevos_npcs", npc_data))
            continue
        n = NPC(campaign_id=camp.id,
                nombre=str(npc_data["nombre"])[:80],
                rol=str(npc_data.get("rol", ""))[:120],
                personalidad=str(npc_data.get("personalidad", "")),
                motivacion=str(npc_data.get("motivacion", "")),
                actitud=npc_data.get("actitud", "neutral")
                if npc_data.get("actitud") in ACTITUDES else "neutral",
                secretos=str(npc_data.get("secretos", "")),
                en_escena=True)
        db.add(n)
        log["aplicados"].append(("nuevo_npc", n.nombre))

    for upd in efectos.get("actualizar_npc") or []:
        if not isinstance(upd, dict):
            continue
        n = await db.get(NPC, upd.get("npc_id", -1))
        if n is None or n.campaign_id != camp.id:
            log["rechazados"].append(("actualizar_npc", upd))
            continue
        if upd.get("actitud") in ACTITUDES:
            n.actitud = upd["actitud"]
        if upd.get("nota_sabe_del_grupo"):
            n.sabe_del_grupo = list(n.sabe_del_grupo) + \
                [str(upd["nota_sabe_del_grupo"])[:300]]
        log["aplicados"].append(("actualizar_npc", n.nombre))

    q = efectos.get("nueva_quest")
    if isinstance(q, dict) and q.get("titulo"):
        origen = q.get("npc_origen_id")
        if origen is not None:
            npc = await db.get(NPC, origen)
            if npc is None or npc.campaign_id != camp.id:
                origen = None
        db.add(Quest(campaign_id=camp.id, titulo=str(q["titulo"])[:160],
                     descripcion=str(q.get("descripcion", "")),
                     principal=bool(q.get("principal", False)),
                     npc_origen_id=origen))
        log["aplicados"].append(("nueva_quest", q["titulo"]))

    cq = efectos.get("completar_quest")
    if isinstance(cq, dict):
        quest = await db.get(Quest, cq.get("quest_id", -1))
        if quest and quest.campaign_id == camp.id and \
                cq.get("resultado") in ("completada", "fallida"):
            quest.estado = cq["resultado"]
            log["aplicados"].append(("quest_" + cq["resultado"], quest.titulo))
        else:
            log["rechazados"].append(("completar_quest", cq))

    pc = efectos.get("consecuencia_pendiente")
    if isinstance(pc, dict) and pc.get("evento") and pc.get("efecto"):
        db.add(PendingConsequence(
            campaign_id=camp.id, evento=str(pc["evento"]),
            efecto=str(pc["efecto"]),
            activacion=str(pc.get("activacion", "a criterio del DM"))))
        log["aplicados"].append(("consecuencia_pendiente", pc["evento"][:60]))

    rc = efectos.get("resolver_consecuencia")
    if isinstance(rc, dict):
        con = await db.get(PendingConsequence, rc.get("consecuencia_id", -1))
        if con and con.campaign_id == camp.id:
            con.resuelta = True
            log["aplicados"].append(("consecuencia_resuelta", con.evento[:60]))

    for npc_id in efectos.get("npcs_salen_de_escena") or []:
        n = await db.get(NPC, npc_id if isinstance(npc_id, int) else -1)
        if n and n.campaign_id == camp.id:
            n.en_escena = False
            log["aplicados"].append(("npc_sale", n.nombre))

    xp = efectos.get("otorgar_xp")
    if isinstance(xp, int) and xp > 0:
        res = await db.execute(select(Character).where(
            Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
        chars = res.scalars().all()
        if chars:
            nivel_prom = sum(c.nivel for c in chars) / len(chars)
            tope = int(XP_NARRATIVO_TOPE_POR_NIVEL * nivel_prom)
            otorgado = min(xp, tope)
            for c in chars:
                c.xp += otorgado
            log["aplicados"].append(("xp_narrativo", otorgado))
            if xp > tope:
                log["rechazados"].append(("xp_excedente", xp - tope))

    t = efectos.get("avanzar_tiempo_min")
    if isinstance(t, int) and 0 < t <= 60 * 24 * 7:   # tope: 1 semana por evento
        camp.tiempo_juego_min += t
        log["aplicados"].append(("tiempo", t))

    ub = efectos.get("nueva_ubicacion")
    if isinstance(ub, str) and ub.strip():
        camp.ubicacion_actual = ub.strip()[:200]
        log["aplicados"].append(("ubicacion", camp.ubicacion_actual))

    loot = efectos.get("loot")
    if isinstance(loot, list) and loot:
        receptor = actor
        if receptor is None:
            res = await db.execute(select(Character).where(
                Character.campaign_id == camp.id,
                Character.vivo == True).limit(1))  # noqa: E712
            receptor = res.scalar_one_or_none()
        if receptor:
            inv = list(receptor.inventario)
            for item in loot[:5]:
                if not isinstance(item, dict) or not item.get("nombre"):
                    continue
                nombre = str(item["nombre"])[:60]
                cant = min(int(item.get("cantidad", 1) or 1), 10)
                existente = next((x for x in inv if x.get("nombre") == nombre), None)
                if existente:
                    existente["cantidad"] = existente.get("cantidad", 1) + cant
                else:
                    inv.append({"nombre": nombre, "cantidad": cant})
                log["aplicados"].append(("loot", f"{nombre} x{cant}"))
            receptor.inventario = inv

    quitar = efectos.get("quitar_item")
    if isinstance(quitar, list) and quitar and actor is not None:
        inv = list(actor.inventario)
        for item in quitar[:5]:
            if not isinstance(item, dict) or not item.get("nombre"):
                continue
            nombre = str(item["nombre"])[:60].lower()
            cant = min(int(item.get("cantidad", 1) or 1), 10)
            # match por nombre exacto o inclusión (el DM no siempre calca el nombre)
            existente = next(
                (x for x in inv if x.get("nombre", "").lower() == nombre), None
            ) or next(
                (x for x in inv if nombre in x.get("nombre", "").lower()
                 or x.get("nombre", "").lower() in nombre), None)
            if existente is None:
                log["rechazados"].append(("quitar_item", nombre))
                continue
            existente["cantidad"] = existente.get("cantidad", 1) - cant
            if existente["cantidad"] <= 0:
                inv.remove(existente)
            log["aplicados"].append(("quitar_item",
                                     f"{existente['nombre']} x{cant}"))
        actor.inventario = inv

    tirada = efectos.get("pedir_tirada")
    if isinstance(tirada, dict) and tirada.get("habilidad"):
        from engine.rules import HABILIDADES
        hab = str(tirada["habilidad"]).lower().strip()[:30]
        if hab not in HABILIDADES:
            log["rechazados"].append(("pedir_tirada", hab))
        else:
            try:
                cd = int(tirada.get("cd", 12))
            except (TypeError, ValueError):
                cd = 12
            cd = max(5, min(30, cd))
            a_quien = str(tirada.get("a_quien", "")).lower().strip()
            grupo_kw = ("", "todos", "el grupo", "grupo", "party", "la party",
                        "todo el grupo", "todos los jugadores", "todos los pj")
            res_c = await db.execute(select(Character).where(
                Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
            vivos = res_c.scalars().all()
            es_grupo = a_quien in grupo_kw
            if es_grupo:
                objetivos = list(vivos)
            else:
                objetivos = [c for c in vivos if c.nombre.lower() == a_quien]
                if not objetivos and actor is not None:
                    objetivos = [actor]
            if objetivos:
                pend = list(camp.tiradas_pendientes or [])
                pend.append({
                    "habilidad": hab, "cd": cd,
                    "motivo": str(tirada.get("motivo", ""))[:120],
                    "pendientes": [c.id for c in objetivos],
                    "tiradas": [],
                })
                camp.tiradas_pendientes = pend
                quien = ("todo el grupo" if es_grupo
                         else ", ".join(c.nombre for c in objetivos))
                db.add(Message(
                    campaign_id=camp.id, autor="sistema", autor_nombre="Sistema",
                    contenido=f"🎲 El DM pide una tirada de **{hab}** (CD {cd}) a "
                              f"{quien}. Cada uno tira con su botón; el DM narra "
                              f"cuando estén todas."))
                log["aplicados"].append(("pedir_tirada", f"{hab} CD{cd} → {quien}"))
            else:
                log["rechazados"].append(("pedir_tirada", a_quien))

    aplicar_cond = efectos.get("aplicar_condicion")
    if isinstance(aplicar_cond, dict) and aplicar_cond.get("tipo"):
        from engine.rules import CONDICIONES_APLICABLES
        tipo = str(aplicar_cond["tipo"]).lower()
        if tipo in CONDICIONES_APLICABLES:
            rondas = min(int(aplicar_cond.get("rondas", 2) or 2), 3)
            objetivo_n = str(aplicar_cond.get("objetivo", "")).lower()
            aplicado = False
            res_c = await db.execute(select(Character).where(
                Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
            for pj in res_c.scalars().all():
                if pj.nombre.lower() == objetivo_n:
                    pj.condiciones = [c for c in pj.condiciones
                                      if c.get("tipo") != tipo] + [
                        {"tipo": tipo, "origen": "dm", "rondas": rondas}]
                    aplicado = True
            if not aplicado:
                res_n = await db.execute(select(NPC).where(
                    NPC.campaign_id == camp.id, NPC.vivo == True))  # noqa: E712
                for npc in res_n.scalars().all():
                    if npc.nombre.lower() == objetivo_n:
                        npc.condiciones = [c for c in npc.condiciones
                                           if c.get("tipo") != tipo] + [
                            {"tipo": tipo, "origen": "dm", "rondas": rondas}]
                        aplicado = True
            if aplicado:
                db.add(Message(campaign_id=camp.id, autor="sistema",
                               autor_nombre="Sistema",
                               contenido=f"⛓ {aplicar_cond.get('objetivo')} "
                                         f"queda {tipo} ({rondas} rondas)."))
                log["aplicados"].append(("aplicar_condicion",
                                         f"{tipo}→{objetivo_n}"))
            else:
                log["rechazados"].append(("aplicar_condicion", objetivo_n))
        else:
            log["rechazados"].append(("aplicar_condicion", tipo))

    quitar_cond = efectos.get("quitar_condicion")
    if isinstance(quitar_cond, dict) and quitar_cond.get("tipo"):
        tipo = str(quitar_cond["tipo"]).lower()
        objetivo_n = str(quitar_cond.get("objetivo", "")).lower()
        for tabla in (Character, NPC):
            res_t = await db.execute(select(tabla).where(
                tabla.campaign_id == camp.id))
            for ent in res_t.scalars().all():
                if ent.nombre.lower() == objetivo_n:
                    ent.condiciones = [c for c in ent.condiciones
                                       if c.get("tipo") != tipo]
                    log["aplicados"].append(("quitar_condicion",
                                             f"{tipo}←{objetivo_n}"))

    insp = efectos.get("otorgar_inspiracion")
    if isinstance(insp, str) and insp.strip():
        objetivo_n = insp.strip().lower()
        res_c = await db.execute(select(Character).where(
            Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
        for pj in res_c.scalars().all():
            if pj.nombre.lower() == objetivo_n:
                if not any(c.get("tipo") == "inspiracion_heroica"
                           for c in pj.condiciones):
                    pj.condiciones = list(pj.condiciones) + [
                        {"tipo": "inspiracion_heroica", "origen": "dm"}]
                db.add(Message(
                    campaign_id=camp.id, autor="sistema", autor_nombre="Sistema",
                    contenido=f"✨ {pj.nombre} gana Inspiración Heroica: "
                              f"ventaja en su próxima tirada."))
                log["aplicados"].append(("inspiracion", pj.nombre))
                break

    # Pagar: el precio viene en oro (PO) pero se cubre con TODA la bolsa
    # (oro + plata + cobre) y se devuelve el cambio en denominaciones óptimas.
    gasto = efectos.get("quitar_monedas")
    if isinstance(gasto, (int, float)) and gasto > 0 and actor is not None:
        gasto = min(int(gasto), 10000)
        costo_cp = gasto * 100
        fondos_cp = _en_cobre(actor.monedas)
        if fondos_cp >= costo_cp:
            nueva = _desde_cobre(fondos_cp - costo_cp)
            actor.monedas = nueva   # reasignar: trampa de mutación JSON
            log["aplicados"].append(("quitar_monedas", gasto))
            db.add(Message(campaign_id=camp.id, autor="sistema",
                           autor_nombre="Sistema",
                           contenido=f"💰 {actor.nombre} paga {gasto} PO "
                                     f"(le quedan {_bolsa_a_texto(nueva)})."))
        else:
            log["rechazados"].append(("quitar_monedas",
                                      f"{gasto} PO > fondos "
                                      f"({fondos_cp / 100:g} PO)"))

    # Otorgar: acepta un entero (oro) o una bolsa {mo,mp,mc}. Se reparte entre
    # los personajes vivos, con tope por nivel promedio.
    oro = efectos.get("otorgar_monedas")
    premio_cp = 0
    if isinstance(oro, dict):
        premio_cp = _en_cobre({k: (v if isinstance(v, (int, float)) else 0)
                               for k, v in oro.items()})
    elif isinstance(oro, int) and oro > 0:
        premio_cp = oro * 100
    if premio_cp > 0:
        res = await db.execute(select(Character).where(
            Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
        chars = res.scalars().all()
        if chars:
            nivel_prom = sum(c.nivel for c in chars) / len(chars)
            tope_cp = int(50 * nivel_prom) * 100
            otorgado_cp = min(premio_cp, tope_cp)
            porcada_cp = max(1, otorgado_cp // len(chars))
            for c in chars:
                c.monedas = _desde_cobre(_en_cobre(c.monedas) + porcada_cp)
            log["aplicados"].append(("monedas", _desde_cobre(porcada_cp)))

    ic = efectos.get("inicia_combate")
    if isinstance(ic, dict):
        monstruos = [m for m in (ic.get("monstruos") or [])
                     if isinstance(m, str) and m in MONSTRUOS][:6]
        if monstruos and camp.estado != "combate":
            # el router decide iniciar el combate con esta lista
            log["inicia_combate"] = monstruos
            log["aplicados"].append(("inicia_combate", monstruos))
        else:
            log["rechazados"].append(("inicia_combate", ic))

    return log
