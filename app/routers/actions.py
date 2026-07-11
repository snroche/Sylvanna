"""Acciones de juego — versión completa.

Cambios clave respecto al paso 3:
- LATENCIA: los endpoints devuelven la resolución mecánica AL INSTANTE y la
  narración del LLM corre en BackgroundTask (Campaign.narrando=True mientras
  tanto; el polling del cliente la levanta cuando está lista).
- TIMEOUT DE TURNO: si un PJ no actúa en 120s, el servidor le aplica Esquivar
  y pasa el turno (se chequea en cada GET de campaña — los clientes pollean).
- DESCANSOS corto (por personaje) y largo (grupal).
- INVENTARIO: usar consumibles, equipar, dar objetos.
- SUBIDA DE NIVEL cuando la XP alcanza.
- MUERTE: _mi_personaje elige el personaje VIVO del jugador (permite reemplazo).
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.combat import Combat
from engine.content import (ARMADURAS, ARMAS, CLASES, CONJUROS, CONSUMIBLES,
                            MONSTRUOS, XP_POR_CR, slots_iniciales)
from engine.dice import roll
from engine.rules import (ataque_magico, cd_salvacion_magica,
                          check_concentracion, curar, descanso_corto,
                          descanso_largo, gastar_slot, mod, nivel_por_xp,
                          puede_lanzar, resolver_ataque, salvacion_muerte,
                          tirada_habilidad, tirada_salvacion)

from ..context import actualizar_resumen_si_corresponde, construir_contexto
from ..db import SessionLocal, get_db
from ..deps import jugador_actual
from ..effects import aplicar_efectos
from ..hydration import (hidratar_npc, hidratar_personaje, persistir_npc,
                         persistir_personaje)
from ..models import (NPC, Campaign, Character, Message, PendingConsequence,
                      Player, Quest, Roll)
from ..narrator import narrar

router = APIRouter(prefix="/api/campaigns/{campaign_id}", tags=["actions"])

TIMEOUT_TURNO_SEG = 120


# ================================================================ helpers

async def _mi_personaje(campaign_id: int, player: Player,
                        db: AsyncSession) -> Character:
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    res = await db.execute(select(Character)
                           .where(Character.player_id == player.id)
                           .order_by(Character.id.desc()))
    chars = res.scalars().all()
    if not chars:
        raise HTTPException(400, "Todavía no creaste un personaje")
    vivo = next((c for c in chars if c.vivo), None)
    if vivo is None:
        raise HTTPException(400, "Tu personaje está muerto. Creá uno nuevo.")
    return vivo


def _msg(db, campaign_id, autor, autor_nombre, contenido):
    db.add(Message(campaign_id=campaign_id, autor=autor,
                   autor_nombre=autor_nombre, contenido=contenido))


def _roll(db, campaign_id, resolucion, character_id=None):
    db.add(Roll(campaign_id=campaign_id, character_id=character_id,
                resolucion=resolucion))


def _quitar_esquivando(char: Character):
    char.condiciones = [c for c in char.condiciones
                        if c.get("tipo") != "esquivando"]


def _inicio_de_turno(char: Character):
    """Limpia condiciones que expiran al empezar el turno del personaje."""
    char.condiciones = [c for c in char.condiciones
                        if c.get("tipo") not in ("esquivando", "ya_ataco")]


# ---------------- narración en background (fix de latencia) ----------------

def encolar_narracion(bg: BackgroundTasks, camp: Campaign,
                      accion: str, actor_id: int | None):
    """Marca narrando=True (el caller comitea) y agenda la narración."""
    camp.narrando = True
    bg.add_task(_narrar_bg, camp.id, accion, actor_id)


async def _narrar_bg(campaign_id: int, accion: str, actor_id: int | None):
    """Corre DESPUÉS de responder el HTTP, con su propia sesión de DB."""
    async with SessionLocal() as db:
        camp = await db.get(Campaign, campaign_id)
        try:
            contexto = await construir_contexto(db, camp)
            narracion, efectos = await narrar(contexto, accion)
            actor = await db.get(Character, actor_id) if actor_id else None
            log = await aplicar_efectos(db, camp, efectos, actor=actor)
            _msg(db, campaign_id, "dm", "DM", narracion)
            if log.get("aplicados"):
                resumen_fx = ", ".join(f"{k}: {v}" for k, v in log["aplicados"])
                _msg(db, campaign_id, "sistema", "Sistema", f"✱ {resumen_fx}")
            if log.get("inicia_combate") and camp.estado != "combate":
                await _iniciar_combate(db, camp, log["inicia_combate"])
            await actualizar_resumen_si_corresponde(db, camp)
        except Exception as e:  # nunca dejar narrando=True colgado
            from ..narrator import NarradorError
            print(f"[narrador-bg] error: {e}")
            if isinstance(e, NarradorError):
                detalle = e.mensaje_humano()
            else:
                detalle = f"error interno del narrador ({type(e).__name__})"
            _msg(db, campaign_id, "sistema", "Sistema",
                 f"⚠ El DM no pudo narrar: {detalle} "
                 f"La mecánica ya está aplicada; pueden continuar.")
        finally:
            camp.narrando = False
            await db.commit()


# ---------------- timeout de turno --------------------------------------

async def chequear_timeout_turno(db: AsyncSession, camp: Campaign) -> list[dict]:
    """Si el PJ del turno actual lleva >120s sin actuar: Esquivar automático
    y pasa el turno. Lo llaman los GET (los clientes pollean constantemente)."""
    if camp.estado != "combate" or not camp.combate:
        return []
    combate = Combat.from_dict(camp.combate)
    if not combate.activo or combate.turno_actual["tipo"] != "pj":
        return []
    ts = combate.turno_ts
    if ts is None or time.time() - ts < TIMEOUT_TURNO_SEG:
        return []

    char = await db.get(Character, int(combate.turno_actual["id"].split("_")[1]))
    if char.pg_actual > 0:
        _inicio_de_turno(char)
        char.condiciones = list(char.condiciones) + [
            {"tipo": "esquivando", "origen": "timeout"}]
        _msg(db, camp.id, "sistema", "Sistema",
             f"⏱ {char.nombre} duda demasiado: se cubre (Esquivar) y pierde el turno.")
    combate.avanzar_turno()
    combate.turno_ts = time.time()
    camp.combate = combate.to_dict()
    eventos = await _resolver_turnos_npc(db, camp)
    await db.commit()
    return eventos


# ================================================================ narrativa

class AccionNarrativa(BaseModel):
    texto: str
    entre_jugadores: bool = False    # True: charla de party, el DM no interviene


@router.post("/say")
async def accion_narrativa(campaign_id: int, body: AccionNarrativa,
                           bg: BackgroundTasks,
                           player: Player = Depends(jugador_actual),
                           db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if body.entre_jugadores:
        # canal de party: se registra (y el DM lo ve en su contexto como
        # charla entre jugadores) pero NO dispara narración
        _msg(db, campaign_id, "party", char.nombre, body.texto)
        await db.commit()
        return {"ok": True, "narrando": False}
    if camp.estado == "combate":
        raise HTTPException(409, "Estás en combate: usá attack o cast")
    _msg(db, campaign_id, "jugador", char.nombre, body.texto)
    encolar_narracion(bg, camp, f"{char.nombre} dice/hace: {body.texto}", char.id)
    await db.commit()
    return {"ok": True, "narrando": True}


class AccionHabilidad(BaseModel):
    habilidad: str
    cd: int = 12
    descripcion: str = ""


@router.post("/skill-check")
async def accion_habilidad(campaign_id: int, body: AccionHabilidad,
                           bg: BackgroundTasks,
                           player: Player = Depends(jugador_actual),
                           db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    cr = hidratar_personaje(char)
    r = tirada_habilidad(cr, body.habilidad, body.cd)
    persistir_personaje(cr, char)
    _msg(db, campaign_id, "jugador", char.nombre,
         f"[{body.habilidad}] {body.descripcion}")
    exito = "✓ éxito" if r["exito"] else "✗ fallo"
    detalle_insp = f" +{r['inspiracion']}🎵" if r.get("inspiracion") else ""
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🎲 {char.nombre} — {body.habilidad}: d20={r['natural']} "
         f"+{r['bono']}{detalle_insp} = {r['total']} → {exito}")
    _roll(db, campaign_id, r, char.id)
    encolar_narracion(
        bg, camp,
        f"{char.nombre} intenta {body.habilidad} "
        f"({body.descripcion or 'sin detalle'}). "
        f"Resultado del sistema: {json.dumps(r, ensure_ascii=False)}",
        char.id)
    await db.commit()
    return {"resolucion": r, "narrando": True}


# ================================================================ combate

async def _iniciar_combate(db: AsyncSession, camp: Campaign,
                           monstruos: list[str]) -> dict:
    npcs = []
    contador: dict[str, int] = {}
    for plantilla in monstruos:
        contador[plantilla] = contador.get(plantilla, 0) + 1
        info = MONSTRUOS[plantilla]
        n = NPC(campaign_id=camp.id, tipo="monstruo", plantilla=plantilla,
                nombre=f"{info['nombre']} {contador[plantilla]}",
                stats=info, pg_actual=info["pg"], en_escena=True,
                actitud="hostil")
        db.add(n)
        npcs.append(n)
    await db.flush()

    res = await db.execute(select(Character).where(
        Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
    chars = res.scalars().all()
    combate = Combat.iniciar([hidratar_personaje(c) for c in chars],
                             [hidratar_npc(n) for n in npcs])
    combate.turno_ts = time.time()
    camp.combate = combate.to_dict()
    camp.estado = "combate"
    _msg(db, camp.id, "sistema", "Sistema",
         f"⚔️ Combate iniciado. Orden: {[e['id'] for e in combate.orden]}")
    _roll(db, camp.id, {"tipo": "inicio_combate",
                        "iniciativas": combate.tiradas_iniciativa})
    eventos = await _resolver_turnos_npc(db, camp)
    return {"orden": combate.orden, "iniciativas": combate.tiradas_iniciativa,
            "turnos_npc": eventos}


class IniciarCombate(BaseModel):
    monstruos: list[str]


@router.post("/combat/start")
async def iniciar_combate_manual(campaign_id: int, body: IniciarCombate,
                                 bg: BackgroundTasks,
                                 player: Player = Depends(jugador_actual),
                                 db: AsyncSession = Depends(get_db)):
    await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "Ya hay un combate activo")
    for m in body.monstruos:
        if m not in MONSTRUOS:
            raise HTTPException(400, f"Monstruo desconocido: {m}. "
                                     f"Opciones: {list(MONSTRUOS)}")
    resultado = await _iniciar_combate(db, camp, body.monstruos)
    encolar_narracion(
        bg, camp,
        f"Comienza un combate contra {body.monstruos}. "
        f"Iniciativas: {json.dumps(resultado['iniciativas'], ensure_ascii=False)}. "
        f"Primeros turnos enemigos: "
        f"{json.dumps(resultado['turnos_npc'], ensure_ascii=False)}",
        None)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {**resultado, "combate": camp.combate}


async def _post_accion_combate(db: AsyncSession, camp: Campaign,
                               combate: Combat, char: Character,
                               objetivo: NPC | None) -> tuple[list, str | None]:
    if objetivo is not None and (objetivo.pg_actual or 0) == 0:
        combate.remover(f"npc_{objetivo.id}")

    fin = None
    if not combate.npcs_restantes():
        fin = "victoria"
        combate.activo = False
        camp.estado = "exploracion"
        camp.combate = None
        res_furia = await db.execute(select(Character).where(
            Character.campaign_id == camp.id))
        for c in res_furia.scalars().all():
            if any(x.get("tipo") in ("furia", "arma_sagrada")
                   for x in c.condiciones):
                c.condiciones = [x for x in c.condiciones
                                 if x.get("tipo") not in ("furia",
                                                          "arma_sagrada")]
        res = await db.execute(select(NPC).where(
            NPC.campaign_id == camp.id, NPC.tipo == "monstruo",
            NPC.vivo == False, NPC.en_escena == True))  # noqa: E712
        caidos = res.scalars().all()
        xp_total = sum(XP_POR_CR.get((n.stats or {}).get("cr", "0"), 10)
                       for n in caidos)
        for n in caidos:
            n.en_escena = False
        res = await db.execute(select(Character).where(
            Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
        vivos = res.scalars().all()
        if vivos and xp_total:
            porcada = max(1, xp_total // len(vivos))
            for c in vivos:
                c.xp += porcada
                if nivel_por_xp(c.xp) > c.nivel:
                    _msg(db, camp.id, "sistema", "Sistema",
                         f"⭐ {c.nombre} puede subir a nivel {nivel_por_xp(c.xp)} "
                         f"(botón en la ficha).")
            _msg(db, camp.id, "sistema", "Sistema",
                 f"⚔️ Victoria. +{porcada} XP para cada personaje vivo.")
    else:
        combate.avanzar_turno()
        combate.turno_ts = time.time()

    camp.combate = combate.to_dict() if combate.activo else None
    eventos = []
    if combate.activo:
        eventos = await _resolver_turnos_npc(db, camp)
        if camp.estado != "combate":
            fin = "derrota"
    return eventos, fin


class Atacar(BaseModel):
    objetivo_npc_id: int
    dos_manos: bool = False


@router.post("/combat/attack")
async def atacar(campaign_id: int, body: Atacar, bg: BackgroundTasks,
                 player: Player = Depends(jugador_actual),
                 db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, "No es tu turno")
    if not char.arma_equipada:
        raise HTTPException(400, "No tenés arma equipada")
    npc = await db.get(NPC, body.objetivo_npc_id)
    if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
        raise HTTPException(404, "Objetivo inválido o ya está fuera de combate")

    _quitar_esquivando(char)
    cr_pj = hidratar_personaje(char)
    cr_npc = hidratar_npc(npc)
    # ataque furtivo: pícaro con un aliado consciente en combate (flanqueo v1)
    furtivo = False
    if char.clase == "picaro":
        res_al = await db.execute(select(Character).where(
            Character.campaign_id == campaign_id, Character.id != char.id,
            Character.vivo == True, Character.pg_actual > 0))  # noqa: E712
        furtivo = res_al.scalars().first() is not None \
            or cr_pj.tiene_condicion("ayudado")
    r = resolver_ataque(cr_pj, cr_npc, ARMAS[char.arma_equipada],
                        dos_manos=body.dos_manos, furtivo=furtivo)
    persistir_personaje(cr_pj, char)
    persistir_npc(cr_npc, npc)
    _msg(db, campaign_id, "jugador", char.nombre, f"[ataque] contra {npc.nombre}")
    _roll(db, campaign_id, r, char.id)

    from engine.content import ATAQUE_EXTRA_NV5
    tiene_oleada = any(c.get("tipo") == "oleada" for c in char.condiciones)
    extra_pendiente = (char.clase in ATAQUE_EXTRA_NV5 and char.nivel >= 5
                       and not any(c.get("tipo") == "ya_ataco"
                                   for c in char.condiciones))
    if tiene_oleada or extra_pendiente:
        # este ataque NO consume el turno (Oleada de Acción / Ataque Extra nv5)
        if tiene_oleada:
            char.condiciones = [c for c in char.condiciones
                                if c.get("tipo") != "oleada"]
        else:
            char.condiciones = list(char.condiciones) + [
                {"tipo": "ya_ataco", "origen": "ataque_extra"}]
        if (npc.pg_actual or 0) == 0:
            combate.remover(f"npc_{npc.id}")
        eventos, fin = ([], None)
        if not combate.npcs_restantes():
            eventos, fin = await _post_accion_combate(db, camp, combate, char, None)
        else:
            camp.combate = combate.to_dict()
    else:
        char.condiciones = [c for c in char.condiciones
                            if c.get("tipo") != "ya_ataco"]
        eventos, fin = await _post_accion_combate(db, camp, combate, char, npc)
    encolar_narracion(
        bg, camp,
        f"Ataque de {char.nombre} contra {npc.nombre}: "
        f"{json.dumps(r, ensure_ascii=False)}. "
        f"Turnos de enemigos: {json.dumps(eventos, ensure_ascii=False)}. "
        f"{('Fin del combate: ' + fin) if fin else 'El combate continúa.'}",
        char.id)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {"resolucion": r, "turnos_npc": eventos, "fin_combate": fin,
            "narrando": True, "combate": camp.combate}


class Lanzar(BaseModel):
    conjuro: str
    objetivo_npc_id: int | None = None
    objetivo_character_id: int | None = None
    nivel_slot: int | None = None


@router.post("/combat/cast")
async def lanzar_conjuro(campaign_id: int, body: Lanzar, bg: BackgroundTasks,
                         player: Player = Depends(jugador_actual),
                         db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, "No es tu turno")

    conjuro = CONJUROS.get(body.conjuro)
    if conjuro is None:
        raise HTTPException(400, f"Conjuro desconocido: {body.conjuro}")

    _quitar_esquivando(char)
    cr_pj = hidratar_personaje(char)
    val = puede_lanzar(cr_pj, body.conjuro)
    if not val["ok"]:
        raise HTTPException(400, f"No podés lanzarlo: {val['motivo']}")

    nivel = conjuro["nivel"]
    gasto = None
    if nivel > 0:
        nivel_usado = body.nivel_slot or nivel
        if nivel_usado < nivel:
            raise HTTPException(400, f"Este conjuro requiere slot nivel {nivel}+")
        gasto = gastar_slot(cr_pj, nivel_usado)
        if not gasto["ok"]:
            raise HTTPException(400, f"Sin espacios: {gasto['motivo']}")

    atributo = CLASES[char.clase]["atributo_magico"] or "INT"

    # trucos escalan a nivel 5: se duplican los dados de daño
    conjuro = dict(conjuro)
    if conjuro["nivel"] == 0 and char.nivel >= 5 and conjuro.get("danio"):
        import re as _re
        conjuro["danio"] = _re.sub(
            r"^(\d+)d", lambda m: f"{int(m.group(1)) * 2}d", conjuro["danio"])

    resoluciones: list[dict] = []
    objetivo_nombre = None
    npc = None

    tipo = conjuro["resolucion"]
    if tipo in ("ataque", "salvacion") or (tipo == "auto" and conjuro.get("proyectiles")):
        npc = await db.get(NPC, body.objetivo_npc_id or -1)
        if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = npc.nombre
        cr_npc = hidratar_npc(npc)

        if tipo == "ataque":
            r = ataque_magico(cr_pj, cr_npc, atributo,
                              conjuro["danio"], conjuro["tipo_danio"])
            resoluciones.append(r)
        elif tipo == "salvacion":
            cd = cd_salvacion_magica(cr_pj, atributo)
            salv = tirada_salvacion(cr_npc, conjuro["salvacion"], cd)
            resoluciones.append(salv)
            if conjuro.get("danio"):
                d = roll(conjuro["danio"])
                final = d["total"]
                if salv["exito"]:
                    final = final // 2 if conjuro.get(
                        "en_salvacion_exitosa") == "mitad" else 0
                if final:
                    from engine.rules import aplicar_danio
                    ev = aplicar_danio(cr_npc, final)
                    resoluciones.append({"tipo": "danio_conjuro", **d,
                                         "final": final,
                                         "efectos": ev["eventos"]})
            elif not salv["exito"]:
                cond = ("paralizado" if "inmovilizar" in body.conjuro
                        else "hechizado")
                cr_npc.condiciones.append({"tipo": cond, "origen": body.conjuro})
                resoluciones.append({"tipo": "condicion_aplicada",
                                     "conjuro": body.conjuro})
        else:  # auto con proyectiles (proyectil mágico)
            from engine.rules import aplicar_danio
            total, dados = 0, []
            for _ in range(conjuro["proyectiles"]):
                d = roll(conjuro["danio"])
                dados.append(d["dados"])
                total += d["total"]
            ev = aplicar_danio(cr_npc, total)
            resoluciones.append({"tipo": "danio_auto", "dados": dados,
                                 "total_final": total,
                                 "efectos": ev["eventos"]})
        persistir_npc(cr_npc, npc)

    elif tipo == "curacion":
        obj = await db.get(Character, body.objetivo_character_id or char.id)
        if obj is None or obj.campaign_id != campaign_id:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = obj.nombre
        cr_obj = hidratar_personaje(obj) if obj.id != char.id else cr_pj
        d = roll(conjuro["curacion"])
        total = d["total"] + (mod(cr_pj.atributos[atributo])
                              if conjuro.get("suma_mod_magico") else 0)
        # Discípulo de la Vida: +2 + nivel del conjuro
        if char.subclase == "dominio_de_la_vida" and conjuro["nivel"] >= 1:
            total += 2 + (body.nivel_slot or conjuro["nivel"])
        cur = curar(cr_obj, total)
        resoluciones.append({"tipo": "curacion", **d, "total_final": total, **cur})
        if obj.id != char.id:
            persistir_personaje(cr_obj, obj)

    else:  # auto sin proyectiles (escudo, bendecir...)
        resoluciones.append({"tipo": "efecto_auto",
                             "efecto": conjuro.get("efecto", body.conjuro)})

    if conjuro.get("concentracion"):
        cr_pj.spell_state.concentracion_activa = {
            "hechizo": body.conjuro, "desde_ronda": combate.ronda}

    persistir_personaje(cr_pj, char)
    _msg(db, campaign_id, "jugador", char.nombre,
         f"[conjuro] {body.conjuro}" +
         (f" contra {objetivo_nombre}" if objetivo_nombre else ""))
    for r in resoluciones:
        _roll(db, campaign_id, r, char.id)

    eventos, fin = await _post_accion_combate(db, camp, combate, char, npc)
    encolar_narracion(
        bg, camp,
        f"{char.nombre} lanza {body.conjuro}"
        f"{' contra ' + objetivo_nombre if objetivo_nombre else ''}. "
        f"Resultados: {json.dumps(resoluciones, ensure_ascii=False)}. "
        f"Turnos de enemigos: {json.dumps(eventos, ensure_ascii=False)}. "
        f"{('Fin del combate: ' + fin) if fin else ''}",
        char.id)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {"resoluciones": resoluciones, "gasto_slot": gasto,
            "turnos_npc": eventos, "fin_combate": fin,
            "narrando": True, "combate": camp.combate}


async def _resolver_turnos_npc(db: AsyncSession, camp: Campaign) -> list[dict]:
    if not camp.combate:
        return []
    combate = Combat.from_dict(camp.combate)
    eventos: list[dict] = []

    for _ in range(30):
        if not combate.activo:
            break
        actual = combate.turno_actual

        if actual["tipo"] == "pj":
            char = await db.get(Character, int(actual["id"].split("_")[1]))
            if char.pg_actual > 0:
                _inicio_de_turno(char)
                break
            cr = hidratar_personaje(char)
            r = salvacion_muerte(cr)
            persistir_personaje(cr, char)
            eventos.append({"actor": char.nombre, "salvacion_muerte": r})
            _roll(db, camp.id, r, char.id)
            if r["evento"] == "muerte":
                _msg(db, camp.id, "sistema", "Sistema",
                     f"💀 {char.nombre} ha muerto.")
                combate.remover(actual["id"])
                if not combate.pjs_restantes():
                    camp.estado = "exploracion"
                    camp.combate = None
                    eventos.append({"fin_combate": "derrota_total"})
                    return eventos
            else:
                combate.avanzar_turno()
            continue

        npc = await db.get(NPC, int(actual["id"].split("_")[1]))
        res = await db.execute(select(Character).where(
            Character.campaign_id == camp.id,
            Character.vivo == True, Character.pg_actual > 0))  # noqa: E712
        objetivos = res.scalars().all()
        if not objetivos:
            camp.estado = "exploracion"
            camp.combate = None
            eventos.append({"fin_combate": "derrota_total"})
            return eventos

        objetivo = min(objetivos, key=lambda c: c.pg_actual)
        cr_npc = hidratar_npc(npc)
        cr_pj = hidratar_personaje(objetivo)
        ataques_sb = (npc.stats or {}).get("ataques") or []
        if ataques_sb:
            from engine.rules import ataque_statblock
            a = ataques_sb[0]
            r = ataque_statblock(cr_npc, cr_pj, a["nombre"], a["bono"],
                                 a["danio"])
        else:
            arma_nombre = (npc.stats or {}).get("armas", ["garrote"])[0]
            arma = ARMAS.get(arma_nombre, ARMAS["garrote"])
            r = resolver_ataque(cr_npc, cr_pj, arma)
        if "requiere_check_concentracion" in r.get("efectos", []):
            conc = check_concentracion(cr_pj, r["danio"]["total_final"])
            eventos.append({"actor": objetivo.nombre, "concentracion": conc})
            _roll(db, camp.id, conc, objetivo.id)
        persistir_personaje(cr_pj, objetivo)
        persistir_npc(cr_npc, npc)
        eventos.append({"actor": npc.nombre, "ataque": r,
                        "objetivo": objetivo.nombre})
        _roll(db, camp.id, r)
        combate.avanzar_turno()

    combate.turno_ts = time.time()
    camp.combate = combate.to_dict() if combate.activo else None
    return eventos


# ================================================================ deshacer / regenerar

def _es_marcador(m) -> bool:
    return m.autor == "sistema" and m.contenido[:1] in ("↺", "⌫")


def _par_narrativo(msgs: list):
    """Devuelve (accion, dm) si el final del log es jugador→dm (ignorando
    nuestros marcadores ↺/⌫), o None si hay mecánica en el medio."""
    limpio = [m for m in msgs if not _es_marcador(m)]
    if len(limpio) >= 2 and limpio[-1].autor == "dm" \
            and limpio[-2].autor == "jugador":
        return limpio[-2], limpio[-1]
    return None


async def _ultimos_mensajes(db, campaign_id, n=6):
    res = await db.execute(
        select(Message).where(Message.campaign_id == campaign_id)
        .order_by(Message.id.desc()).limit(n))
    return list(reversed(res.scalars().all()))


@router.post("/narration/regenerate")
async def regenerar_narracion(campaign_id: int, bg: BackgroundTasks,
                              player: Player = Depends(jugador_actual),
                              db: AsyncSession = Depends(get_db)):
    """Borra la última respuesta del DM y vuelve a narrar la misma acción.
    Solo si el final del log es (acción de jugador → dm), sin mecánica en
    el medio: las tiradas y el combate no se re-tiran."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.narrando:
        raise HTTPException(409, "El DM está narrando: esperá")
    if camp.estado == "combate":
        raise HTTPException(409, "No se regenera narración en combate")
    msgs = await _ultimos_mensajes(db, campaign_id)
    par = _par_narrativo(msgs)
    if par is None:
        raise HTTPException(409, "Solo se puede regenerar la respuesta a una "
                                 "acción narrativa simple (sin tiradas ni "
                                 "mecánica en el medio)")
    accion, dm = par
    await db.delete(dm)
    _msg(db, campaign_id, "sistema", "Sistema",
         f"↺ {char.nombre} pidió regenerar la última narración.")
    encolar_narracion(bg, camp,
                      f"{accion.autor_nombre} dice/hace: {accion.contenido} "
                      f"(REGENERACIÓN: narrá esta acción de nuevo, distinto "
                      f"al intento anterior)", char.id)
    await db.commit()
    return {"ok": True, "narrando": True}


