"""Puente DB ↔ motor.

hidratar_*: modelo SQLAlchemy → Criatura del motor.
persistir_*: vuelca las mutaciones del motor de vuelta al modelo.
"""
from __future__ import annotations

from engine.content import ARMADURAS, MONSTRUOS
from engine.entities import Criatura, SpellState

from .models import NPC, Character


def hidratar_personaje(c: Character) -> Criatura:
    from engine.content import resistencias_de_raza
    nivel_furtivo = (c.nivel + 1) // 2 if c.clase == "picaro" else 0
    ca_alt = c.clase if c.clase in ("barbaro", "monje") else None
    if c.clase == "hechicero" and c.subclase == "linaje_draconico":
        ca_alt = "draconico"
    crit_min = 19 if (c.clase == "guerrero" and c.subclase == "campeon"
                      and c.nivel >= 3) else 20
    # Furia del bárbaro: resistencia a daño físico mientras dura
    resist = list(resistencias_de_raza(c.raza))
    if any(x.get("tipo") == "furia" for x in c.condiciones):
        for t in ("contundente", "perforante", "cortante"):
            if t not in resist:
                resist.append(t)
    # Forma Salvaje (druida): la CA la fija el stat block de la bestia
    forma = (c.recursos_clase or {}).get("_forma_salvaje")
    ca_fija = forma.get("ca_fija") if forma else None
    # competencias + elecciones de clase (invocaciones que dan competencias,
    # y expertise de pícaro/bardo → doble competencia en tiradas de habilidad)
    from engine.content import INVOCACIONES
    opc = c.opciones_clase or {}
    competencias = {k: list(v) if isinstance(v, list) else v
                    for k, v in (c.competencias or {}).items()}
    habs = list(competencias.get("habilidades", []))
    for inv in opc.get("invocaciones", []):
        for h in INVOCACIONES.get(inv, {}).get("otorga_competencias", []):
            if h not in habs:
                habs.append(h)
    competencias["habilidades"] = habs
    competencias["expertise"] = list(opc.get("expertise", []))
    # dotes: bono de iniciativa (Alerta), etc.
    from engine.content import efectos_feats
    ef_feats = efectos_feats(c.feats or [])
    bono_ini = ef_feats["bono_iniciativa"]
    # Swashbuckler (pícaro): Audacia Temeraria suma el mod de CAR a la iniciativa
    if c.clase == "picaro" and c.subclase == "swashbuckler":
        from engine.rules import mod as _mod
        bono_ini += _mod(c.atributos["CAR"])
    return Criatura(
        id=f"pj_{c.id}",
        nombre=c.nombre,
        nivel=c.nivel,
        atributos=dict(c.atributos),
        pg_actual=c.pg_actual,
        pg_max=c.pg_max,
        velocidad_m=c.velocidad_m,
        competencias=competencias,
        condiciones=[dict(x) for x in c.condiciones],
        armadura=ARMADURAS.get(c.armadura) if c.armadura else None,
        escudo=c.escudo,
        ca_fija=ca_fija,
        ca_alternativa=ca_alt,
        estilo_combate=c.estilo_combate,
        nivel_furtivo=nivel_furtivo,
        crit_min=crit_min,
        subclase=c.subclase,
        resistencias=resist,
        spell_state=SpellState(
            slots={k: dict(v) for k, v in c.slots.items()},
            conocidos=list(c.conocidos),
            preparados=list(c.preparados),
            concentracion_activa=dict(c.concentracion) if c.concentracion else None,
        ) if c.slots or c.conocidos else None,
        dados_golpe_disp=c.dados_golpe_disp,
        dado_golpe=c.dado_golpe,
        bono_iniciativa=bono_ini,
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
    _resist = list((n.stats or {}).get("resistencias", []))
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
        resistencias=_resist,
        tipo_criatura=stats.get("tipo_criatura"),
        vivo=n.vivo,
    )


def persistir_npc(cr: Criatura, n: NPC) -> None:
    n.pg_actual = cr.pg_actual
    n.condiciones = cr.condiciones
    if cr.pg_actual == 0:
        n.vivo = False
        n.en_escena = False
