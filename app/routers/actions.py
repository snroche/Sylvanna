"""Acciones de juego: narrativa, habilidades, combate.

Flujo: validar → hidratar → motor → persistir → narrar → guardar mensajes.
Los turnos de NPC se resuelven automáticamente con IA simple del servidor
(atacar al PJ con menos PG); en el paso 3 el LLM decidirá las acciones.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.combat import Combat
from engine.content import ARMAS, MONSTRUOS
from engine.rules import (check_concentracion, salvacion_muerte,
                          tirada_habilidad, resolver_ataque)

from ..db import get_db
from ..deps import jugador_actual
from ..hydration import (hidratar_npc, hidratar_personaje,
                         persistir_npc, persistir_personaje)
from ..models import NPC, Campaign, Character, Message, Player, Roll
from ..narrator import narrar

router = APIRouter(prefix="/api/campaigns/{campaign_id}", tags=["actions"])


# ---------------------------------------------------------------- helpers

async def _mi_personaje(campaign_id: int, player: Player,
                        db: AsyncSession) -> Character:
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    res = await db.execute(select(Character).where(Character.player_id == player.id))
    c = res.scalar_one_or_none()
    if c is None:
        raise HTTPException(400, "Todavía no creaste un personaje")
    if not c.vivo:
        raise HTTPException(400, "Tu personaje está muerto")
    return c


async def _guardar(db, campaign_id, autor, autor_nombre, contenido,
                   character_id=None, resolucion=None):
    db.add(Message(campaign_id=campaign_id, autor=autor,
                   autor_nombre=autor_nombre, contenido=contenido))
    if resolucion is not None:
        db.add(Roll(campaign_id=campaign_id, character_id=character_id,
                    resolucion=resolucion))


def _contexto_simple(camp: Campaign, chars: list[Character]) -> str:
    pjs = "; ".join(f"{c.nombre} ({c.clase} nv{c.nivel}, {c.pg_actual}/{c.pg_max} PG)"
                    for c in chars)
    return (f"Campaña: {camp.nombre}. Ubicación: {camp.ubicacion_actual or 'inicio'}. "
            f"Estado: {camp.estado}.\nPersonajes: {pjs}\n"
            f"Resumen previo: {camp.resumen_actual or '(campaña recién iniciada)'}")


# ---------------------------------------------------------------- narrativa

class AccionNarrativa(BaseModel):
    texto: str


@router.post("/say")
async def accion_narrativa(campaign_id: int, body: AccionNarrativa,
                           player: Player = Depends(jugador_actual),
                           db: AsyncSession = Depends(get_db)):
    """El jugador habla o declara una acción sin tirada."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    res = await db.execute(select(Character).where(Character.campaign_id == campaign_id))
    chars = res.scalars().all()

    await _guardar(db, campaign_id, "jugador", char.nombre, body.texto)
    narracion = await narrar(_contexto_simple(camp, chars),
                             f"{char.nombre} dice/hace: {body.texto}")
    await _guardar(db, campaign_id, "dm", "DM", narracion)
    await db.commit()
    return {"narracion": narracion}


# ---------------------------------------------------------------- habilidad

class AccionHabilidad(BaseModel):
    habilidad: str
    cd: int = 12
    descripcion: str = ""