@router.post("/narration/undo")
async def deshacer_accion(campaign_id: int,
                          player: Player = Depends(jugador_actual),
                          db: AsyncSession = Depends(get_db)):
    """Borra el último par (acción del jugador → respuesta del DM).
    Mismas restricciones que regenerate. Los efectos ya aplicados por esa
    narración (XP, loot) no se revierten: es un deshacer de conversación."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.narrando:
        raise HTTPException(409, "El DM está narrando: esperá")
    if camp.estado == "combate":
        raise HTTPException(409, "No se deshace en combate")
    msgs = await _ultimos_mensajes(db, campaign_id)
    par = _par_narrativo(msgs)
    if par is None:
        raise HTTPException(409, "Solo se puede deshacer un par acción→"
                                 "narración simple")
    accion, dm = par
    await db.delete(dm)
    await db.delete(accion)
    _msg(db, campaign_id, "sistema", "Sistema",
         f"⌫ {char.nombre} deshizo la última acción.")
    await db.commit()
    return {"ok": True}


# ================================================================ typing

@router.post("/typing")
async def escribiendo(campaign_id: int,
                      player: Player = Depends(jugador_actual),
                      db: AsyncSession = Depends(get_db)):
    """Heartbeat liviano: 'este jugador está tipeando'. El cliente lo manda
    cada ~3s mientras el input tiene texto; expira solo a los 6s."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    t = dict(camp.typing or {})
    t[char.nombre] = time.time()
    # limpiar vencidos para que el JSON no crezca
    camp.typing = {k: v for k, v in t.items() if time.time() - v < 10}
    await db.commit()
    return {"ok": True}


