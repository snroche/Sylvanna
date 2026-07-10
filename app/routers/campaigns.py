from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import jugador_actual
from ..models import Campaign, Character, Message, Player

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CrearCampania(BaseModel):
    nombre: str
    nombre_jugador: str


class Unirse(BaseModel):
    invite_code: str
    nombre_jugador: str


@router.post("")
async def crear_campania(body: CrearCampania, db: AsyncSession = Depends(get_db)):
    camp = Campaign(nombre=body.nombre)
    db.add(camp)
    await db.flush()
    player = Player(campaign_id=camp.id, nombre=body.nombre_jugador)
    db.add(player)
    await db.commit()
    return {"campaign_id": camp.id, "invite_code": camp.invite_code,
            "player_token": player.token, "player_id": player.id}


@router.post("/join")
async def unirse(body: Unirse, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Campaign).where(Campaign.invite_code == body.invite_code))
    camp = res.scalar_one_or_none()
    if camp is None:
        raise HTTPException(404, "Código de invitación inválido")
    player = Player(campaign_id=camp.id, nombre=body.nombre_jugador)
    db.add(player)
    await db.commit()
    return {"campaign_id": camp.id, "player_token": player.token,
            "player_id": player.id}


@router.get("/{campaign_id}")
async def ver_campania(campaign_id: int, player: Player = Depends(jugador_actual),
                       db: AsyncSession = Depends(get_db)):
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    camp = await db.get(Campaign, campaign_id)
    res = await db.execute(
        select(Character).where(Character.campaign_id == campaign_id))
    chars = res.scalars().all()
    return {
        "id": camp.id, "nombre": camp.nombre, "estado": camp.estado,
        "ubicacion": camp.ubicacion_actual,
        "combate": camp.combate,
        "personajes": [
            {"id": c.id, "nombre": c.nombre, "clase": c.clase, "nivel": c.nivel,
             "pg_actual": c.pg_actual, "pg_max": c.pg_max, "vivo": c.vivo,
             "player_id": c.player_id}
            for c in chars
        ],
    }


@router.get("/{campaign_id}/messages")
async def mensajes(campaign_id: int, since: int = 0,
                   player: Player = Depends(jugador_actual),
                   db: AsyncSession = Depends(get_db)):
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    res = await db.execute(
        select(Message)
        .where(Message.campaign_id == campaign_id, Message.id > since)
        .order_by(Message.id).limit(100))
    return [{"id": m.id, "autor": m.autor, "autor_nombre": m.autor_nombre,
             "contenido": m.contenido} for m in res.scalars().all()]
