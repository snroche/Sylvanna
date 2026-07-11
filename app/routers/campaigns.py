from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import jugador_actual
from ..models import Campaign, Character, Message, Player

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CrearCampania(BaseModel):
    nombre: str
    nombre_jugador: str
    descripcion: str = ""    # ambientación: "transcurre en Baldur's Gate..."


class Unirse(BaseModel):
    invite_code: str
    nombre_jugador: str


@router.post("")
async def crear_campania(body: CrearCampania, db: AsyncSession = Depends(get_db)):
    camp = Campaign(nombre=body.nombre, descripcion=body.descripcion[:2000])
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


@router.get("/me")
async def quien_soy(player: Player = Depends(jugador_actual),
                    db: AsyncSession = Depends(get_db)):
    """Retomar campaña con solo el token del jugador."""
    camp = await db.get(Campaign, player.campaign_id)
    res = await db.execute(select(Character)
                           .where(Character.player_id == player.id)
                           .order_by(Character.id.desc()))
    chars = res.scalars().all()
    vivo = next((c for c in chars if c.vivo), None)
    return {"campaign_id": camp.id, "campaign_nombre": camp.nombre,
            "player_id": player.id, "player_nombre": player.nombre,
            "invite_code": camp.invite_code,
            "character_id": vivo.id if vivo else None,
            "personaje_muerto": bool(chars) and vivo is None}


@router.get("/{campaign_id}")
async def ver_campania(campaign_id: int, player: Player = Depends(jugador_actual),
                       db: AsyncSession = Depends(get_db)):
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    camp = await db.get(Campaign, campaign_id)

    # timeout de turno: los clientes pollean, así que este es el "reloj"
    from .actions import chequear_timeout_turno
    await chequear_timeout_turno(db, camp)

    res = await db.execute(
        select(Character).where(Character.campaign_id == campaign_id))
    chars = res.scalars().all()

    from ..models import NPC
    res = await db.execute(select(NPC).where(
        NPC.campaign_id == campaign_id, NPC.en_escena == True))  # noqa: E712
    npcs = res.scalars().all()

    def salud(n):
        maximo = (n.stats or {}).get("pg")
        if n.pg_actual is None or not maximo:
            return None
        r = n.pg_actual / maximo
        if n.pg_actual == 0:
            return "caído"
        if r >= 1:
            return "ileso"
        if r >= 0.66:
            return "magullado"
        if r >= 0.33:
            return "herido"
        return "malherido"

    return {
        "id": camp.id, "nombre": camp.nombre, "estado": camp.estado,
        "ubicacion": camp.ubicacion_actual,
        "tiempo_juego_min": camp.tiempo_juego_min,
        "narrando": camp.narrando,
        "ultimo_mensaje_id": (await db.execute(
            select(func.max(Message.id)).where(
                Message.campaign_id == camp.id))).scalar() or 0,
        "escribiendo": [n for n, ts in (camp.typing or {}).items()
                        if __import__("time").time() - ts < 6],
        "combate": camp.combate,
        "personajes": [
            {"id": c.id, "nombre": c.nombre, "clase": c.clase, "nivel": c.nivel,
             "raza": c.raza, "alineamiento": c.alineamiento,
             "pg_actual": c.pg_actual, "pg_max": c.pg_max, "vivo": c.vivo,
             "condiciones": [x["tipo"] for x in c.condiciones],
             "player_id": c.player_id}
            for c in chars
        ],
        "npcs_en_escena": [
            {"id": n.id, "nombre": n.nombre, "tipo": n.tipo,
             "actitud": n.actitud, "salud": salud(n), "vivo": n.vivo}
            for n in npcs
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