# ================================================================ habilidades de clase

class UsarHabilidadClase(BaseModel):
    nombre: str
    objetivo_character_id: int | None = None
    cantidad: int | None = None      # imposición de manos: cuántos PG del pool


@router.post("/class-ability")
async def habilidad_clase(campaign_id: int, body: UsarHabilidadClase,
                          player: Player = Depends(jugador_actual),
                          db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    import copy
    recursos = copy.deepcopy(char.recursos_clase or {})
    rec = recursos.get(body.nombre)
    if rec is None:
        raise HTTPException(400, f"Tu clase no tiene '{body.nombre}' (o no al "
                                 f"nivel {char.nivel})")

    en_combate = camp.estado == "combate" and camp.combate
    if en_combate:
        combate = Combat.from_dict(camp.combate)
        if not combate.es_turno_de(f"pj_{char.id}"):
            raise HTTPException(409, "En combate, solo en tu turno")

    resultado: dict = {"habilidad": body.nombre}

    if body.nombre == "furia":
        if not en_combate:
            raise HTTPException(409, "La furia se activa en combate")
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Sin usos de furia hasta descansar")
        if any(c.get("tipo") == "furia" for c in char.condiciones):
            raise HTTPException(409, "Ya estás en furia")
        rec["usados"] += 1
        char.condiciones = list(char.condiciones) + [
            {"tipo": "furia", "origen": "clase"}]
        resultado["efecto"] = "+2 daño melé hasta que termine el combate"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"💢 {char.nombre} entra en FURIA.")

    elif body.nombre == "nuevo_aliento":
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Ya usaste Nuevo Aliento (descanso corto)")
        rec["usados"] += 1
        cr = hidratar_personaje(char)
        d = roll("1d10")
        cur = curar(cr, d["total"] + char.nivel)
        persistir_personaje(cr, char)
        resultado.update({"tipo": "curacion", **d, "curado": cur["curado"],
                          "pg_actual": char.pg_actual})
        _msg(db, campaign_id, "sistema", "Sistema",
             f"❤️ {char.nombre} usa Nuevo Aliento: +{cur['curado']} PG.")

    elif body.nombre == "oleada_de_accion":
        if not en_combate:
            raise HTTPException(409, "Solo en combate")
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Ya usaste Oleada de Acción")
        rec["usados"] += 1
        char.condiciones = list(char.condiciones) + [
            {"tipo": "oleada", "origen": "clase"}]
        resultado["efecto"] = "tu próximo ataque este turno no consume el turno"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"⚡ {char.nombre} usa Oleada de Acción: ¡ataca dos veces!")

    elif body.nombre == "canalizar_divinidad":
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Sin usos (descanso corto)")
        obj = await db.get(Character, body.objetivo_character_id or char.id)
        if obj is None or obj.campaign_id != campaign_id or not obj.vivo:
            raise HTTPException(404, "Objetivo inválido")
        rec["usados"] += 1
        cr_o = hidratar_personaje(obj)
        cur = curar(cr_o, 5 * char.nivel)
        persistir_personaje(cr_o, obj)
        resultado.update({"tipo": "curacion", "curado": cur["curado"],
                          "objetivo": obj.nombre})
        _msg(db, campaign_id, "sistema", "Sistema",
             f"✝️ {char.nombre} canaliza divinidad: {obj.nombre} +{cur['curado']} PG.")

    elif body.nombre == "imposicion_de_manos":
        cant = body.cantidad or 0
        if cant <= 0 or cant > rec.get("pool", 0):
            raise HTTPException(400, f"Cantidad inválida (pool: {rec.get('pool', 0)})")
        obj = await db.get(Character, body.objetivo_character_id or char.id)
        if obj is None or obj.campaign_id != campaign_id or not obj.vivo:
            raise HTTPException(404, "Objetivo inválido")
        rec["pool"] -= cant
        cr_o = hidratar_personaje(obj)
        cur = curar(cr_o, cant)
        persistir_personaje(cr_o, obj)
        resultado.update({"tipo": "curacion", "curado": cur["curado"],
                          "objetivo": obj.nombre, "pool_restante": rec["pool"]})
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🙏 {char.nombre} impone manos: {obj.nombre} +{cur['curado']} PG.")

    elif body.nombre == "inspiracion_bardica":
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Sin inspiraciones hasta descanso largo")
        obj = await db.get(Character, body.objetivo_character_id or -1)
        if obj is None or obj.campaign_id != campaign_id or not obj.vivo \
                or obj.id == char.id:
            raise HTTPException(404, "Elegí a un aliado (no a vos)")
        rec["usados"] += 1
        dado_insp = "1d8" if char.nivel >= 5 else "1d6"
        obj.condiciones = list(obj.condiciones) + [
            {"tipo": "inspirado", "origen": char.nombre, "dado": dado_insp}]
        resultado["efecto"] = f"{obj.nombre} suma {dado_insp} a su próxima tirada"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🎵 {char.nombre} inspira a {obj.nombre} (+1d6 próxima tirada).")

    elif body.nombre == "rafaga_de_golpes":
        if not en_combate:
            raise HTTPException(409, "Solo en combate")
        ki = recursos.get("ki")
        if not ki or ki["usados"] >= ki["max"]:
            raise HTTPException(400, "Sin puntos de ki (descanso corto)")
        ki["usados"] += 1
        char.condiciones = list(char.condiciones) + [
            {"tipo": "oleada", "origen": "ki"}]
        resultado["efecto"] = "un ataque extra este turno"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"👊 {char.nombre} desata una ráfaga de golpes.")

    elif body.nombre == "defensa_paciente":
        if not en_combate:
            raise HTTPException(409, "Solo en combate")
        ki = recursos.get("ki")
        if not ki or ki["usados"] >= ki["max"]:
            raise HTTPException(400, "Sin puntos de ki")
        ki["usados"] += 1
        _quitar_esquivando(char)
        char.condiciones = list(char.condiciones) + [
            {"tipo": "esquivando", "origen": "ki"}]
        resultado["efecto"] = "esquivás sin perder el turno"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🧘 {char.nombre} adopta defensa paciente (y aún puede actuar).")

    elif body.nombre == "frenesi":
        if not en_combate:
            raise HTTPException(409, "Solo en combate")
        if char.subclase != "senda_del_berserker" or char.nivel < 3:
            raise HTTPException(400, "Requiere Berserker nivel 3")
        if not any(c.get("tipo") == "furia" for c in char.condiciones):
            raise HTTPException(409, "El frenesí requiere estar en furia")
        if any(c.get("tipo") == "oleada" for c in char.condiciones):
            raise HTTPException(409, "Ya tenés un ataque extra pendiente")
        char.condiciones = list(char.condiciones) + [
            {"tipo": "oleada", "origen": "frenesi"}]
        resultado["efecto"] = "un ataque extra este turno (frenesí)"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🔥 {char.nombre} entra en frenesí.")

    elif body.nombre == "arma_sagrada":
        if char.subclase != "juramento_de_devocion" or char.nivel < 3:
            raise HTTPException(400, "Requiere Juramento de Devoción nivel 3")
        cd_rec = recursos.get("canalizar_divinidad")
        if not cd_rec or cd_rec["usados"] >= cd_rec["max"]:
            raise HTTPException(400, "Sin usos de Canalizar (descanso corto)")
        cd_rec["usados"] += 1
        valor = max(1, mod(char.atributos["CAR"]))
        char.condiciones = [c for c in char.condiciones
                            if c.get("tipo") != "arma_sagrada"] + [
            {"tipo": "arma_sagrada", "origen": "devocion", "valor": valor}]
        resultado["efecto"] = f"+{valor} a tus ataques hasta el fin del combate"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"✨ El arma de {char.nombre} resplandece (+{valor} al ataque).")

    else:
        raise HTTPException(400, f"Habilidad sin efecto activo: {body.nombre}")

    char.recursos_clase = recursos
    _roll(db, campaign_id, {"tipo": "habilidad_clase", **resultado}, char.id)
    await db.commit()
    return resultado


