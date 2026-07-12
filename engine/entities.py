"""Entidades puras del motor de reglas.

Son dataclasses sin dependencia de SQLAlchemy ni async. La capa de API se
encarga de hidratar estas entidades desde la DB antes de llamar al motor,
y de persistir los cambios después. Así el motor es 100% testeable en aislamiento.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Arma:
    nombre: str
    dado_danio: str                 # "1d8"
    tipo_danio: str                 # "cortante" | "perforante" | "contundente"
    categoria: str                  # "simple" | "marcial"
    finura: bool = False
    distancia: bool = False         # arma de ataque a distancia
    dos_manos: Optional[str] = None  # dado alternativo a dos manos, ej "1d10"
    dos_manos_fijo: bool = False     # arma inherentemente a dos manos (mandoble)
    arrojadiza: bool = False
    alcance_m: Optional[int] = None
    ligera: bool = False             # apta para combate con dos armas


@dataclass
class Armadura:
    nombre: str
    categoria: str                  # "ligera" | "media" | "pesada"
    ca_base: int
    des_max: Optional[int] = None   # None = sin límite; 2 para media; 0 para pesada


@dataclass
class SpellState:
    # slots: {"1": {"usados": 0, "max": 2}, ...}
    slots: dict = field(default_factory=dict)
    conocidos: list[str] = field(default_factory=list)
    preparados: list[str] = field(default_factory=list)
    concentracion_activa: Optional[dict] = None  # {"hechizo": str, "desde_ronda": int}


@dataclass
class Criatura:
    """Base común para PJs y NPCs: todo lo que el motor necesita para resolver."""
    id: str
    nombre: str
    nivel: int
    atributos: dict                 # {"FUE": 16, "DES": 12, ...}
    pg_actual: int
    pg_max: int
    velocidad_m: int = 9
    tipo_criatura: Optional[str] = None   # "no_muerto" | "infernal" | "Undead"...
    # competencias: {"habilidades": [...], "salvaciones": ["FUE"], "armas": ["simple"],
    #                "armaduras": ["ligera"]}
    competencias: dict = field(default_factory=lambda: {
        "habilidades": [], "salvaciones": [], "armas": [], "armaduras": [],
    })
    condiciones: list[dict] = field(default_factory=list)
    armadura: Optional[Armadura] = None
    escudo: bool = False
    ca_fija: Optional[int] = None   # para monstruos con CA de stat block
    ca_alternativa: Optional[str] = None   # "barbaro" (10+DES+CON) | "monje" (10+DES+SAB)
    estilo_combate: Optional[str] = None   # "defensa" | "duelo" | "arqueria"
    nivel_furtivo: int = 0          # pícaro: dados de ataque furtivo disponibles
    crit_min: int = 20              # Campeón nv3: crítico con 19-20
    subclase: Optional[str] = None
    resistencias: list = field(default_factory=list)  # tipos de daño a mitad
    spell_state: Optional[SpellState] = None
    dados_golpe_disp: int = 0
    dado_golpe: str = "d8"          # "d6" | "d8" | "d10" | "d12"
    bono_iniciativa: int = 0        # dotes/rasgos que suman a la iniciativa
    # salvaciones de muerte (solo PJs)
    muerte_exitos: int = 0
    muerte_fallos: int = 0
    vivo: bool = True

    def tiene_condicion(self, tipo: str) -> bool:
        return any(c.get("tipo") == tipo for c in self.condiciones)

    def quitar_condicion(self, tipo: str) -> None:
        self.condiciones = [c for c in self.condiciones if c.get("tipo") != tipo]