@router.post("/skill-check")
async def accion_habilidad(campaign_id: int, body: AccionHabilidad,
                           player: Player = Depends(jugador_actual),
                           db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    cr = hidratar_personaje(char)
    r = tirada_habilidad(cr, body.habilidad, body.cd)
    persistir_personaje(cr, char)

    detalle = (f"{char.nombre} intenta {body.habilidad}"
               f"{': ' + body.descripcion if body.descripcion else ''}. "
               f"Resultado del sistema: {json.dumps(r, ensure_ascii=False)}")
    await _guardar(db, campaign_id, "jugador", char.nombre,
                   f"[{body.habilidad}] {body.descripcion}",
                   char.id, r)
    res = await db.execute(select(Character).where(Character.campaign_id == campaign_id))
    narracion = await narrar(_contexto_simple(camp, res.scalars().all()), detalle)
    await _guardar(db, campaign_id, "dm", "DM", narracion)
    await db.commit()
    return {"resolucion": r, "narracion": narracion}


# ---------------------------------------------------------------- combate

class IniciarCombate(BaseModel):
    monstruos: list[str]  # ["goblin", "goblin", "orco"]


@router.post("/combat/start")
async def iniciar_combate(campaign_id: int, body: IniciarCombate,
                          player: Player = Depends(jugador_actual),
                          db: AsyncSession = Depends(get_db)):
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "Ya hay un combate activo")
    for m in body.monstruos:
        if m not in MONSTRUOS:
            raise HTTPException(400, f"Monstruo desconocido: {m}. "
                                     f"Opciones: {list(MONSTRUOS)}")

    # crear NPCs de combate
    npcs = []
    contador: dict[str, int] = {}
    for plantilla in body.monstruos:
        contador[plantilla] = contador.get(plantilla, 0) + 1
        info = MONSTRUOS[plantilla]
        n = NPC(campaign_id=campaign_id, tipo="monstruo", plantilla=plantilla,
                nombre=f"{info['nombre']} {contador[plantilla]}",
                stats=info, pg_actual=info["pg"], en_escena=True, actitud="hostil")
        db.add(n)
        npcs.append(n)
    await db.flush()

    res = await db.execute(select(Character).where(
        Character.campaign_id == campaign_id, Character.vivo == True))  # noqa: E712
    chars = res.scalars().all()
    if not chars:
        raise HTTPException(400, "No hay personajes vivos")

    combate = Combat.iniciar([hidratar_personaje(c) for c in chars],
                             [hidratar_npc(n) for n in npcs])
    camp.combate = combate.to_dict()
    camp.estado = "combate"

    orden_legible = [e["id"] for e in combate.orden]
    await _guardar(db, campaign_id, "sistema", "Sistema",
                   f"⚔️ Combate iniciado. Orden: {orden_legible}",
                   resolucion={"tipo": "inicio_combate",
                               "iniciativas": combate.tiradas_iniciativa})
    await db.commit()

    # si arranca un NPC, resolver sus turnos hasta que le toque a un PJ
    eventos_npc = await _resolver_turnos_npc(campaign_id, db)
    await db.commit()
    return {"orden": combate.orden,
            "iniciativas": combate.tiradas_iniciativa,
            "turnos_npc": eventos_npc,
            "combate": (await db.get(Campaign, campaign_id)).combate}


class Atacar(BaseModel):
    objetivo_npc_id: int
    dos_manos: bool = False


@router.post("/combat/attack")
async def atacar(campaign_id: int, body: Atacar,
                 player: Player = Depends(jugador_actual),
                 db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)

    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, f"No es tu turno. Turno actual: "
                                 f"{combate.turno_actual['id']}")
    if not char.arma_equipada:
        raise HTTPException(400, "No tenés arma equipada")

    npc = await db.get(NPC, body.objetivo_npc_id)
    if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
        raise HTTPException(404, "Objetivo inválido o ya está fuera de combate")

    cr_pj = hidratar_personaje(char)
    cr_npc = hidratar_npc(npc)
    r = resolver_ataque(cr_pj, cr_npc, ARMAS[char.arma_equipada],
                        dos_manos=body.dos_manos)
    persistir_personaje(cr_pj, char)
    persistir_npc(cr_npc, npc)
    await _guardar(db, campaign_id, "jugador", char.nombre,
                   f"[ataque] contra {npc.nombre}", char.id, r)

    if cr_npc.pg_actual == 0:
        combate.remover(f"npc_{npc.id}")

    fin = None
    if not combate.npcs_restantes():
        fin = "victoria"
        camp.estado = "exploracion"
        camp.combate = None
        combate.activo = False
    else:
        combate.avanzar_turno()

    camp.combate = combate.to_dict() if combate.activo else None
    await db.commit()

    eventos_npc = []
    if combate.activo:
        eventos_npc = await _resolver_turnos_npc(campaign_id, db)
        await db.commit()

    camp = await db.get(Campaign, campaign_id)

    # narración del intercambio completo
    res = await db.execute(select(Character).where(Character.campaign_id == campaign_id))
    detalle = (f"Ataque de {char.nombre} contra {npc.nombre}: "
               f"{json.dumps(r, ensure_ascii=False)}. "
               f"Turnos de enemigos: {json.dumps(eventos_npc, ensure_ascii=False)}. "
               f"{'¡Combate terminado: ' + fin + '!' if fin else ''}")
    narracion = await narrar(_contexto_simple(camp, res.scalars().all()), detalle)
    await _guardar(db, campaign_id, "dm", "DM", narracion)
    await db.commit()

    return {"resolucion": r, "turnos_npc": eventos_npc, "fin_combate": fin,
            "narracion": narracion, "combate": camp.combate}


