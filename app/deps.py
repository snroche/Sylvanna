"""Dependencias compartidas de FastAPI."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import Player


async def jugador_actual(
    x_player_token: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Player:
    res = await db.execute(select(Player).where(Player.token == x_player_token))
    player = res.scalar_one_or_none()
    if player is None:
        raise HTTPException(401, "Token de jugador inválido")
    return player
