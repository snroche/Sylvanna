"""Puente DB ↔ motor.

hidratar_*: modelo SQLAlchemy → Criatura del motor.
persistir_*: vuelca las mutaciones del motor de vuelta al modelo.
"""
from __future__ import annotations

from engine.content import ARMADURAS, MONSTRUOS
from engine.entities import Criatura, SpellState

from .models import NPC, Character


def hidratar_personaje(c: Character) -> Criatura:
    return Criatura(
        id=f"pj_{c.id}",
        nombre=c.nombre,
        nivel=c.nivel,
        atributos=dict(c.atributos),
        pg_actual=c.pg_actual,
        pg_max=c.pg_max,
        velocidad_m=c.velocidad_m,
        competencias=dict(c.competencias),
        condiciones=[dict(x) for x in c.condiciones],
        armadura=ARMADURAS.get(c.armadura) if c.armadura else None,
        escudo=c.escudo,
        spell_state=SpellState(
            slots={k: dict(v) for k, v in c.slots.items()},
            conocidos=list(c.conocidos),
            preparados=list(c.preparados),
            concentracion_activa=dict(c.concentracion) if c.concentracion else None,
        ) if c.slots or c.conocidos else None,
        dados_golpe_disp=c.dados_golpe_disp,
        dado_golpe=c.dado_golpe,
        muerte_exitos=c.muerte_exitos,
        muerte_fallos=c.muerte_fallos,
        vivo=c.vivo,
    )


def persistir_personaje(cr: Criatura, c: Character) -> None:
    c.pg_actual = cr.pg_actual
    c.condiciones = cr.condiciones
    c.dados_golpe_disp = cr.dados_golpe_disp
    c.muerte_exitos = cr.muerte_exitos
    c.muerte_fallos = cr.muerte_fallos
    c.vivo = cr.vivo
    if cr.spell_state:
        c.slots = cr.spell_state.slots
        c.concentracion = cr.spell_state.concentracion_activa


def hidratar_npc(n: NPC) -> Criatura:
    stats = n.stats or (MONSTRUOS.get(n.plantilla, {}) if n.plantilla else {})
    return Criatura(
        id=f"npc_{n.id}",
        nombre=n.nombre,
        nivel=1,
        atributos=stats.get("atributos",
                            {"FUE": 10, "DES": 10, "CON": 10,
                             "INT": 10, "SAB": 10, "CAR": 10}),
        pg_actual=n.pg_actual if n.pg_actual is not None else stats.get("pg", 10),
        pg_max=stats.get("pg", 10),
        velocidad_m=stats.get("velocidad_m", 9),
        ca_fija=stats.get("ca_fija"),
        condiciones=[dict(x) for x in n.condiciones],
        vivo=n.vivo,
    )


def persistir_npc(cr: Criatura, n: NPC) -> None:
    n.pg_actual = cr.pg_actual
    n.condiciones = cr.condiciones
    if cr.pg_actual == 0:
        n.vivo = False
        n.en_escena = False