async def _resolver_turnos_npc(campaign_id: int, db: AsyncSession) -> list[dict]:
    """Resuelve turnos de NPC consecutivos hasta que toque un PJ o termine.

    IA v1: el NPC ataca al PJ vivo con menos PG. Salvaciones de muerte de PJs
    caídos se tiran automáticamente al inicio de su turno.
    """
    camp = await db.get(Campaign, campaign_id)
    if not camp.combate:
        return []
    combate = Combat.from_dict(camp.combate)
    eventos: list[dict] = []

    for _ in range(30):  # tope de seguridad
        if not combate.activo:
            break
        actual = combate.turno_actual

        if actual["tipo"] == "pj":
            char = await db.get(Character, int(actual["id"].split("_")[1]))
            if char.pg_actual > 0:
                break  # le toca a un jugador consciente: cortamos y esperamos
            # PJ a 0: salvación de muerte automática y pasa turno
            cr = hidratar_personaje(char)
            r = salvacion_muerte(cr)
            persistir_personaje(cr, char)
            eventos.append({"actor": char.nombre, "salvacion_muerte": r})
            db.add(Roll(campaign_id=campaign_id, character_id=char.id, resolucion=r))
            if r["evento"] == "muerte":
                combate.remover(actual["id"])
                if not combate.pjs_restantes():
                    camp.estado = "exploracion"
                    camp.combate = None
                    eventos.append({"fin_combate": "derrota_total"})
                    return eventos
            else:
                combate.avanzar_turno()
            continue

        # turno de NPC
        npc = await db.get(NPC, int(actual["id"].split("_")[1]))
        res = await db.execute(select(Character).where(
            Character.campaign_id == campaign_id,
            Character.vivo == True, Character.pg_actual > 0))  # noqa: E712
        objetivos = res.scalars().all()
        if not objetivos:
            camp.estado = "exploracion"
            camp.combate = None
            eventos.append({"fin_combate": "derrota_total"})
            return eventos

        objetivo = min(objetivos, key=lambda c: c.pg_actual)
        arma_nombre = (npc.stats or {}).get("armas", ["garrote"])[0]
        arma = ARMAS.get(arma_nombre, ARMAS["garrote"])

        cr_npc = hidratar_npc(npc)
        cr_pj = hidratar_personaje(objetivo)
        r = resolver_ataque(cr_npc, cr_pj, arma)
        # check de concentración si corresponde
        if "requiere_check_concentracion" in r.get("efectos", []):
            conc = check_concentracion(cr_pj, r["danio"]["total_final"])
            eventos.append({"actor": objetivo.nombre, "concentracion": conc})
        persistir_personaje(cr_pj, objetivo)
        persistir_npc(cr_npc, npc)
        eventos.append({"actor": npc.nombre, "ataque": r,
                        "objetivo": objetivo.nombre})
        db.add(Roll(campaign_id=campaign_id, resolucion=r))
        combate.avanzar_turno()

    camp.combate = combate.to_dict() if combate.activo else None
    return eventos
