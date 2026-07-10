"""Aplica los efectos declarados por el narrador (contrato JSON) a la DB.

Cada efecto se valida antes de aplicarse. Fallos individuales no rompen
el resto: se registran y se sigue. El LLM no tiene autoridad sobre PG,
slots ni recursos de PJs — esos campos no existen en el contrato.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.content import MONSTRUOS

from .models import NPC, Campaign, Character, PendingConsequence, Quest

XP_NARRATIVO_TOPE_POR_NIVEL = 50   # tope: 50 × nivel_promedio por evento
ACTITUDES = {"amistoso", "neutral", "desconfiado", "hostil"}


async def aplicar_efectos(db: AsyncSession, camp: Campaign,
                          efectos: dict) -> dict:
    """Devuelve un log de qué se aplicó y qué se rechazó."""
    log = {"aplicados": [], "rechazados": [], "inicia_combate": None}
    if not efectos:
        return log

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