# ================================================================ acciones de combate

def _combate_activo(camp: Campaign, char: Character) -> Combat:
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, "No es tu turno")
    return combate


async def _cerrar_turno(db, camp, combate, char):
    combate.avanzar_turno()
    combate.turno_ts = time.time()
    camp.combate = combate.to_dict()
    return await _resolver_turnos_npc(db, camp)


@router.post("/combat/dodge")
async def esquivar(campaign_id: int,
                   player: Player = Depends(jugador_actual),
                   db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    combate = _combate_activo(camp, char)
    _quitar_esquivando(char)
    char.condiciones = list(char.condiciones) + [
        {"tipo": "esquivando", "origen": "accion"}]
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🛡 {char.nombre} se pone a la defensiva (los ataques en su contra "
         f"tienen desventaja hasta su próximo turno).")
    eventos = await _cerrar_turno(db, camp, combate, char)
    await db.commit()
    return {"ok": True, "turnos_npc": eventos}


class Ayudar(BaseModel):
    aliado_character_id: int


@router.post("/combat/help")
async def ayudar(campaign_id: int, body: Ayudar,
                 player: Player = Depends(jugador_actual),
                 db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    combate = _combate_activo(camp, char)
    obj = await db.get(Character, body.aliado_character_id)
    if obj is None or obj.campaign_id != campaign_id or not obj.vivo \
            or obj.id == char.id:
        raise HTTPException(404, "Elegí a un aliado (no a vos)")
    obj.condiciones = list(obj.condiciones) + [
        {"tipo": "ayudado", "origen": char.nombre}]
    _quitar_esquivando(char)
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🤝 {char.nombre} ayuda a {obj.nombre}: ventaja en su próximo ataque.")
    eventos = await _cerrar_turno(db, camp, combate, char)
    await db.commit()
    return {"ok": True, "turnos_npc": eventos}


class Empujar(BaseModel):
    objetivo_npc_id: int


@router.post("/combat/shove")
async def empujar(campaign_id: int, body: Empujar,
                  player: Player = Depends(jugador_actual),
                  db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    combate = _combate_activo(camp, char)
    npc = await db.get(NPC, body.objetivo_npc_id)
    if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
        raise HTTPException(404, "Objetivo inválido")
    _quitar_esquivando(char)
    cr_pj = hidratar_personaje(char)
    cr_npc = hidratar_npc(npc)
    cd = 10 + mod(cr_npc.atributos["DES"])
    r = tirada_habilidad(cr_pj, "atletismo", cd)
    persistir_personaje(cr_pj, char)
    if r["exito"]:
        cr_npc.condiciones.append({"tipo": "derribado", "origen": "empujon"})
        persistir_npc(cr_npc, npc)
        _msg(db, campaign_id, "sistema", "Sistema",
             f"💥 {char.nombre} derriba a {npc.nombre} (los ataques melé en "
             f"su contra tienen ventaja).")
    else:
        _msg(db, campaign_id, "sistema", "Sistema",
             f"{char.nombre} intenta derribar a {npc.nombre} y falla.")
    _roll(db, campaign_id, r, char.id)
    eventos = await _cerrar_turno(db, camp, combate, char)
    await db.commit()
    return {"resolucion": r, "derribado": r["exito"], "turnos_npc": eventos}


@router.post("/combat/flee")
async def huir(campaign_id: int, bg: BackgroundTasks,
               player: Player = Depends(jugador_actual),
               db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    combate = _combate_activo(camp, char)
    _quitar_esquivando(char)
    cr_pj = hidratar_personaje(char)
    r = tirada_habilidad(cr_pj, "acrobacias", 12)
    _roll(db, campaign_id, r, char.id)
    eventos = []
    if r["exito"]:
        combate.remover(f"pj_{char.id}")
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🏃 {char.nombre} escapa del combate.")
        if not combate.pjs_restantes():
            camp.estado = "exploracion"
            camp.combate = None
            for n in (await db.execute(select(NPC).where(
                    NPC.campaign_id == campaign_id, NPC.tipo == "monstruo",
                    NPC.en_escena == True))).scalars().all():  # noqa: E712
                n.en_escena = False
            _msg(db, campaign_id, "sistema", "Sistema",
                 "El grupo entero huyó. El combate termina... por ahora.")
            encolar_narracion(bg, camp,
                              "El grupo huyó del combate. Narrá la retirada "
                              "y sus posibles consecuencias.", char.id)
        else:
            camp.combate = combate.to_dict()
            eventos = await _resolver_turnos_npc(db, camp)
    else:
        # fallo: un enemigo lo castiga y no escapa
        npcs_ids = combate.npcs_restantes()
        if npcs_ids:
            npc = await db.get(NPC, int(npcs_ids[0].split("_")[1]))
            arma_n = (npc.stats or {}).get("armas", ["garrote"])[0]
            atk = resolver_ataque(hidratar_npc(npc), cr_pj,
                                  ARMAS.get(arma_n, ARMAS["garrote"]))
            eventos.append({"actor": npc.nombre, "ataque": atk,
                            "objetivo": char.nombre})
            _roll(db, campaign_id, atk)
        _msg(db, campaign_id, "sistema", "Sistema",
             f"{char.nombre} intenta huir, tropieza, y recibe un golpe "
             f"de oportunidad.")
        eventos += await _cerrar_turno(db, camp, combate, char)
    persistir_personaje(cr_pj, char)
    await db.commit()
    return {"resolucion": r, "escapo": r["exito"], "turnos_npc": eventos}


# ================================================================ descansos

class DescansoCorto(BaseModel):
    dados: int = 1


@router.post("/rest/short")
async def rest_short(campaign_id: int, body: DescansoCorto,
                     player: Player = Depends(jugador_actual),
                     db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "No se descansa en combate")
    cr = hidratar_personaje(char)
    r = descanso_corto(cr, body.dados)
    if not r["ok"]:
        raise HTTPException(400, f"No podés: {r['motivo']} "
                                 f"(disponibles: {r.get('disponibles', 0)})")
    # Brujo: recupera todos sus slots con descanso corto
    if char.clase == "brujo" and cr.spell_state:
        for s in cr.spell_state.slots.values():
            s["usados"] = 0
        r["slots_brujo_recuperados"] = True
    # recursos de clase con reset corto (deepcopy: trampa de mutación JSON)
    import copy
    recursos = copy.deepcopy(char.recursos_clase or {})
    for nombre, rec in recursos.items():
        if rec.get("reset") == "corto" and "usados" in rec:
            rec["usados"] = 0
    # Recuperación Arcana del mago: 1 vez por día, automática en el corto
    ra = recursos.get("recuperacion_arcana")
    if ra and ra["usados"] < ra["max"] and cr.spell_state:
        presupuesto = (char.nivel + 1) // 2
        recuperados = []
        for nv in sorted(cr.spell_state.slots, key=int):
            s = cr.spell_state.slots[nv]
            while s["usados"] > 0 and presupuesto >= int(nv):
                s["usados"] -= 1
                presupuesto -= int(nv)
                recuperados.append(nv)
        if recuperados:
            ra["usados"] = 1
            r["recuperacion_arcana"] = recuperados
    char.recursos_clase = recursos
    persistir_personaje(cr, char)
    camp.tiempo_juego_min += 60
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🔥 {char.nombre} descansa una hora: gasta {body.dados} dado(s) de "
         f"golpe y recupera {r['curado']} PG "
         f"({char.pg_actual}/{char.pg_max}).")
    _roll(db, campaign_id, r, char.id)
    await db.commit()
    return r


@router.post("/rest/long")
async def rest_long(campaign_id: int, bg: BackgroundTasks,
                    player: Player = Depends(jugador_actual),
                    db: AsyncSession = Depends(get_db)):
    await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "No se descansa en combate")
    if camp.tiempo_juego_min - camp.ultimo_descanso_largo_min < 480:
        raise HTTPException(409, "Descansaron hace muy poco (regla de una vez "
                                 "por día de juego)")
    res = await db.execute(select(Character).where(
        Character.campaign_id == campaign_id, Character.vivo == True))  # noqa: E712
    resultados = {}
    from engine.content import recursos_clase_iniciales
    for c in res.scalars().all():
        cr = hidratar_personaje(c)
        r = descanso_largo(cr)
        persistir_personaje(cr, c)
        c.pg_actual = c.pg_max  # persistir_personaje ya lo hace; explícito
        c.recursos_clase = recursos_clase_iniciales(
            c.clase, c.nivel, mod(c.atributos["CAR"]))
        resultados[c.nombre] = {"pg": c.pg_max, "dados": c.dados_golpe_disp}
    camp.tiempo_juego_min += 480
    camp.ultimo_descanso_largo_min = camp.tiempo_juego_min
    _msg(db, campaign_id, "sistema", "Sistema",
         "🌙 El grupo hace un descanso largo: PG al máximo, espacios de "
         "conjuro recuperados, mitad de los dados de golpe de vuelta.")
    encolar_narracion(bg, camp,
                      "El grupo acampa y hace un descanso largo de 8 horas. "
                      "Narrá el paso de la noche (puede pasar algo o no).",
                      None)
    await db.commit()
    return {"ok": True, "resultados": resultados}


# ================================================================ inventario

class UsarObjeto(BaseModel):
    nombre: str


@router.post("/inventory/use")
async def usar_objeto(campaign_id: int, body: UsarObjeto,
                      player: Player = Depends(jugador_actual),
                      db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    inv = list(char.inventario)
    item = next((x for x in inv if x.get("nombre") == body.nombre
                 and x.get("cantidad", 0) > 0), None)
    if item is None:
        raise HTTPException(404, f"No tenés {body.nombre}")

    info = CONSUMIBLES.get(body.nombre, {"efecto": "narrativo"})
    resultado = {"objeto": body.nombre}
    if info["efecto"] == "curacion":
        if camp.estado == "combate":
            combate = Combat.from_dict(camp.combate)
            if not combate.es_turno_de(f"pj_{char.id}"):
                raise HTTPException(409, "En combate solo podés usar objetos "
                                         "en tu turno")
        cr = hidratar_personaje(char)
        d = roll(info["formula"])
        cur = curar(cr, d["total"])
        persistir_personaje(cr, char)
        resultado.update({"tipo": "curacion", **d, "curado": cur["curado"],
                          "pg_actual": char.pg_actual})
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🧪 {char.nombre} usa {body.nombre}: +{cur['curado']} PG "
             f"({char.pg_actual}/{char.pg_max}).")
        _roll(db, campaign_id, resultado, char.id)
        # usar objeto en combate consume el turno
        if camp.estado == "combate":
            combate = Combat.from_dict(camp.combate)
            combate.avanzar_turno()
            combate.turno_ts = time.time()
            camp.combate = combate.to_dict()
            await _resolver_turnos_npc(db, camp)
    else:
        _msg(db, campaign_id, "sistema", "Sistema",
             f"{char.nombre} usa {body.nombre}.")

    item["cantidad"] -= 1
    char.inventario = [x for x in inv if x.get("cantidad", 0) > 0]
    await db.commit()
    return resultado


class Equipar(BaseModel):
    arma: str | None = None
    armadura: str | None = None
    escudo: bool | None = None


@router.post("/inventory/equip")
async def equipar(campaign_id: int, body: Equipar,
                  player: Player = Depends(jugador_actual),
                  db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "No podés reequiparte en pleno combate")
    nombres_inv = {x.get("nombre") for x in char.inventario}
    if body.arma is not None:
        if body.arma not in ARMAS:
            raise HTTPException(400, "Arma desconocida")
        if body.arma not in nombres_inv and body.arma != char.arma_equipada:
            raise HTTPException(400, f"No tenés {body.arma} en el inventario")
        char.arma_equipada = body.arma
    if body.armadura is not None:
        if body.armadura and body.armadura not in ARMADURAS:
            raise HTTPException(400, "Armadura desconocida")
        if body.armadura and body.armadura not in nombres_inv \
                and body.armadura != char.armadura:
            raise HTTPException(400, f"No tenés {body.armadura}")
        char.armadura = body.armadura or None
    if body.escudo is not None:
        char.escudo = body.escudo
    await db.commit()
    from engine.rules import calcular_ca
    return {"ok": True, "arma": char.arma_equipada,
            "armadura": char.armadura, "escudo": char.escudo,
            "ca": calcular_ca(hidratar_personaje(char))}


class DarObjeto(BaseModel):
    a_character_id: int
    nombre: str
    cantidad: int = 1


@router.post("/inventory/give")
async def dar_objeto(campaign_id: int, body: DarObjeto,
                     player: Player = Depends(jugador_actual),
                     db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    destino = await db.get(Character, body.a_character_id)
    if destino is None or destino.campaign_id != campaign_id or not destino.vivo:
        raise HTTPException(404, "Destinatario inválido")
    inv = list(char.inventario)
    item = next((x for x in inv if x.get("nombre") == body.nombre), None)
    if item is None or item.get("cantidad", 0) < body.cantidad:
        raise HTTPException(400, f"No tenés {body.cantidad}x {body.nombre}")
    item["cantidad"] -= body.cantidad
    char.inventario = [x for x in inv if x.get("cantidad", 0) > 0]
    inv2 = list(destino.inventario)
    ex = next((x for x in inv2 if x.get("nombre") == body.nombre), None)
    if ex:
        ex["cantidad"] = ex.get("cantidad", 1) + body.cantidad
    else:
        inv2.append({"nombre": body.nombre, "cantidad": body.cantidad})
    destino.inventario = inv2
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🎒 {char.nombre} le da {body.cantidad}x {body.nombre} a "
         f"{destino.nombre}.")
    await db.commit()
    return {"ok": True}


# ================================================================ conjuros

class GestionarConjuros(BaseModel):
    lista: list[str]


@router.post("/spells/manage")
async def gestionar_conjuros(campaign_id: int, body: GestionarConjuros,
                             player: Player = Depends(jugador_actual),
                             db: AsyncSession = Depends(get_db)):
    """Setea los conjuros preparados (mago/clérigo/druida/paladín) o
    conocidos (bardo/hechicero/brujo/ranger), con validación completa:
    existencia, nivel lanzable y cantidad máxima. Solo fuera de combate."""
    from engine.content import limite_conjuros, nivel_max_conjuro
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "No podés reorganizar conjuros en combate")

    atributo = CLASES[char.clase]["atributo_magico"]
    if not atributo:
        raise HTTPException(400, "Tu clase no lanza conjuros")
    sistema, limite = limite_conjuros(char.clase, char.nivel,
                                      mod(char.atributos[atributo]))
    if sistema == "ninguno" or limite == 0:
        raise HTTPException(400, "Tu clase no maneja conjuros a este nivel")

    nv_max = nivel_max_conjuro(char.clase, char.nivel)
    trucos, con_nivel = [], []
    for nombre in dict.fromkeys(body.lista):   # dedup preservando orden
        c = CONJUROS.get(nombre)
        if c is None:
            raise HTTPException(400, f"Conjuro desconocido: {nombre}")
        if c["nivel"] == 0:
            trucos.append(nombre)
        else:
            if c["nivel"] > nv_max:
                raise HTTPException(400, f"{nombre} es nivel {c['nivel']} y tu "
                                         f"máximo lanzable es {nv_max}")
            con_nivel.append(nombre)
    if len(con_nivel) > limite:
        raise HTTPException(400, f"Máximo {limite} conjuros con nivel "
                                 f"({sistema}); mandaste {len(con_nivel)}")
    if len(trucos) > 6:
        raise HTTPException(400, "Máximo 6 trucos")

    final = trucos + con_nivel
    if sistema == "preparados":
        char.preparados = final
    else:
        char.conocidos = final
    _msg(db, campaign_id, "sistema", "Sistema",
         f"📜 {char.nombre} reorganiza sus conjuros ({len(con_nivel)}/{limite} "
         f"con nivel + {len(trucos)} trucos).")
    await db.commit()
    return {"sistema": sistema, "limite": limite, "nivel_max": nv_max,
            "lista": final}


# ================================================================ nivel

class SubirNivel(BaseModel):
    metodo: str = "fijo"   # "fijo" (mitad+1) | "tirar"
    # Mejora de atributos (niveles 4 y 8): {"FUE": 2} o {"DES": 1, "CON": 1}
    asi: dict[str, int] | None = None
    subclase: str | None = None   # requerida al llegar al nivel de subclase


@router.post("/level-up")
async def subir_nivel(campaign_id: int, body: SubirNivel,
                      player: Player = Depends(jugador_actual),
                      db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    objetivo = nivel_por_xp(char.xp)
    if objetivo <= char.nivel:
        raise HTTPException(400, f"Todavía no tenés XP para subir "
                                 f"(nivel {char.nivel}, {char.xp} XP)")
    nuevo_nivel = char.nivel + 1
    # subclase al llegar al nivel correspondiente (elección narrativa v1)
    from engine.content import NIVEL_SUBCLASE, SUBCLASES_SRD
    if nuevo_nivel == NIVEL_SUBCLASE.get(char.clase) and not char.subclase:
        opciones = SUBCLASES_SRD.get(char.clase, [])
        if body.subclase not in opciones and not (body.subclase or "").strip():
            raise HTTPException(400,
                f"Nivel {nuevo_nivel}: elegí subclase. Del SRD: {opciones} "
                f"(o escribí la tuya como texto libre)")
        char.subclase = (body.subclase or "").strip()[:60]
    # ASI en niveles 4 y 8 (SRD): +2 puntos de atributo a repartir
    if nuevo_nivel in (4, 8):
        asi = body.asi or {}
        valido = (sum(asi.values()) == 2
                  and all(a in ("FUE", "DES", "CON", "INT", "SAB", "CAR")
                          and 1 <= v <= 2 for a, v in asi.items()))
        if not valido:
            raise HTTPException(400,
                "Nivel {}: mandá 'asi' con +2 puntos a repartir, ej "
                '{{"FUE": 2}} o {{"DES": 1, "CON": 1}}'.format(nuevo_nivel))
        atrs = dict(char.atributos)
        for a, v in asi.items():
            if atrs[a] + v > 20:
                raise HTTPException(400, f"{a} superaría 20")
            atrs[a] += v
        char.atributos = atrs
    char.nivel = nuevo_nivel
    caras = int(char.dado_golpe[1:])
    con = mod(char.atributos["CON"])
    if body.metodo == "tirar":
        d = roll(f"1{char.dado_golpe}")
        ganancia = max(1, d["dados"][0] + con)
        detalle = {"metodo": "tirar", "dado": d["dados"][0]}
    else:
        ganancia = max(1, (caras // 2 + 1) + con)
        detalle = {"metodo": "fijo", "valor": caras // 2 + 1}
    # PG extra por rasgos: enano de las colinas y linaje dracónico
    if "colinas" in (char.raza or "") or char.subclase == "linaje_draconico":
        ganancia += 1
    char.pg_max += ganancia
    char.pg_actual += ganancia
    char.dados_golpe_disp = min(char.nivel, char.dados_golpe_disp + 1)

    # recursos de clase del nuevo nivel (usos gastados se preservan)
    from engine.content import recursos_clase_iniciales
    nuevos_rec = recursos_clase_iniciales(char.clase, char.nivel,
                                          mod(char.atributos["CAR"]))
    viejos_rec = char.recursos_clase or {}
    for nombre, rec in nuevos_rec.items():
        if nombre in viejos_rec:
            if "usados" in rec:
                rec["usados"] = min(viejos_rec[nombre].get("usados", 0),
                                    rec["max"])
            if "pool" in rec:
                gastado = viejos_rec[nombre].get("pool_max", 0) - \
                    viejos_rec[nombre].get("pool", 0)
                rec["pool"] = max(0, rec["pool_max"] - gastado)
    char.recursos_clase = nuevos_rec

    # recalcular slots preservando los gastados
    nuevos = slots_iniciales(char.clase, char.nivel)
    for nv, s in nuevos.items():
        usados_previos = char.slots.get(nv, {}).get("usados", 0)
        s["usados"] = min(usados_previos, s["max"])
    char.slots = nuevos

    _msg(db, campaign_id, "sistema", "Sistema",
         f"⭐ {char.nombre} sube a nivel {char.nivel} (+{ganancia} PG máx).")
    _roll(db, campaign_id, {"tipo": "subida_nivel", "nivel": char.nivel,
                            "pg_ganados": ganancia, **detalle}, char.id)
    await db.commit()
    return {"nivel": char.nivel, "pg_ganados": ganancia,
            "pg_max": char.pg_max, "slots": char.slots, **detalle}


# ================================================================ estado

@router.get("/state")
async def estado_mundo(campaign_id: int,
                       player: Player = Depends(jugador_actual),
                       db: AsyncSession = Depends(get_db)):
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    camp = await db.get(Campaign, campaign_id)
    quests = (await db.execute(select(Quest).where(
        Quest.campaign_id == campaign_id))).scalars().all()
    npcs = (await db.execute(select(NPC).where(
        NPC.campaign_id == campaign_id, NPC.tipo == "personaje"))).scalars().all()
    cons = (await db.execute(select(PendingConsequence).where(
        PendingConsequence.campaign_id == campaign_id,
        PendingConsequence.resuelta == False))).scalars().all()  # noqa: E712
    return {
        "estado": camp.estado, "ubicacion": camp.ubicacion_actual,
        "tiempo_juego_min": camp.tiempo_juego_min,
        "resumen": camp.resumen_actual,
        "quests": [{"id": q.id, "titulo": q.titulo, "descripcion": q.descripcion,
                    "estado": q.estado, "principal": q.principal,
                    "npc_origen_id": q.npc_origen_id} for q in quests],
        "npcs_conocidos": [{"id": n.id, "nombre": n.nombre, "rol": n.rol,
                            "actitud": n.actitud, "en_escena": n.en_escena}
                           for n in npcs],
        "consecuencias_pendientes": len(cons),
    }
