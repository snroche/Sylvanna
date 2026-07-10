"""Motor de reglas D&D 5e — puro, sin dependencias de DB, LLM ni async."""
from .combat import CampaignState, Combat, validar_transicion
from .dice import d20, roll
from .entities import Arma, Armadura, Criatura, SpellState
from .rules import (
    aplicar_danio,
    ataque_magico,
    bc,
    calcular_ca,
    cd_salvacion_magica,
    check_concentracion,
    curar,
    descanso_corto,
    descanso_largo,
    gastar_slot,
    iniciativa,
    mod,
    nivel_por_xp,
    puede_lanzar,
    resolver_ataque,
    salvacion_muerte,
    tirada_habilidad,
    tirada_salvacion,
)
