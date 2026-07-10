"""Modelos de base de datos.

JSON se usa para estructuras internas (atributos, slots, condiciones, inventario)
— funciona nativo tanto en SQLite como en Postgres.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _ahora():
    return datetime.now(timezone.utc)


def _codigo_invitacion():
    return secrets.token_urlsafe(8)


def _token_jugador():
    return secrets.token_urlsafe(24)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    estado: Mapped[str] = mapped_column(String(20), default="exploracion")
    resumen_actual: Mapped[str] = mapped_column(Text, default="")
    tiempo_juego_min: Mapped[int] = mapped_column(Integer, default=0)
    ubicacion_actual: Mapped[str] = mapped_column(String(200), default="")
    invite_code: Mapped[str] = mapped_column(String(20), unique=True,
                                             default=_codigo_invitacion)
    combate: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Combat.to_dict()
    narrando: Mapped[bool] = mapped_column(Boolean, default=False)
    ultimo_descanso_largo_min: Mapped[int] = mapped_column(Integer, default=-10_000)
    creada: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    players: Mapped[list["Player"]] = relationship(back_populates="campaign")
    characters: Mapped[list["Character"]] = relationship(back_populates="campaign")


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    nombre: Mapped[str] = mapped_column(String(80))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True,
                                       default=_token_jugador)

    campaign: Mapped[Campaign] = relationship(back_populates="players")
    character: Mapped["Character | None"] = relationship(back_populates="player",
                                                         uselist=False)


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    nombre: Mapped[str] = mapped_column(String(80))
    raza: Mapped[str] = mapped_column(String(40))
    clase: Mapped[str] = mapped_column(String(40))
    nivel: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)

    atributos: Mapped[dict] = mapped_column(JSON)     # {"FUE": 16, ...}
    pg_actual: Mapped[int] = mapped_column(Integer)
    pg_max: Mapped[int] = mapped_column(Integer)
    velocidad_m: Mapped[int] = mapped_column(Integer, default=9)
    dado_golpe: Mapped[str] = mapped_column(String(4))
    dados_golpe_disp: Mapped[int] = mapped_column(Integer, default=1)

    competencias: Mapped[dict] = mapped_column(JSON, default=dict)
    condiciones: Mapped[list] = mapped_column(JSON, default=list)

    armadura: Mapped[str | None] = mapped_column(String(40), nullable=True)
    escudo: Mapped[bool] = mapped_column(Boolean, default=False)
    arma_equipada: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # inventario: [{"nombre": "antorcha", "cantidad": 3, "props": {...}}]
    inventario: Mapped[list] = mapped_column(JSON, default=list)
    monedas: Mapped[dict] = mapped_column(JSON, default=lambda: {"mo": 0, "mp": 0, "mc": 0})

    # magia
    slots: Mapped[dict] = mapped_column(JSON, default=dict)
    conocidos: Mapped[list] = mapped_column(JSON, default=list)
    preparados: Mapped[list] = mapped_column(JSON, default=list)
    concentracion: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    muerte_exitos: Mapped[int] = mapped_column(Integer, default=0)
    muerte_fallos: Mapped[int] = mapped_column(Integer, default=0)
    vivo: Mapped[bool] = mapped_column(Boolean, default=True)

    campaign: Mapped[Campaign] = relationship(back_populates="characters")
    player: Mapped[Player] = relationship(back_populates="character")


class NPC(Base):
    """NPCs narrativos Y monstruos de combate."""
    __tablename__ = "npcs"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    nombre: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[str] = mapped_column(String(20), default="personaje")  # personaje|monstruo
    plantilla: Mapped[str | None] = mapped_column(String(40), nullable=True)  # "goblin"
    rol: Mapped[str] = mapped_column(String(120), default="")
    personalidad: Mapped[str] = mapped_column(Text, default="")
    motivacion: Mapped[str] = mapped_column(Text, default="")
    actitud: Mapped[str] = mapped_column(String(30), default="neutral")
    sabe_del_grupo: Mapped[list] = mapped_column(JSON, default=list)
    promesas: Mapped[str] = mapped_column(Text, default="")
    secretos: Mapped[str] = mapped_column(Text, default="")
    # stats de combate (solo si puede pelear)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pg_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condiciones: Mapped[list] = mapped_column(JSON, default=list)
    en_escena: Mapped[bool] = mapped_column(Boolean, default=False)
    vivo: Mapped[bool] = mapped_column(Boolean, default=True)


class Quest(Base):
    __tablename__ = "quests"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    titulo: Mapped[str] = mapped_column(String(160))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(20), default="activa")  # activa|completada|fallida
    principal: Mapped[bool] = mapped_column(Boolean, default=False)
    npc_origen_id: Mapped[int | None] = mapped_column(ForeignKey("npcs.id"),
                                                      nullable=True)


class PendingConsequence(Base):
    __tablename__ = "pending_consequences"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    evento: Mapped[str] = mapped_column(Text)
    efecto: Mapped[str] = mapped_column(Text)
    activacion: Mapped[str] = mapped_column(Text)
    resuelta: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    autor: Mapped[str] = mapped_column(String(20))  # jugador|dm|sistema
    autor_nombre: Mapped[str] = mapped_column(String(80), default="")
    contenido: Mapped[str] = mapped_column(Text)
    resumido: Mapped[bool] = mapped_column(Boolean, default=False)
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class Roll(Base):
    """Auditoría de toda resolución del motor."""
    __tablename__ = "rolls"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"),
                                                     nullable=True)
    resolucion: Mapped[dict] = mapped_column(JSON)  # el dict completo del motor
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
