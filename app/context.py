"""Pipeline de contexto para el narrador.

Presupuesto objetivo ~6-8k tokens de entrada:
  system prompt (fijo) + resumen rodante + estado estructurado (DB)
  + resultado mecánico + últimos 12 mensajes.

Los datos duros (NPCs, quests, consecuencias) SIEMPRE salen de la DB,
nunca de la memoria del modelo.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import (NPC, Campaign, Character, Message, PendingConsequence,
                     Quest)

MENSAJES_RECIENTES = 12
# umbral configurable por env RESUMIR_CADA (default 40). Nota: NO regenera
# la crónica entera cada vez: integra el lote nuevo al resumen existente.
MAX_PALABRAS_RESUMEN = 600


def _umbral() -> int:
    """Configurable por env RESUMIR_CADA (default 40). El resumen NO se
    regenera entero: integra el lote nuevo a la crónica existente."""
    return get_settings().resumir_cada


async def construir_contexto(db: AsyncSession, camp: Campaign) -> str:
    """Arma el bloque de contexto completo para una llamada al narrador."""
    partes: list[str] = []

    # --- resumen rodante
    partes.append(f"## CAMPAÑA: {camp.nombre}")
    if camp.descripcion:
        partes.append(f"## AMBIENTACIÓN (respetarla siempre)\n{camp.descripcion}")
    partes.append(f"Estado: {camp.estado}. "
                  f"Ubicación: {camp.ubicacion_actual or 'sin definir'}. "
                  f"Tiempo de juego: {camp.tiempo_juego_min} min.")
    if camp.resumen_actual:
        partes.append(f"## RESUMEN DE LO OCURRIDO\n{camp.resumen_actual}")

    # --- grupo
    res = await db.execute(select(Character).where(
        Character.campaign_id == camp.id))
    chars = res.scalars().all()
    lineas = []
    for c in chars:
        estado = "MUERTO" if not c.vivo else \
            f"{c.pg_actual}/{c.pg_max} PG" + \
            (f", condiciones: {[x['tipo'] for x in c.condiciones]}"
             if c.condiciones else "")
        sub = f"/{c.subclase}" if c.subclase else ""
        lineas.append(f"- {c.nombre} ({c.raza} {c.clase}{sub} nv{c.nivel}): {estado}")
    partes.append("## GRUPO\n" + "\n".join(lineas))

    # --- NPCs en escena (ficha completa solo de los presentes)
    res = await db.execute(select(NPC).where(
        NPC.campaign_id == camp.id, NPC.en_escena == True))  # noqa: E712
    npcs = res.scalars().all()
    if npcs:
        lineas = []
        for n in npcs:
            lineas.append(
                f"- [{n.id}] {n.nombre} ({n.rol or n.tipo}) | actitud: {n.actitud}"
                + (f" | personalidad: {n.personalidad}" if n.personalidad else "")
                + (f" | motivación: {n.motivacion}" if n.motivacion else "")
                + (f" | sabe del grupo: {n.sabe_del_grupo}" if n.sabe_del_grupo else "")
                + (f" | secretos (NO revelar directamente): {n.secretos}"
                   if n.secretos else ""))
        partes.append("## NPCs EN ESCENA\n" + "\n".join(lineas))

    # --- quests
    res = await db.execute(select(Quest).where(
        Quest.campaign_id == camp.id, Quest.estado == "activa"))
    quests = res.scalars().all()
    if quests:
        partes.append("## MISIONES ACTIVAS\n" + "\n".join(
            f"- [{q.id}] {'(PRINCIPAL) ' if q.principal else ''}{q.titulo}: "
            f"{q.descripcion}" for q in quests))

    # --- consecuencias pendientes
    res = await db.execute(select(PendingConsequence).where(
        PendingConsequence.campaign_id == camp.id,
        PendingConsequence.resuelta == False))  # noqa: E712
    cons = res.scalars().all()
    if cons:
        partes.append("## CONSECUENCIAS PENDIENTES (honrarlas cuando corresponda)\n"
                      + "\n".join(f"- [{c.id}] {c.evento} → {c.efecto} "
                                  f"(se activa: {c.activacion})" for c in cons))

    # --- mensajes recientes
    res = await db.execute(select(Message)
                           .where(Message.campaign_id == camp.id)
                           .order_by(Message.id.desc())
                           .limit(MENSAJES_RECIENTES))
    recientes = list(reversed(res.scalars().all()))
    if recientes:
        def _linea(m):
            if m.autor == "party":
                return (f"[charla entre jugadores — NO respondas por ellos] "
                        f"{m.autor_nombre}: {m.contenido[:300]}")
            return f"[{m.autor_nombre or m.autor}] {m.contenido[:400]}"
        partes.append("## ÚLTIMOS MENSAJES\n" + "\n".join(
            _linea(m) for m in recientes))

    return "\n\n".join(partes)


async def actualizar_resumen_si_corresponde(db: AsyncSession,
                                            camp: Campaign) -> bool:
    """Resumen rodante: cada _umbral() mensajes sin resumir, reescribe
    el resumen integrando lo nuevo. Devuelve True si resumió."""
    res = await db.execute(select(Message).where(
        Message.campaign_id == camp.id,
        Message.resumido == False).order_by(Message.id))  # noqa: E712
    pendientes = res.scalars().all()
    if len(pendientes) < _umbral():
        return False

    lote = pendientes[:_umbral()]
    crudos = "\n".join(f"[{m.autor_nombre or m.autor}] {m.contenido[:300]}"
                       for m in lote)
    prompt = (
        f"Resumen actual de una campaña de D&D:\n"
        f"{camp.resumen_actual or '(vacío, campaña nueva)'}\n\n"
        f"Nuevos eventos (mensajes crudos):\n{crudos}\n\n"
        f"Reescribí el resumen COMPLETO integrando los nuevos eventos, en español, "
        f"máximo {MAX_PALABRAS_RESUMEN} palabras. Priorizá: misiones y quién las dio, "
        f"promesas hechas, enemigos creados, decisiones importantes, lugares. "
        f"Descartá: descripciones ambientales y combates sin consecuencia. "
        f"Respondé SOLO con el resumen, sin preámbulo.")

    from .narrator import NarradorError, completar  # import tardío (ciclo)
    s = get_settings()
    modelo = s.openrouter_model_summarizer or s.modelos[0]
    try:
        nuevo = await completar(prompt, modelo=modelo, max_tokens=900,
                                reintentos=0)
    except NarradorError as e:
        # sin drama: los mensajes quedan sin resumir y se reintenta la próxima
        print(f"[resumen] pospuesto: {e}")
        return False
    if nuevo:
        camp.resumen_actual = nuevo.strip()
        for m in lote:
            m.resumido = True
        return True
    return False
