"""Contenido 5e hardcodeado para v1. Migrable a Open5e API más adelante.

Todo es data pura (dicts) para poder eventualmente moverlo a la DB o a JSON.
"""
from __future__ import annotations

from .entities import Arma, Armadura

# ---------------------------------------------------------------- armas

ARMAS: dict[str, Arma] = {
    "daga": Arma("daga", "1d4", "perforante", "simple", finura=True,
                 arrojadiza=True, alcance_m=6, ligera=True),
    "espada_corta": Arma("espada_corta", "1d6", "perforante", "marcial",
                         finura=True, ligera=True),
    "espada_larga": Arma("espada_larga", "1d8", "cortante", "marcial", dos_manos="1d10"),
    "hacha_de_mano": Arma("hacha_de_mano", "1d6", "cortante", "simple",
                          arrojadiza=True, alcance_m=6, ligera=True),
    "hacha_de_batalla": Arma("hacha_de_batalla", "1d8", "cortante", "marcial",
                             dos_manos="1d10"),
    "arco_corto": Arma("arco_corto", "1d6", "perforante", "simple",
                       distancia=True, alcance_m=24),
    "arco_largo": Arma("arco_largo", "1d8", "perforante", "marcial",
                       distancia=True, alcance_m=45),
    "ballesta_de_mano": Arma("ballesta_de_mano", "1d6", "perforante", "marcial",
                             distancia=True, alcance_m=9, ligera=True),
    "lanza": Arma("lanza", "1d6", "perforante", "simple", dos_manos="1d8",
                  arrojadiza=True, alcance_m=6),
    "mazo": Arma("mazo", "1d6", "contundente", "simple"),
    "mandoble": Arma("mandoble", "2d6", "cortante", "marcial",
                     dos_manos_fijo=True),
    "hacha_grande": Arma("hacha_grande", "1d12", "cortante", "marcial",
                         dos_manos_fijo=True),
    "baston": Arma("baston", "1d6", "contundente", "simple", dos_manos="1d8"),
    "cimitarra": Arma("cimitarra", "1d6", "cortante", "marcial", finura=True,
                      ligera=True),
    "garrote": Arma("garrote", "1d4", "contundente", "simple", ligera=True),
    # armas naturales de monstruos
    "mordida": Arma("mordida", "1d6", "perforante", "simple"),
    "garra": Arma("garra", "1d6", "cortante", "simple"),
    "mordida_grande": Arma("mordida_grande", "2d4", "perforante", "simple"),
    "clava_grande": Arma("clava_grande", "2d8", "contundente", "simple",
                         dos_manos_fijo=True),
    "artes_marciales": Arma("artes_marciales", "1d4", "contundente", "simple",
                            finura=True, ligera=True),
}

ARMADURAS: dict[str, Armadura] = {
    "cuero": Armadura("cuero", "ligera", 11, des_max=None),
    "cuero_tachonado": Armadura("cuero_tachonado", "ligera", 12, des_max=None),
    "camisa_de_mallas": Armadura("camisa_de_mallas", "media", 13, des_max=2),
    "coraza": Armadura("coraza", "media", 14, des_max=2),
    "media_armadura": Armadura("media_armadura", "media", 15, des_max=2),
    "ring_mail": Armadura("ring_mail", "pesada", 14, des_max=0),
    "cota_de_mallas": Armadura("cota_de_mallas", "pesada", 16, des_max=0),
    "armadura_de_placas": Armadura("armadura_de_placas", "pesada", 18, des_max=0),
}

# Aliases de compatibilidad: nombres viejos → misma armadura (personajes
# existentes en DB siguen funcionando; la UI solo lista los nuevos).
ARMADURAS["cota_de_malla_camisa"] = ARMADURAS["camisa_de_mallas"]
ARMADURAS["cota_de_anillas"] = ARMADURAS["ring_mail"]
ARMADURAS["cota_de_malla"] = ARMADURAS["cota_de_mallas"]
ARMADURAS["cota_de_placas"] = ARMADURAS["armadura_de_placas"]

# ---------------------------------------------------------------- clases

CLASES: dict[str, dict] = {
    "barbaro":   {"dado_golpe": "d12", "lanzador": None,     "atributo_magico": None},
    "guerrero":  {"dado_golpe": "d10", "lanzador": None,     "atributo_magico": None},
    "paladin":   {"dado_golpe": "d10", "lanzador": "medio",  "atributo_magico": "CAR"},
    "ranger":    {"dado_golpe": "d10", "lanzador": "medio",  "atributo_magico": "SAB"},
    "clerigo":   {"dado_golpe": "d8",  "lanzador": "completo", "atributo_magico": "SAB"},
    "druida":    {"dado_golpe": "d8",  "lanzador": "completo", "atributo_magico": "SAB"},
    "bardo":     {"dado_golpe": "d8",  "lanzador": "completo", "atributo_magico": "CAR"},
    "monje":     {"dado_golpe": "d8",  "lanzador": None,     "atributo_magico": None},
    "picaro":    {"dado_golpe": "d8",  "lanzador": None,     "atributo_magico": None},
    "hechicero": {"dado_golpe": "d8",  "lanzador": "completo", "atributo_magico": "CAR"},
    "mago":      {"dado_golpe": "d6",  "lanzador": "completo", "atributo_magico": "INT"},
    "brujo":     {"dado_golpe": "d6",  "lanzador": "brujo",  "atributo_magico": "CAR"},
}

# Slots de lanzador completo por nivel de personaje (niveles 1-20, SRD/PHB)
SLOTS_COMPLETO: dict[int, dict[str, int]] = {
    1:  {"1": 2},
    2:  {"1": 3},
    3:  {"1": 4, "2": 2},
    4:  {"1": 4, "2": 3},
    5:  {"1": 4, "2": 3, "3": 2},
    6:  {"1": 4, "2": 3, "3": 3},
    7:  {"1": 4, "2": 3, "3": 3, "4": 1},
    8:  {"1": 4, "2": 3, "3": 3, "4": 2},
    9:  {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    10: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    11: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    12: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    13: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    14: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    15: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    16: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    17: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1, "9": 1},
    18: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 1, "7": 1, "8": 1, "9": 1},
    19: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 1, "8": 1, "9": 1},
    20: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 2, "8": 1, "9": 1},
}

# Slots de medio lanzador (Paladín / Ranger) por nivel de personaje (1-20)
SLOTS_MEDIO: dict[int, dict[str, int]] = {
    1: {},
    2: {"1": 2},
    3: {"1": 3},
    4: {"1": 3},
    5: {"1": 4, "2": 2},
    6: {"1": 4, "2": 2},
    7: {"1": 4, "2": 3},
    8: {"1": 4, "2": 3},
    9: {"1": 4, "2": 3, "3": 2},
    10: {"1": 4, "2": 3, "3": 2},
    11: {"1": 4, "2": 3, "3": 3},
    12: {"1": 4, "2": 3, "3": 3},
    13: {"1": 4, "2": 3, "3": 3, "4": 1},
    14: {"1": 4, "2": 3, "3": 3, "4": 1},
    15: {"1": 4, "2": 3, "3": 3, "4": 2},
    16: {"1": 4, "2": 3, "3": 3, "4": 2},
    17: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    18: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    19: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    20: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
}

# Brujo: (cantidad de slots, nivel de esos slots) por nivel de personaje (1-20)
SLOTS_BRUJO: dict[int, tuple[int, int]] = {
    1: (1, 1), 2: (2, 1), 3: (2, 2), 4: (2, 2), 5: (2, 3),
    6: (2, 3), 7: (2, 4), 8: (2, 4), 9: (2, 5), 10: (2, 5),
    11: (3, 5), 12: (3, 5), 13: (3, 5), 14: (3, 5), 15: (3, 5),
    16: (3, 5), 17: (4, 5), 18: (4, 5), 19: (4, 5), 20: (4, 5),
}


def cr_a_numero(cr: str) -> float:
    """'1/4' → 0.25; '2' → 2.0. Para comparar Challenge Ratings."""
    cr = str(cr).strip()
    if "/" in cr:
        n, d = cr.split("/")
        return int(n) / int(d)
    try:
        return float(cr)
    except ValueError:
        return 0.0


# Bestias elegibles como Forma Salvaje (druida). El tope de CR sube por nivel.
FORMAS_SALVAJES = ["rata_gigante", "jabali", "lobo", "pantera",
                   "arania_gigante", "oso_pardo"]


def cr_max_forma_salvaje(nivel: int) -> float:
    """Tope de CR de Forma Salvaje por nivel de druida (SRD, sin movilidad
    especial en v1): nv2 → 1/4, nv4 → 1/2, nv8 → 1."""
    if nivel >= 8:
        return 1.0
    if nivel >= 4:
        return 0.5
    return 0.25


def formas_salvajes_disponibles(nivel: int) -> list[str]:
    tope = cr_max_forma_salvaje(nivel)
    return [b for b in FORMAS_SALVAJES
            if b in MONSTRUOS and cr_a_numero(MONSTRUOS[b]["cr"]) <= tope]


def slots_iniciales(clase: str, nivel: int) -> dict:
    """Devuelve el dict de slots {'1': {'usados': 0, 'max': X}, ...} para clase/nivel."""
    info = CLASES[clase]
    tipo = info["lanzador"]
    if tipo is None:
        return {}
    if tipo == "completo":
        tabla = SLOTS_COMPLETO[min(max(nivel, 1), 20)]
    elif tipo == "medio":
        tabla = SLOTS_MEDIO[min(max(nivel, 1), 20)]
    else:  # brujo
        cant, nv = SLOTS_BRUJO[min(max(nivel, 1), 20)]
        return {str(nv): {"usados": 0, "max": cant}}
    return {nv: {"usados": 0, "max": m} for nv, m in tabla.items()}


# ---------------------------------------------------------------- XP por CR
# Para cálculo automático de XP de combate en el backend.

XP_POR_CR: dict[str, int] = {
    "0": 10, "1/8": 25, "1/4": 50, "1/2": 100,
    "1": 200, "2": 450, "3": 700, "4": 1100, "5": 1800,
}

# ---------------------------------------------------------------- monstruos v1

MONSTRUOS: dict[str, dict] = {
    "goblin": {
        "nombre": "Goblin", "cr": "1/4", "pg": 7, "ca_fija": 15, "velocidad_m": 9,
        "atributos": {"FUE": 8, "DES": 14, "CON": 10, "INT": 10, "SAB": 8, "CAR": 8},
        "armas": ["cimitarra", "arco_corto"],
    },
    "lobo": {
        "nombre": "Lobo", "cr": "1/4", "pg": 11, "ca_fija": 13, "velocidad_m": 12,
        "atributos": {"FUE": 12, "DES": 15, "CON": 12, "INT": 3, "SAB": 12, "CAR": 6},
        "armas": ["mordida"],  # arma custom: 2d4+2 perforante — definir en props del NPC
    },
    "bandido": {
        "nombre": "Bandido", "cr": "1/8", "pg": 11, "ca_fija": 12, "velocidad_m": 9,
        "atributos": {"FUE": 11, "DES": 12, "CON": 12, "INT": 10, "SAB": 10, "CAR": 10},
        "armas": ["cimitarra", "ballesta_de_mano"],
    },
    "esqueleto": {
        "nombre": "Esqueleto", "cr": "1/4", "pg": 13, "ca_fija": 13, "velocidad_m": 9,
        "atributos": {"FUE": 10, "DES": 14, "CON": 15, "INT": 6, "SAB": 8, "CAR": 5},
        "armas": ["espada_corta", "arco_corto"], "tipo_criatura": "no_muerto",
    },
    "zombi": {
        "nombre": "Zombi", "cr": "1/4", "pg": 22, "ca_fija": 8, "velocidad_m": 6,
        "atributos": {"FUE": 13, "DES": 6, "CON": 16, "INT": 3, "SAB": 6, "CAR": 5},
        "armas": ["garrote"], "tipo_criatura": "no_muerto",
    },
    "orco": {
        "nombre": "Orco", "cr": "1/2", "pg": 15, "ca_fija": 13, "velocidad_m": 9,
        "atributos": {"FUE": 16, "DES": 12, "CON": 16, "INT": 7, "SAB": 11, "CAR": 10},
        "armas": ["hacha_de_batalla"],
    },
    "rata_gigante": {
        "nombre": "Rata gigante", "cr": "1/8", "pg": 7, "ca_fija": 12, "velocidad_m": 9,
        "atributos": {"FUE": 7, "DES": 15, "CON": 11, "INT": 2, "SAB": 10, "CAR": 4},
        "armas": ["mordida"],
    },
    "cultista": {
        "nombre": "Cultista", "cr": "1/8", "pg": 9, "ca_fija": 12, "velocidad_m": 9,
        "atributos": {"FUE": 11, "DES": 12, "CON": 10, "INT": 10, "SAB": 11, "CAR": 10},
        "armas": ["cimitarra"],
    },
    "maton": {
        "nombre": "Matón", "cr": "1/2", "pg": 32, "ca_fija": 11, "velocidad_m": 9,
        "atributos": {"FUE": 15, "DES": 11, "CON": 14, "INT": 10, "SAB": 10, "CAR": 11},
        "armas": ["mazo"],
    },
    "arania_gigante": {
        "nombre": "Araña gigante", "cr": "1", "pg": 26, "ca_fija": 14, "velocidad_m": 9,
        "atributos": {"FUE": 14, "DES": 16, "CON": 12, "INT": 2, "SAB": 11, "CAR": 4},
        "armas": ["mordida_grande"],
    },
    "ogro": {
        "nombre": "Ogro", "cr": "2", "pg": 59, "ca_fija": 11, "velocidad_m": 12,
        "atributos": {"FUE": 19, "DES": 8, "CON": 16, "INT": 5, "SAB": 7, "CAR": 7},
        "armas": ["clava_grande"],
    },
    # bestias (para Forma Salvaje del druida y monturas)
    "oso_pardo": {
        "nombre": "Oso pardo", "cr": "1", "pg": 34, "ca_fija": 11, "velocidad_m": 12,
        "atributos": {"FUE": 19, "DES": 10, "CON": 16, "INT": 2, "SAB": 13, "CAR": 7},
        "armas": ["garra"], "tipo_criatura": "bestia",
    },
    "jabali": {
        "nombre": "Jabalí", "cr": "1/4", "pg": 11, "ca_fija": 11, "velocidad_m": 12,
        "atributos": {"FUE": 13, "DES": 11, "CON": 12, "INT": 2, "SAB": 9, "CAR": 5},
        "armas": ["mordida"], "tipo_criatura": "bestia",
    },
    "caballo_de_guerra": {
        "nombre": "Caballo de guerra", "cr": "1/2", "pg": 19, "ca_fija": 11,
        "velocidad_m": 18,
        "atributos": {"FUE": 18, "DES": 12, "CON": 13, "INT": 2, "SAB": 12, "CAR": 7},
        "armas": ["garra"], "tipo_criatura": "bestia", "montura": True,
    },
    "pantera": {
        "nombre": "Pantera", "cr": "1/4", "pg": 13, "ca_fija": 12, "velocidad_m": 15,
        "atributos": {"FUE": 14, "DES": 15, "CON": 10, "INT": 3, "SAB": 14, "CAR": 7},
        "armas": ["mordida"], "tipo_criatura": "bestia",
    },
}

# ---------------------------------------------------------------- consumibles

CONSUMIBLES: dict[str, dict] = {
    "pocion_de_curacion": {"efecto": "curacion", "formula": "2d4+2",
                           "descripcion": "Recupera 2d4+2 PG al beberla"},
    "pocion_de_curacion_mayor": {"efecto": "curacion", "formula": "4d4+4",
                                 "descripcion": "Recupera 4d4+4 PG"},
    "antorcha": {"efecto": "narrativo", "descripcion": "Ilumina 6m por 1 hora"},
    "racion": {"efecto": "narrativo", "descripcion": "Comida para un día"},
}

# ---------------------------------------------------------------- conjuros v1
# Solo lo mecánico. La descripción narrativa la pone el LLM.
# "resolucion": "ataque" | "salvacion" | "auto" | "curacion"

CONJUROS: dict[str, dict] = {
    # Trucos
    "ray_of_frost": {
        "nivel": 0, "resolucion": "ataque", "danio": "1d8", "tipo_danio": "frio",
        "concentracion": False, "efecto_extra": "velocidad_objetivo -3m 1 turno",
    },
    "sacred_flame": {
        "nivel": 0, "resolucion": "salvacion", "salvacion": "DES",
        "danio": "1d8", "tipo_danio": "radiante", "en_salvacion_exitosa": "nada",
        "concentracion": False,
    },
    "chill_touch": {
        "nivel": 0, "resolucion": "ataque", "danio": "1d8", "tipo_danio": "necrotico",
        "concentracion": False, "efecto_extra": "no puede recuperar PG 1 turno",
    },
    "light": {"nivel": 0, "resolucion": "auto", "concentracion": False},
    "eldritch_blast": {  # eldritch blast (SRD)
        "nivel": 0, "resolucion": "ataque", "danio": "1d10",
        "tipo_danio": "fuerza", "concentracion": False,
    },
    "prestidigitation": {"nivel": 0, "resolucion": "auto", "concentracion": False},

    # Nivel 1
    "magic_missile": {
        "nivel": 1, "resolucion": "auto", "danio": "1d4+1", "proyectiles": 3,
        "tipo_danio": "fuerza", "concentracion": False,
        "escalado": "+1 proyectil por nivel de slot extra",
        "escalado_proyectiles": 1,
    },
    "cure_wounds": {
        "nivel": 1, "resolucion": "curacion", "curacion": "1d8",
        "suma_mod_magico": True, "concentracion": False,
        "escalado": "+1d8 por nivel de slot extra",
        "escalado_curacion": "1d8",
    },
    "healing_word": {
        "nivel": 1, "resolucion": "curacion", "curacion": "1d4",
        "suma_mod_magico": True, "concentracion": False, "accion": "adicional",
        "escalado_curacion": "1d4",
    },
    "burning_hands": {
        "nivel": 1, "resolucion": "salvacion", "salvacion": "DES",
        "danio": "3d6", "tipo_danio": "fuego", "en_salvacion_exitosa": "mitad",
        "area": "cono 4.5m", "concentracion": False,
        "escalado": "+1d6 por nivel de slot extra",
        "escalado_danio": "1d6",
    },
    "shield": {
        "nivel": 1, "resolucion": "auto", "concentracion": False,
        "accion": "reaccion", "efecto": "+5 CA hasta inicio de su próximo turno",
    },
    "mage_armor": {
        "nivel": 1, "resolucion": "auto", "concentracion": False,
        "efecto": "CA base = 13 + DES por 8 horas (sin armadura)",
    },
    "bless": {
        "nivel": 1, "resolucion": "auto", "concentracion": True,
        "efecto": "hasta 3 aliados suman 1d4 a ataques y salvaciones",
    },
    "bane": {
        "nivel": 1, "resolucion": "salvacion", "salvacion": "CAR",
        "concentracion": True,
        "efecto": "hasta 3 enemigos restan 1d4 a ataques y salvaciones",
    },
    "sleep": {
        "nivel": 1, "resolucion": "auto", "concentracion": False,
        "efecto": "5d8 PG de criaturas caen dormidas, de menor a mayor PG actual",
        "escalado": "+2d8 por nivel de slot extra",
    },
    "thunderwave": {
        "nivel": 1, "resolucion": "salvacion", "salvacion": "CON",
        "danio": "2d8", "tipo_danio": "trueno", "en_salvacion_exitosa": "mitad",
        "area": "cubo 4.5m", "concentracion": False,
        "efecto_extra": "empuja 3m si falla la salvación",
        "escalado_danio": "1d8",
    },
    "charm_person": {
        "nivel": 1, "resolucion": "salvacion", "salvacion": "SAB",
        "concentracion": False, "efecto": "hechizado 1 hora (humanoide)",
    },
    "heroism": {  # heroism
        "nivel": 1, "resolucion": "auto", "concentracion": True,
        "efecto": "objetivo inmune a asustado, gana PG temporales = mod mágico por turno",
    },
    "hunter_s_mark": {
        "nivel": 1, "resolucion": "auto", "concentracion": True,
        "efecto": "+1d6 de daño contra el objetivo marcado",
    },
    "color_spray": {
        "nivel": 1, "resolucion": "auto", "concentracion": False,
        "efecto": "6d10 PG de criaturas quedan cegadas 1 ronda, de menor a mayor",
    },

    # Nivel 2
    "scorching_ray": {
        "nivel": 2, "resolucion": "ataque", "danio": "2d6", "tipo_danio": "fuego",
        "proyectiles": 3, "concentracion": False,
        "escalado": "+1 rayo por nivel de slot extra",
    },
    "hold_person": {
        "nivel": 2, "resolucion": "salvacion", "salvacion": "SAB",
        "concentracion": True, "efecto": "paralizado; repite salvación cada turno",
    },
    "invisibility": {
        "nivel": 2, "resolucion": "auto", "concentracion": True,
        "efecto": "invisible hasta atacar o lanzar conjuro",
    },
    "misty_step": {
        "nivel": 2, "resolucion": "auto", "concentracion": False,
        "accion": "adicional", "efecto": "teleport 9m a punto visible",
    },
    "aid": {  # aid
        "nivel": 2, "resolucion": "auto", "concentracion": False,
        "efecto": "+5 PG max y actuales a 3 criaturas por 8 horas",
    },

    # -------- conjuros rituales (se lanzan sin gastar espacio, +10 min) -------
    "detect_magic": {
        "nivel": 1, "resolucion": "auto", "concentracion": True, "ritual": True,
        "componentes": "VS",
        "efecto": "Percibís la presencia de magia a 9m durante 10 minutos.",
    },
    "comprehend_languages": {
        "nivel": 1, "resolucion": "auto", "concentracion": False, "ritual": True,
        "componentes": "VSM",
        "efecto": "Entendés cualquier idioma hablado que oigas por 1 hora.",
    },
    "speak_with_animals": {
        "nivel": 1, "resolucion": "auto", "concentracion": False, "ritual": True,
        "componentes": "VS",
        "efecto": "Podés comunicarte con bestias durante 10 minutos.",
    },
    "alarm": {
        "nivel": 1, "resolucion": "auto", "concentracion": False, "ritual": True,
        "componentes": "VSM",
        "efecto": "Creás una alarm en un área por 8 horas.",
    },
    "identify": {
        "nivel": 1, "resolucion": "auto", "concentracion": False, "ritual": True,
        "componentes": "VSM",
        "componente_costoso": {"nombre": "perla", "costo": 100,
                               "consumido": False},
        "efecto": "Aprendés las propiedades de un objeto mágico.",
    },
    "augury": {
        "nivel": 2, "resolucion": "auto", "concentracion": False, "ritual": True,
        "componentes": "VSM",
        "componente_costoso": {"nombre": "varillas_de_augurio", "costo": 25,
                               "consumido": False},
        "efecto": "Recibís un presagio sobre una acción en la próxima hora "
                  "(buenaventura, infortunio, ambos o nada).",
    },
}

# Clases que pueden lanzar rituales (con el conjuro conocido/preparado)
CLASES_RITUALISTAS = {"bardo", "clerigo", "druida", "mago"}

# --------- listas de conjuros por clase (quién puede aprender qué, SRD) -------
# Los conjuros importados de Open5e ya traen "clases" en inglés; los curados
# arriba no, así que se las asignamos acá. Esto restringe qué puede elegir cada
# clase (p. ej. el druida no aprende Sirviente Invisible).
_NORM_CLASE = {
    "barbarian": "barbaro", "fighter": "guerrero", "paladin": "paladin",
    "ranger": "ranger", "cleric": "clerigo", "druid": "druida", "bard": "bardo",
    "monk": "monje", "rogue": "picaro", "sorcerer": "hechicero",
    "wizard": "mago", "warlock": "brujo",
    # identidad para claves ya en español
    "barbaro": "barbaro", "guerrero": "guerrero", "clerigo": "clerigo",
    "druida": "druida", "bardo": "bardo", "monje": "monje", "picaro": "picaro",
    "hechicero": "hechicero", "mago": "mago", "brujo": "brujo",
}

# Clases de los conjuros curados (claves en español de arriba).
_CLASES_CURADAS = {
    # trucos
    "ray_of_frost": ["hechicero", "mago"],
    "sacred_flame": ["clerigo"],
    "chill_touch": ["hechicero", "mago", "brujo"],
    "light": ["bardo", "clerigo", "hechicero", "mago"],
    "eldritch_blast": ["brujo"],
    "prestidigitation": ["bardo", "hechicero", "mago", "brujo"],
    # nivel 1
    "magic_missile": ["hechicero", "mago"],
    "cure_wounds": ["bardo", "clerigo", "druida", "paladin", "ranger"],
    "healing_word": ["bardo", "clerigo", "druida"],
    "burning_hands": ["hechicero", "mago"],
    "shield": ["hechicero", "mago"],
    "mage_armor": ["hechicero", "mago"],
    "bless": ["clerigo", "paladin"],
    "bane": ["bardo", "clerigo"],
    "sleep": ["bardo", "hechicero", "mago"],
    "thunderwave": ["bardo", "druida", "hechicero", "mago"],
    "charm_person": ["bardo", "druida", "hechicero", "mago", "brujo"],
    "heroism": ["bardo", "paladin"],
    "hunter_s_mark": ["ranger"],
    "color_spray": ["hechicero", "mago"],
    # nivel 2
    "scorching_ray": ["hechicero", "mago"],
    "hold_person": ["bardo", "clerigo", "druida", "hechicero", "mago", "brujo"],
    "invisibility": ["bardo", "hechicero", "mago", "brujo"],
    "misty_step": ["hechicero", "mago", "brujo"],
    "aid": ["clerigo", "paladin"],
    # rituales
    "detect_magic": ["bardo", "clerigo", "druida", "paladin", "ranger",
                       "hechicero", "mago"],
    "comprehend_languages": ["bardo", "hechicero", "mago", "brujo"],
    "speak_with_animals": ["bardo", "druida", "ranger"],
    "alarm": ["mago", "ranger"],
    "identify": ["bardo", "mago"],
    "augury": ["clerigo"],
}
for _k, _cl in _CLASES_CURADAS.items():
    if _k in CONJUROS:
        CONJUROS[_k]["clases"] = _cl


def clases_de_conjuro(conjuro: dict) -> list[str]:
    """Clases (claves en español) que pueden aprender un conjuro dado su dict."""
    out: list[str] = []
    for c in conjuro.get("clases", []) or []:
        n = _NORM_CLASE.get(str(c).lower().strip())
        if n and n not in out:
            out.append(n)
    return out


def puede_aprender_conjuro(clase: str, conjuro: str) -> bool:
    """¿La clase puede aprender ese conjuro? (True si no tenemos su lista de
    clases, para no bloquear contenido importado sin metadata)."""
    c = CONJUROS.get(conjuro)
    if c is None:
        return False
    clases = clases_de_conjuro(c)
    return clase in clases if clases else True


# --------- riqueza inicial por clase (PHB "Starting Wealth by Class") ----------
# (cantidad de d4, multiplicador). El monje usa 5d4 sin multiplicar.
PLATA_INICIAL_CLASE = {
    "barbaro": (2, 10), "bardo": (5, 10), "clerigo": (5, 10), "druida": (2, 10),
    "guerrero": (5, 10), "monje": (5, 1), "paladin": (5, 10), "ranger": (5, 10),
    "picaro": (4, 10), "hechicero": (3, 10), "mago": (4, 10), "brujo": (4, 10),
}


def oro_inicial_clase(clase: str) -> int:
    """Tira la riqueza inicial de la clase (PHB) y devuelve el oro resultante."""
    from .dice import roll
    n, mult = PLATA_INICIAL_CLASE.get(clase, (0, 0))
    return roll(f"{n}d4")["total"] * mult if n else 0


# ---------------------------------------------------------------- razas

# bonos: se suman a los atributos base elegidos por el jugador.
# velocidad_m: sobreescribe la base de 9m si difiere.
RAZAS: dict[str, dict] = {
    "humano": {
        "bonos": {}, "velocidad_m": 9,
        "rasgo": "Adaptable y ambicioso",
        "subrazas": {
            "estandar": {"bonos": {"FUE": 1, "DES": 1, "CON": 1,
                                   "INT": 1, "SAB": 1, "CAR": 1},
                         "rasgo": "+1 a todos los atributos"},
            "variante": {"bonos": {}, "bonos_a_eleccion": 2,
                         "rasgo": "+1 a dos atributos a elección, una "
                                  "competencia de habilidad extra y un feat "
                                  "(cargá los tuyos en FEATS)"},
        },
    },
    "elfo": {
        "bonos": {"DES": 2}, "velocidad_m": 9,
        "rasgo": "Visión en la oscuridad, ventaja contra encantamientos",
        "subrazas": {
            "alto_elfo": {"bonos": {"INT": 1}, "rasgo": "Un truco de mago extra"},
            "elfo_de_los_bosques": {"bonos": {"SAB": 1}, "velocidad_m": 10,
                                    "rasgo": "Pies ligeros: velocidad 10m"},
            "drow": {"bonos": {"CAR": 1},
                     "rasgo": "Visión superior en la oscuridad"},
        },
    },
    "enano": {
        "bonos": {"CON": 2}, "velocidad_m": 7,
        "rasgo": "Resistencia al veneno, visión en la oscuridad",
        "resistencias": ["veneno"],
        "subrazas": {
            "enano_de_las_colinas": {"bonos": {"SAB": 1},
                                     "rasgo": "+1 PG por nivel"},
            "enano_de_las_montanas": {"bonos": {"FUE": 2},
                                      "rasgo": "Competencia con armadura ligera y media"},
        },
    },
    "mediano": {
        "bonos": {"DES": 2}, "velocidad_m": 7,
        "rasgo": "Suertudo: repite los 1 naturales (narrativo v1)",
        "subrazas": {
            "piesligeros": {"bonos": {"CAR": 1}, "rasgo": "Sigilo natural"},
            "fornido": {"bonos": {"CON": 1}, "rasgo": "Resistencia al veneno"},
        },
    },
    "gnomo": {
        "bonos": {"INT": 2}, "velocidad_m": 7,
        "rasgo": "Astucia gnoma: ventaja en salvaciones mentales vs magia",
        "subrazas": {
            "gnomo_del_bosque": {"bonos": {"DES": 1}, "rasgo": "Habla con animales pequeños"},
            "gnomo_de_las_rocas": {"bonos": {"CON": 1}, "rasgo": "Saber artificiero"},
        },
    },
    "semielfo": {
        "bonos": {"CAR": 2}, "velocidad_m": 9,
        "rasgo": "+2 CAR y +1 a DOS atributos a elección; visión en la "
                 "oscuridad, ventaja contra encantamientos",
        "bonos_a_eleccion": 2,
        "subrazas": {
            "estandar": {"bonos": {},
                         "rasgo": "Versatilidad: dos competencias de "
                                  "habilidad extra a elección"},
            "descendiente_alto_elfo": {"bonos": {},
                                       "rasgo": "Un truco de la lista de "
                                                "mago (elegilo en Conjuros)"},
            "descendiente_drow": {"bonos": {},
                                  "rasgo": "Magia drow: luces danzantes; "
                                           "más adelante fuego feérico"},
        },
    },
    "semiorco": {
        "bonos": {"FUE": 2, "CON": 1}, "velocidad_m": 9,
        "rasgo": "Aguante implacable: 1 vez por descanso largo, queda a 1 PG en vez de 0",
        "subrazas": {},
    },
    "draconido": {
        "bonos": {"FUE": 2, "CAR": 1}, "velocidad_m": 9,
        "rasgo": "Ascendencia dracónica: aliento de dragón y resistencia "
                 "elemental según tu linaje",
        "subrazas": {
            "negro": {"bonos": {}, "elemento": "acido", "salvacion_aliento": "DES",
                "rasgo": "Aliento de acido (2d6, salvación de DES para mitad) y resistencia al acido"},
            "azul": {"bonos": {}, "elemento": "rayo", "salvacion_aliento": "DES",
                "rasgo": "Aliento de rayo (2d6, salvación de DES para mitad) y resistencia al rayo"},
            "laton": {"bonos": {}, "elemento": "fuego", "salvacion_aliento": "DES",
                "rasgo": "Aliento de fuego (2d6, salvación de DES para mitad) y resistencia al fuego"},
            "bronce": {"bonos": {}, "elemento": "rayo", "salvacion_aliento": "DES",
                "rasgo": "Aliento de rayo (2d6, salvación de DES para mitad) y resistencia al rayo"},
            "cobre": {"bonos": {}, "elemento": "acido", "salvacion_aliento": "DES",
                "rasgo": "Aliento de acido (2d6, salvación de DES para mitad) y resistencia al acido"},
            "oro": {"bonos": {}, "elemento": "fuego", "salvacion_aliento": "DES",
                "rasgo": "Aliento de fuego (2d6, salvación de DES para mitad) y resistencia al fuego"},
            "verde": {"bonos": {}, "elemento": "veneno", "salvacion_aliento": "CON",
                "rasgo": "Aliento de veneno (2d6, salvación de CON para mitad) y resistencia al veneno"},
            "rojo": {"bonos": {}, "elemento": "fuego", "salvacion_aliento": "DES",
                "rasgo": "Aliento de fuego (2d6, salvación de DES para mitad) y resistencia al fuego"},
            "plata": {"bonos": {}, "elemento": "frio", "salvacion_aliento": "CON",
                "rasgo": "Aliento de frio (2d6, salvación de CON para mitad) y resistencia al frio"},
            "blanco": {"bonos": {}, "elemento": "frio", "salvacion_aliento": "CON",
                "rasgo": "Aliento de frio (2d6, salvación de CON para mitad) y resistencia al frio"},
        },
    },
    "tiefling": {
        "bonos": {"CAR": 2}, "velocidad_m": 9,
        "rasgo": "Resistencia al fuego, visión en la oscuridad. Tu linaje "
                 "infernal define tu segundo atributo y tu magia.",
        "resistencias": ["fuego"],
        # Linajes de Mordenkainen (todos suman CAR+2 en la base y un +1 propio).
        "subrazas": {
            "asmodeus": {"bonos": {"INT": 1},
                         "rasgo": "Legado de Asmodeus: truco Taumaturgia; a nv3 "
                                  "Reprensión Infernal, a nv5 Oscuridad (CAR)."},
            "baalzebul": {"bonos": {"INT": 1},
                          "rasgo": "Legado de Baalzebul: truco Toque Gélido; a "
                                   "nv3 Rayo Enfermizo, a nv5 Rayo de Debilidad."},
            "dispater": {"bonos": {"DES": 1},
                         "rasgo": "Legado de Dispater: truco Taumaturgia; a nv3 "
                                  "Disfrazarse, a nv5 Detectar Pensamientos."},
            "fierna": {"bonos": {"SAB": 1},
                       "rasgo": "Legado de Fierna: truco Amistad; a nv3 "
                                "Hechizar Persona, a nv5 Sugestión."},
            "glasya": {"bonos": {"DES": 1},
                       "rasgo": "Legado de Glasya: truco Ilusión Menor; a nv3 "
                                "Disfrazarse, a nv5 Invisibilidad."},
            "levistus": {"bonos": {"CON": 1},
                         "rasgo": "Legado de Levistus: truco Rayo de Escarcha; "
                                  "a nv3 Perdición, a nv5 Inmovilizar Persona.",
                         "resistencias": ["frio"]},
            "mammon": {"bonos": {"INT": 1},
                       "rasgo": "Legado de Mammon: truco Mano de Mago; a nv3 "
                                "Detectar Objetos, a nv5 Aureola de Monedas."},
            "mephistopheles": {"bonos": {"INT": 1},
                               "rasgo": "Legado de Mephistopheles: truco Manos "
                                        "Ardientes-menor; a nv3 Manos Ardientes, "
                                        "a nv5 Flecha Ácida de Melf."},
            "zariel": {"bonos": {"FUE": 1},
                       "rasgo": "Legado de Zariel: truco Llama Sagrada; a nv3 "
                                "Fe Militante, a nv5 Franja Abrasadora."},
        },
    },
}
RAZAS["tiflin"] = RAZAS["tiefling"]  # alias de compatibilidad

def parsear_raza(raza_str: str) -> tuple[str, str | None]:
    """'draconido (oro)' → ('draconido', 'oro'); 'humano' → ('humano', None)."""
    raza_str = (raza_str or "").strip()
    if "(" in raza_str:
        base, _, resto = raza_str.partition("(")
        return base.strip(), resto.rstrip(")").strip() or None
    return raza_str, None


def resistencias_de_raza(raza_str: str) -> list[str]:
    base, sub = parsear_raza(raza_str)
    r = RAZAS.get(base)
    if r is None:
        return []
    res = list(r.get("resistencias", []))
    if sub and sub in r["subrazas"]:
        sr = r["subrazas"][sub]
        res += sr.get("resistencias", [])
        if sr.get("elemento"):           # dracónido: resiste su elemento
            res.append(sr["elemento"])
    return res


def aliento_de_raza(raza_str: str) -> dict | None:
    """Datos del aliento de dragón si la raza lo tiene."""
    base, sub = parsear_raza(raza_str)
    if base != "draconido" or not sub:
        return None
    sr = RAZAS["draconido"]["subrazas"].get(sub)
    if not sr:
        return None
    return {"elemento": sr["elemento"], "salvacion": sr["salvacion_aliento"]}


def recursos_raciales(raza_str: str, nivel: int) -> dict:
    """Recursos activos que vienen de la raza (se suman a los de clase)."""
    r: dict = {}
    if aliento_de_raza(raza_str):
        r["aliento_de_dragon"] = {"usados": 0, "max": 1, "reset": "corto"}
    return r


# ---------------------------------------------------------------- trasfondos
# Trasfondos (SRD Acólito + los 13 del PHB). Otorgan 2 competencias de
# habilidad, equipo, oro inicial y un rasgo narrativo que la IA puede usar.
# "competencias" usa las claves de HABILIDADES.
TRASFONDOS: dict[str, dict] = {
    "acolito": {
        "nombre": "Acólito", "competencias": ["perspicacia", "religion"],
        "idiomas": 2, "oro": 15,
        "equipo": [{"nombre": "simbolo_sagrado", "cantidad": 1},
                   {"nombre": "libro_de_oraciones", "cantidad": 1},
                   {"nombre": "vestiduras", "cantidad": 1}],
        "rasgo": "Refugio de los Fieles",
        "rasgo_desc": "Templos afines te dan cobijo, curación básica y apoyo "
                      "(pero no dinero) a vos y a tus compañeros."},
    "charlatan": {
        "nombre": "Charlatán", "competencias": ["engano", "juego_de_manos"],
        "herramientas": ["kit_de_disfraz", "kit_de_falsificacion"], "oro": 15,
        "equipo": [{"nombre": "kit_de_disfraz", "cantidad": 1}],
        "rasgo": "Identidad Falsa",
        "rasgo_desc": "Tenés una segunda identidad creíble y sabés falsificar "
                      "documentos."},
    "criminal": {
        "nombre": "Criminal", "competencias": ["engano", "sigilo"],
        "herramientas": ["kit_de_ladron"], "oro": 15,
        "equipo": [{"nombre": "palanca", "cantidad": 1}],
        "rasgo": "Contacto Criminal",
        "rasgo_desc": "Tenés un contacto confiable en el bajomundo que hace de "
                      "enlace con otros criminales."},
    "artista": {
        "nombre": "Artista", "competencias": ["acrobacias", "actuacion"],
        "herramientas": ["kit_de_disfraz", "instrumento_musical"], "oro": 15,
        "equipo": [{"nombre": "instrumento_musical", "cantidad": 1}],
        "rasgo": "Por Demanda Popular",
        "rasgo_desc": "Siempre encontrás dónde actuar; a cambio te dan hospedaje "
                      "y comida, y la gente del lugar te aprecia."},
    "heroe_del_pueblo": {
        "nombre": "Héroe del Pueblo",
        "competencias": ["trato_con_animales", "supervivencia"],
        "herramientas": ["herramientas_de_artesano"], "oro": 10,
        "equipo": [{"nombre": "herramientas_de_artesano", "cantidad": 1},
                   {"nombre": "pala", "cantidad": 1}],
        "rasgo": "Hospitalidad Rústica",
        "rasgo_desc": "La gente común te esconde y ayuda: podés refugiarte "
                      "entre ellos mientras no atraigas a sus enemigos."},
    "gremio_artesano": {
        "nombre": "Artesano de Gremio",
        "competencias": ["perspicacia", "persuasion"],
        "herramientas": ["herramientas_de_artesano"], "idiomas": 1, "oro": 15,
        "equipo": [{"nombre": "herramientas_de_artesano", "cantidad": 1}],
        "rasgo": "Membresía de Gremio",
        "rasgo_desc": "Tu gremio te da apoyo político y social, alojamiento en "
                      "sus casas y contactos, a cambio de cuotas."},
    "ermitano": {
        "nombre": "Ermitaño", "competencias": ["medicina", "religion"],
        "herramientas": ["kit_de_herboristeria"], "idiomas": 1, "oro": 5,
        "equipo": [{"nombre": "kit_de_herboristeria", "cantidad": 1}],
        "rasgo": "Descubrimiento",
        "rasgo_desc": "En tu aislamiento hallaste una verdad única y poderosa "
                      "(un secreto, una reliquia o una revelación)."},
    "noble": {
        "nombre": "Noble", "competencias": ["historia", "persuasion"],
        "herramientas": ["set_de_juego"], "idiomas": 1, "oro": 25,
        "equipo": [{"nombre": "anillo_de_sello", "cantidad": 1},
                   {"nombre": "ropa_fina", "cantidad": 1}],
        "rasgo": "Posición de Privilegio",
        "rasgo_desc": "La gente te trata con deferencia; conseguís audiencias, "
                      "hospedaje entre nobles y acceso a la alta sociedad."},
    "forastero": {
        "nombre": "Forastero", "competencias": ["atletismo", "supervivencia"],
        "herramientas": ["instrumento_musical"], "idiomas": 1, "oro": 10,
        "equipo": [{"nombre": "baston", "cantidad": 1},
                   {"nombre": "trampa_de_caza", "cantidad": 1}],
        "rasgo": "Errante",
        "rasgo_desc": "Recordás la geografía, ríos y asentamientos; podés "
                      "hallar comida y agua para el grupo en la naturaleza."},
    "sabio": {
        "nombre": "Sabio", "competencias": ["arcanos", "historia"],
        "idiomas": 2, "oro": 10,
        "equipo": [{"nombre": "frasco_de_tinta", "cantidad": 1},
                   {"nombre": "pluma", "cantidad": 1}],
        "rasgo": "Investigador",
        "rasgo_desc": "Aunque no sepas un dato, sabés dónde y de quién "
                      "obtenerlo: bibliotecas, universidades, colegas."},
    "marinero": {
        "nombre": "Marinero", "competencias": ["atletismo", "percepcion"],
        "herramientas": ["herramientas_de_navegante"], "oro": 10,
        "equipo": [{"nombre": "cuerda_de_seda", "cantidad": 1},
                   {"nombre": "amuleto_de_la_suerte", "cantidad": 1}],
        "rasgo": "Pasaje de Barco",
        "rasgo_desc": "Podés conseguir pasaje gratis en un barco para vos y el "
                      "grupo, a cambio de ayudar con la tripulación."},
    "soldado": {
        "nombre": "Soldado", "competencias": ["atletismo", "intimidacion"],
        "herramientas": ["set_de_juego"], "oro": 10,
        "equipo": [{"nombre": "insignia_de_rango", "cantidad": 1},
                   {"nombre": "set_de_juego", "cantidad": 1}],
        "rasgo": "Rango Militar",
        "rasgo_desc": "Tu rango es reconocido: soldados leales a tu antiguo "
                      "ejército te obedecen en asuntos menores."},
    "huerfano": {
        "nombre": "Pilluelo", "competencias": ["juego_de_manos", "sigilo"],
        "herramientas": ["kit_de_disfraz", "kit_de_ladron"], "oro": 10,
        "equipo": [{"nombre": "mapa_de_la_ciudad", "cantidad": 1},
                   {"nombre": "cuchillo", "cantidad": 1}],
        "rasgo": "Secretos de la Ciudad",
        "rasgo_desc": "Conocés los pasajes secretos de la urbe: te movés por "
                      "ella al doble de velocidad entre callejones."},
}


def aplicar_trasfondo(clave: str) -> dict:
    """Devuelve los datos del trasfondo o lanza ValueError si no existe."""
    if clave not in TRASFONDOS:
        raise ValueError(f"Trasfondo desconocido: {clave}. "
                         f"Opciones: {list(TRASFONDOS)}")
    return TRASFONDOS[clave]


# ---------------------------------------------------------------- point buy

PUNTOS_COMPRA = 27
COSTO_PUNTOS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}


def validar_point_buy(atributos: dict) -> tuple[bool, str]:
    """Valida una asignación base (SIN bonos raciales) contra point buy 27."""
    total = 0
    for atr, v in atributos.items():
        if v not in COSTO_PUNTOS:
            return False, f"{atr}={v} fuera de rango point buy (8-15)"
        total += COSTO_PUNTOS[v]
    if total > PUNTOS_COMPRA:
        return False, f"Gastaste {total} puntos (máximo {PUNTOS_COMPRA})"
    return True, f"{total}/{PUNTOS_COMPRA} puntos usados"


def aplicar_bonos_raciales(base: dict, raza: str, subraza: str | None,
                           bonos_eleccion: list[str] | None = None) -> tuple[dict, int, str]:
    """Devuelve (atributos_finales, velocidad_m, rasgos_texto).

    Lanza ValueError si raza/subraza/elección son inválidas.
    """
    if raza not in RAZAS:
        raise ValueError(f"Raza desconocida: {raza}. Opciones: {list(RAZAS)}")
    r = RAZAS[raza]
    if r["subrazas"] and not subraza:
        raise ValueError(f"La raza {raza} requiere subraza: {list(r['subrazas'])}")
    if subraza and subraza not in r["subrazas"]:
        raise ValueError(f"Subraza inválida para {raza}: {subraza}")

    finales = dict(base)
    rasgos = [r["rasgo"]]
    for atr, b in r["bonos"].items():
        finales[atr] = finales.get(atr, 10) + b
    velocidad = r.get("velocidad_m", 9)

    if subraza:
        sr = r["subrazas"][subraza]
        for atr, b in sr.get("bonos", {}).items():
            finales[atr] = finales.get(atr, 10) + b
        velocidad = sr.get("velocidad_m", velocidad)
        rasgos.append(sr["rasgo"])

    n_eleccion = r.get("bonos_a_eleccion", 0)
    if subraza:
        n_eleccion = r["subrazas"][subraza].get("bonos_a_eleccion", n_eleccion)
    if n_eleccion:
        elegidos = bonos_eleccion or []
        if len(set(elegidos)) != n_eleccion or                 any(a not in ("FUE", "DES", "CON", "INT", "SAB", "CAR")
                    for a in elegidos) or                 any(a in r["bonos"] for a in elegidos):
            raise ValueError(
                f"{raza}: elegí {n_eleccion} atributos distintos "
                f"(que no sean {list(r['bonos'])}) para el +1")
        for a in elegidos:
            finales[a] += 1

    for atr, v in finales.items():
        finales[atr] = min(20, v)
    return finales, velocidad, "; ".join(rasgos)


# ---------------------------------------------------------------- alineamientos

ALINEAMIENTOS = [
    "legal_bueno", "neutral_bueno", "caotico_bueno",
    "legal_neutral", "neutral", "caotico_neutral",
    "legal_malvado", "neutral_malvado", "caotico_malvado",
]

# ---------------------------------------------------------------- estilos de combate (guerrero, SRD)

ESTILOS_COMBATE = {
    "defensa": "+1 CA mientras usás armadura",
    "duelo": "+2 al daño con arma melé a una mano",
    "arqueria": "+2 a las tiradas de ataque a distancia",
    "gran_arma": "Re-tirás los 1 y 2 en los dados de daño de un arma melé a dos manos",
    "proteccion": "Con escudo, usás tu reacción para dar desventaja a un ataque "
                  "contra un aliado cercano",
    "dos_armas": "Sumás tu modificador de atributo al daño del ataque con la "
                 "mano secundaria",
}

# ---------------------------------------------------------------- competencias de clase (SRD)
# Competencias que otorga cada clase: salvaciones, categorías de armas y de
# armaduras (incluye "escudo"). Fuente única para creación, /api/content y la UI.
SALVACIONES_CLASE = {
    "barbaro": ["FUE", "CON"], "guerrero": ["FUE", "CON"],
    "paladin": ["SAB", "CAR"], "ranger": ["FUE", "DES"],
    "clerigo": ["SAB", "CAR"], "druida": ["INT", "SAB"],
    "bardo": ["DES", "CAR"], "monje": ["FUE", "DES"],
    "picaro": ["DES", "INT"], "hechicero": ["CON", "CAR"],
    "mago": ["INT", "SAB"], "brujo": ["SAB", "CAR"],
}

ARMAS_COMP_CLASE = {
    "barbaro": ["simple", "marcial"], "guerrero": ["simple", "marcial"],
    "paladin": ["simple", "marcial"], "ranger": ["simple", "marcial"],
    "clerigo": ["simple"], "druida": ["simple"],
    "bardo": ["simple"], "monje": ["simple"],
    "picaro": ["simple"], "hechicero": ["simple"],
    "mago": ["simple"], "brujo": ["simple"],
}

ARMADURAS_COMP_CLASE = {
    "barbaro": ["ligera", "media", "escudo"],
    "guerrero": ["ligera", "media", "pesada", "escudo"],
    "paladin": ["ligera", "media", "pesada", "escudo"],
    "ranger": ["ligera", "media", "escudo"],
    "clerigo": ["ligera", "media", "escudo"],
    "druida": ["ligera", "media", "escudo"],
    "bardo": ["ligera"], "monje": [], "picaro": ["ligera"],
    "hechicero": [], "mago": [], "brujo": ["ligera"],
}


# Lista de habilidades entre las que elige cada clase, y cuántas (PHB).
# Las competencias de habilidad del PJ = estas elegidas + las del trasfondo.
CLASE_HABILIDADES = {
    "barbaro": ["trato_con_animales", "atletismo", "intimidacion", "naturaleza",
                "percepcion", "supervivencia"],
    "bardo": ["atletismo", "acrobacias", "juego_de_manos", "sigilo", "arcanos",
              "historia", "investigacion", "naturaleza", "religion",
              "perspicacia", "medicina", "percepcion", "supervivencia",
              "trato_con_animales", "engano", "intimidacion", "actuacion",
              "persuasion"],   # bardo: cualquier habilidad
    "clerigo": ["historia", "perspicacia", "medicina", "persuasion", "religion"],
    "druida": ["arcanos", "trato_con_animales", "perspicacia", "medicina",
               "naturaleza", "percepcion", "religion", "supervivencia"],
    "guerrero": ["acrobacias", "trato_con_animales", "atletismo", "historia",
                 "perspicacia", "intimidacion", "percepcion", "supervivencia"],
    "monje": ["acrobacias", "atletismo", "historia", "perspicacia", "religion",
              "sigilo"],
    "paladin": ["atletismo", "perspicacia", "intimidacion", "medicina",
                "persuasion", "religion"],
    "ranger": ["trato_con_animales", "atletismo", "perspicacia", "investigacion",
               "naturaleza", "percepcion", "sigilo", "supervivencia"],
    "picaro": ["acrobacias", "atletismo", "engano", "perspicacia", "intimidacion",
               "investigacion", "percepcion", "actuacion", "persuasion",
               "juego_de_manos", "sigilo"],
    "hechicero": ["arcanos", "engano", "perspicacia", "intimidacion",
                  "persuasion", "religion"],
    "mago": ["arcanos", "historia", "perspicacia", "investigacion", "medicina",
             "religion"],
    "brujo": ["arcanos", "engano", "historia", "intimidacion", "investigacion",
              "naturaleza", "religion"],
}

# Cantidad de habilidades que elige cada clase (PHB): la mayoría 2; pícaro 4;
# bardo y explorador 3.
CLASE_HABILIDADES_N = {
    "barbaro": 2, "bardo": 3, "clerigo": 2, "druida": 2, "guerrero": 2,
    "monje": 2, "paladin": 2, "ranger": 3, "picaro": 4, "hechicero": 2,
    "mago": 2, "brujo": 2,
}


def competencias_de_clase(clase: str) -> dict:
    """Competencias base (sin trasfondo) que otorga una clase."""
    return {
        "salvaciones": list(SALVACIONES_CLASE.get(clase, [])),
        "armas": list(ARMAS_COMP_CLASE.get(clase, [])),
        "armaduras": list(ARMADURAS_COMP_CLASE.get(clase, [])),
    }


def puede_usar_arma(competencias: dict, arma_nombre: str) -> bool:
    """¿La criatura es competente con esa arma? (por categoría o nombre)."""
    a = ARMAS.get(arma_nombre)
    if a is None:
        return False
    comp = competencias.get("armas", [])
    return a.categoria in comp or arma_nombre in comp


def puede_usar_armadura(competencias: dict, armadura_nombre: str | None) -> bool:
    """¿Es competente con esa armadura? Sin armadura siempre es válido."""
    if not armadura_nombre:
        return True
    a = ARMADURAS.get(armadura_nombre)
    if a is None:
        return False
    return a.categoria in competencias.get("armaduras", [])


def puede_usar_escudo(competencias: dict) -> bool:
    return "escudo" in competencias.get("armaduras", [])

# ---------------------------------------------------------------- recursos de clase (SRD, niveles 1-4)
# tipo: "corto" se recupera con descanso corto; "largo" con descanso largo.

def _usos_furia(nivel: int) -> int:
    """Usos de Furia por nivel (SRD). Ilimitada a nivel 20."""
    if nivel >= 20:
        return 99
    if nivel >= 17:
        return 6
    if nivel >= 12:
        return 5
    if nivel >= 6:
        return 4
    if nivel >= 3:
        return 3
    return 2


def _usos_canalizar_clerigo(nivel: int) -> int:
    """Usos de Canalizar Divinidad del clérigo por nivel (SRD)."""
    if nivel >= 18:
        return 3
    if nivel >= 6:
        return 2
    return 1


def recursos_clase_iniciales(clase: str, nivel: int, mod_car: int = 0) -> dict:
    """Recursos activos de clase para clase/nivel. Se guarda en Character."""
    r: dict = {}
    if clase == "barbaro":
        r["furia"] = {"usados": 0, "max": _usos_furia(nivel), "reset": "largo"}
    if clase == "guerrero":
        r["nuevo_aliento"] = {"usados": 0, "max": 1, "reset": "corto"}
        if nivel >= 2:
            r["oleada_de_accion"] = {"usados": 0,
                                     "max": 2 if nivel >= 17 else 1,
                                     "reset": "corto"}
    if clase == "clerigo" and nivel >= 2:
        r["canalizar_divinidad"] = {"usados": 0,
                                    "max": _usos_canalizar_clerigo(nivel),
                                    "reset": "corto"}
    if clase == "paladin":
        r["imposicion_de_manos"] = {"pool": 5 * nivel, "pool_max": 5 * nivel,
                                    "reset": "largo"}
    if clase == "bardo":
        r["inspiracion_bardica"] = {"usados": 0, "max": max(1, mod_car),
                                    "reset": "corto" if nivel >= 5 else "largo"}
    if clase == "monje" and nivel >= 2:
        r["ki"] = {"usados": 0, "max": nivel, "reset": "corto"}
    if clase == "druida" and nivel >= 2:
        r["forma_salvaje"] = {"usados": 0, "max": 2, "reset": "corto"}
    if clase == "hechicero" and nivel >= 2:
        r["puntos_hechiceria"] = {"pool": nivel, "pool_max": nivel,
                                  "reset": "largo"}
    if clase == "paladin" and nivel >= 3:
        r["canalizar_divinidad"] = {"usados": 0,
                                    "max": 2 if nivel >= 18 else 1,
                                    "reset": "corto"}
    if clase == "mago":
        r["recuperacion_arcana"] = {"usados": 0, "max": 1, "reset": "largo"}
    return r


# ---------------------------------------------------------------- hechicero
# Fuente de Magia: costo en Puntos de Hechicería para CREAR un espacio de
# conjuro de cada nivel (SRD). Convertir un espacio en puntos da PH = nivel.
COSTO_SLOT_EN_PH = {1: 2, 2: 3, 3: 5, 4: 6, 5: 7}

# Metamagia (SRD): efectos soportados por el motor + costo en PH.
# "empoderado" y "elevado" tienen efecto mecánico completo; el resto gasta los
# puntos y el narrador describe el efecto.
METAMAGIA: dict[str, dict] = {
    "empoderado": {"nombre": "Conjuro Empoderado", "costo": 1,
                   "desc": "Re-tirás hasta tu mod de CAR dados de daño y usás "
                           "las nuevas tiradas."},
    "elevado": {"nombre": "Conjuro Elevado", "costo": 3,
                "desc": "El objetivo tiene desventaja en su primera salvación "
                        "contra el conjuro."},
    "acelerado": {"nombre": "Conjuro Acelerado", "costo": 2,
                  "desc": "Lanzás un conjuro de acción como acción adicional."},
    "sutil": {"nombre": "Conjuro Sutil", "costo": 1,
              "desc": "Lanzás sin componentes verbales ni somáticos."},
    "gemelo": {"nombre": "Conjuro Gemelo", "costo": "nivel",
               "desc": "Un conjuro de un solo objetivo apunta a un segundo "
                       "objetivo (costo = nivel del conjuro, mín 1)."},
    "distante": {"nombre": "Conjuro Distante", "costo": 1,
                 "desc": "Duplicás el alcance del conjuro."},
    "prolongado": {"nombre": "Conjuro Prolongado", "costo": 1,
                   "desc": "Duplicás la duración del conjuro."},
    "cuidadoso": {"nombre": "Conjuro Cuidadoso", "costo": 1,
                  "desc": "Aliados elegidos salvan automáticamente contra tu "
                          "conjuro de área."},
}


# ---------------------------------------------------------------- brujo
# Invocaciones Sobrenaturales (SRD). "requisito_conjuro" exige conocer ese
# conjuro; "nivel_min" el nivel mínimo de brujo. "mecanico" marca las que el
# motor aplica; el resto van al contexto del narrador.
INVOCACIONES: dict[str, dict] = {
    "explosion_agonizante": {
        "nombre": "Explosión Agonizante", "nivel_min": 2, "mecanico": True,
        "requisito_conjuro": "eldritch_blast",
        "desc": "Sumás tu modificador de Carisma al daño de tu Explosión "
                "Sobrenatural."},
    "explosion_repelente": {
        "nombre": "Explosión Repelente", "nivel_min": 2,
        "requisito_conjuro": "eldritch_blast",
        "desc": "Al impactar con Explosión Sobrenatural, empujás al objetivo 3m."},
    "hechicero_del_pacto": {
        "nombre": "Tomo del Pacto (Secretos Ancestrales)", "nivel_min": 2,
        "desc": "Aprendés trucos rituales y podés lanzarlos como rituales."},
    "vista_del_diablo": {
        "nombre": "Vista del Diablo", "nivel_min": 2,
        "desc": "Ves en la oscuridad, incluso mágica, hasta 36m."},
    "influencia_seductora": {
        "nombre": "Influencia Seductora", "nivel_min": 2, "mecanico": True,
        "otorga_competencias": ["engano", "persuasion"],
        "desc": "Ganás competencia en Engaño y Persuasión."},
    "mascara_de_mil_rostros": {
        "nombre": "Máscara de Mil Rostros", "nivel_min": 2,
        "desc": "Podés lanzar Disfrazarse a voluntad, sin gastar espacio."},
    "lanza_sobrenatural": {
        "nombre": "Lanza Sobrenatural", "nivel_min": 2,
        "requisito_conjuro": "eldritch_blast",
        "desc": "El alcance de tu Explosión Sobrenatural sube a 90m."},
    "hoja_sedienta": {
        "nombre": "Hoja Sedienta", "nivel_min": 5,
        "desc": "Tu arma de pacto gana +tu mod de CAR de daño necrótico "
                "(narrativo v1)."},
}


def invocaciones_conocidas_max(nivel: int) -> int:
    """Cantidad de Invocaciones Sobrenaturales conocidas por nivel de brujo."""
    tabla = {2: 2, 5: 3, 7: 4, 9: 5, 12: 6, 15: 7, 18: 8}
    disponible = 0
    for nv, n in sorted(tabla.items()):
        if nivel >= nv:
            disponible = n
    return disponible


def metamagias_conocidas_max(nivel: int) -> int:
    """Cantidad de opciones de metamagia que conoce un hechicero por nivel."""
    if nivel >= 17:
        return 4
    if nivel >= 10:
        return 3
    if nivel >= 3:
        return 2
    return 0


def costo_metamagia(clave: str, nivel_conjuro: int) -> int:
    """Costo en PH de una metamagia para un conjuro de nivel dado."""
    c = METAMAGIA[clave]["costo"]
    if c == "nivel":
        return max(1, nivel_conjuro)
    return int(c)


# Descripciones para UI y para el contexto del narrador
HABILIDADES_CLASE_INFO = {
    "furia": "Bárbaro — Acción adicional. +2 daño melé y aguante hasta que "
             "termine el combate.",
    "nuevo_aliento": "Guerrero — Acción adicional. Recuperás 1d10+nivel PG.",
    "oleada_de_accion": "Guerrero nv2 — Este turno hacés UNA acción de "
                        "ataque extra.",
    "canalizar_divinidad": "Clérigo nv2 — Preservar Vida: curás 5×nivel PG "
                           "a un aliado.",
    "imposicion_de_manos": "Paladín — Curás X PG de tu reserva de 5×nivel.",
    "inspiracion_bardica": "Bardo — Acción adicional. Un aliado suma 1d6 a "
                           "su próxima tirada de ataque o habilidad.",
    "recuperacion_arcana": "Mago — En un descanso corto recuperás espacios "
                           "de conjuro (total de niveles = mitad de tu nivel, "
                           "redondeado arriba). Se aplica solo.",
    "rafaga_de_golpes": "Monje nv2 — 1 ki. Un ataque desarmado extra este "
                        "turno.",
    "defensa_paciente": "Monje nv2 — 1 ki. Esquivar sin consumir el turno.",
    "frenesi": "Berserker nv3 — En furia: un ataque extra este turno, gratis.",
    "arma_sagrada": "Devoción nv3 — Canalizar divinidad: sumás tu mod CAR a "
                    "los ataques hasta que termine el combate.",
}

# Rasgos de subclase (info para ficha y contexto del DM)
SUBCLASES_INFO = {
    "campeon": "Crítico mejorado: criticás con 19-20 (mecánico)",
    "dominio_de_la_vida": "Discípulo de la Vida: tus conjuros de curación "
                          "curan +2+nivel del conjuro (mecánico)",
    "cazador": "Presa del cazador: +1d8 de daño contra criaturas heridas "
               "(mecánico)",
    "linaje_draconico": "Resiliencia dracónica: +1 PG por nivel y CA 13+DES "
                        "sin armadura (mecánico)",
    "senda_del_berserker": "Frenesí: en furia, un ataque extra por turno "
                           "(mecánico)",
    "juramento_de_devocion": "Arma Sagrada: canalizás para sumar CAR a tus "
                             "ataques (mecánico)",
    "camino_de_la_mano_abierta": "Técnica de la mano abierta (narrativo v1)",
    "colegio_del_saber": "Tres competencias extra y palabras cortantes "
                         "(narrativo v1)",
    "circulo_de_la_tierra": "Recuperación natural y conjuros de círculo "
                            "(narrativo v1)",
    "ladron": "Manos rápidas y trepar de segundo piso (narrativo v1)",
    "escuela_de_evocacion": "Esculpir conjuros: tus aliados esquivan tus "
                            "evocaciones (narrativo v1: avisale al DM)",
    "patron_infernal": "Bendición del oscuro: PG temporales al abatir "
                       "enemigos (narrativo v1)",
}

# ---------------------------------------------------------------- feats
# Dotes (feats) del PHB + el Grappler del SRD. Efectos soportados por el motor:
#   "asi": {"ATR": n}                 → suma fija a atributo(s) (tope 20)
#   "asi_eleccion": ["FUE","DES"]     → +1 a UNO de esos a elección del jugador
#   "hp_por_nivel": n                 → +n PG por nivel de personaje (Vigoroso)
#   "bono_iniciativa": n              → +n a la iniciativa (Alerta)
#   "competencia_salvacion_eleccion": ["FUE",...] → competencia en la salv. elegida
#   "competencias": ["sigilo", ...]   → competencias de habilidad fijas
#   "pasivo": "texto"                 → efecto narrativo (va al contexto del DM)
# Las dotes se toman en los niveles de Mejora (4, 8, 12, 16, 19) en vez del +2.
FEATS: dict[str, dict] = {
    "luchador_agarrador": {  # Grappler (SRD)
        "nombre": "Luchador Agarrador", "requisito": {"FUE": 13},
        "efectos": {"pasivo": "Ventaja en ataques contra criaturas que "
                              "agarraste; podés intentar inmovilizarlas."}},
    "resistente": {  # Resilient
        "nombre": "Resistente", "requisito": {},
        "efectos": {"asi_eleccion": ["FUE", "DES", "CON", "INT", "SAB", "CAR"],
                    "competencia_salvacion_eleccion": ["FUE", "DES", "CON",
                                                       "INT", "SAB", "CAR"],
                    "pasivo": "Competencia en salvaciones del atributo elegido."}},
    "vigoroso": {  # Tough
        "nombre": "Vigoroso", "requisito": {},
        "efectos": {"hp_por_nivel": 2,
                    "pasivo": "Tus PG máximos suben en 2 por nivel."}},
    "alerta": {  # Alert
        "nombre": "Alerta", "requisito": {},
        "efectos": {"bono_iniciativa": 5,
                    "pasivo": "No podés ser sorprendido mientras estés "
                              "consciente; los atacantes ocultos no ganan "
                              "ventaja contra vos."}},
    "atleta": {  # Athlete
        "nombre": "Atleta", "requisito": {},
        "efectos": {"asi_eleccion": ["FUE", "DES"],
                    "pasivo": "Te levantás de estar derribado con solo 1.5m de "
                              "movimiento; trepás sin coste extra."}},
    "actor": {
        "nombre": "Actor", "requisito": {},
        "efectos": {"asi": {"CAR": 1},
                    "pasivo": "Ventaja en Engaño y Actuación al hacerte pasar "
                              "por otra persona; imitás voces."}},
    "observador": {  # Observant
        "nombre": "Observador", "requisito": {},
        "efectos": {"asi_eleccion": ["INT", "SAB"],
                    "pasivo": "+5 a tu Percepción y Perspicacia pasivas; leés "
                              "los labios."}},
    "robusto": {  # Durable
        "nombre": "Robusto", "requisito": {},
        "efectos": {"asi": {"CON": 1},
                    "pasivo": "Al gastar Dados de Golpe recuperás como mínimo "
                              "el doble de tu mod. de CON."}},
    "experto_en_habilidades": {  # Skilled
        "nombre": "Experto en Habilidades", "requisito": {},
        "efectos": {"pasivo": "Ganás competencia en tres habilidades o "
                              "herramientas a elección (cargalas con el DM)."}},
    "gran_maestro_de_armas": {  # Great Weapon Master
        "nombre": "Gran Maestro de Armas", "requisito": {},
        "efectos": {"pasivo": "Al sacar crítico o abatir a un enemigo, ganás un "
                              "ataque de arma cuerpo a cuerpo como acción "
                              "adicional. Podés restar 5 al ataque para sumar "
                              "10 al daño con armas pesadas (avisá al DM)."}},
    "tirador_agudo": {  # Sharpshooter
        "nombre": "Tirador Agudo", "requisito": {},
        "efectos": {"pasivo": "Ignorás cobertura parcial y penalización por "
                              "largo alcance. Podés restar 5 al ataque a "
                              "distancia para sumar 10 al daño (avisá al DM)."}},
    "centinela": {  # Sentinel
        "nombre": "Centinela", "requisito": {},
        "efectos": {"pasivo": "Tus ataques de oportunidad reducen a 0 el "
                              "movimiento del objetivo; atacás a quien ataque "
                              "a un aliado cerca tuyo."}},
    "afortunado": {  # Lucky
        "nombre": "Afortunado", "requisito": {},
        "efectos": {"pasivo": "Tenés 3 puntos de suerte por descanso largo para "
                              "re-tirar un d20 de ataque, salvación o habilidad "
                              "(avisá al DM)."}},
}


def efectos_feats(feats: list) -> dict:
    """Agrega los efectos mecánicos de una lista de feats guardados en el
    personaje (cada uno {'clave': str, 'atributo': str|None}).
    Devuelve {'hp_por_nivel': int, 'bono_iniciativa': int}."""
    hp = 0
    ini = 0
    for f in feats or []:
        clave = f.get("clave") if isinstance(f, dict) else f
        if not clave:
            continue
        ef = FEATS.get(clave, {}).get("efectos", {})
        hp += ef.get("hp_por_nivel", 0)
        ini += ef.get("bono_iniciativa", 0)
    return {"hp_por_nivel": hp, "bono_iniciativa": ini}


# ---------------------------------------------------------------- contenido importado
# scripts/importar_srd.py genera data/*.json desde Open5e (SRD, CC-BY).
# Se mergean sin pisar el contenido curado de arriba.

import json as _json
import pathlib as _pathlib

# Objetos mágicos importados del SRD (catálogo para loot/tiendas futuras)
OBJETOS_MAGICOS: dict[str, dict] = {}

# Razas/subrazas custom del usuario: data/razas_custom.json.
# Formato (mismo que RAZAS; las claves nuevas se agregan, las existentes
# se MERGEAN a nivel subraza — ideal para agregar bloodlines de tus libros):
# {
#   "tiefling": {"subrazas": {
#       "zariel": {"bonos": {"FUE": 1}, "rasgo": "Truco taumaturgia; ..."},
#       "mephistopheles": {"bonos": {"INT": 1}, "rasgo": "..."}
#   }},
#   "raza_totalmente_nueva": {"bonos": {"DES": 2}, "velocidad_m": 9,
#                             "rasgo": "...", "subrazas": {}}
# }
# Nota: si a una raza sin subrazas le agregás subrazas, la subraza pasa a
# ser obligatoria en creación (agregá una "estandar" con bonos {} si querés
# conservar la versión base).

_DATA = _pathlib.Path(__file__).resolve().parent.parent / "data"
_p_razas = _DATA / "razas_custom.json"
if _p_razas.exists():
    try:
        try:
            _texto = _p_razas.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            _texto = _p_razas.read_text(encoding="cp1252")
        for _rk, _rv in _json.loads(_texto).items():
            if _rk in RAZAS:
                RAZAS[_rk].setdefault("subrazas", {}).update(
                    _rv.get("subrazas", {}))
                for _campo in ("bonos", "rasgo", "velocidad_m",
                               "resistencias", "bonos_a_eleccion"):
                    if _campo in _rv and _campo != "subrazas":
                        RAZAS[_rk][_campo] = _rv[_campo]
            else:
                _rv.setdefault("subrazas", {})
                _rv.setdefault("bonos", {})
                _rv.setdefault("rasgo", "")
                RAZAS[_rk] = _rv
    except Exception as _e:
        print(f"[content] no pude cargar razas_custom.json: {_e}")

for _archivo, _destino in (("monstruos_srd.json", MONSTRUOS),
                           ("conjuros_srd.json", CONJUROS),
                           ("objetos_magicos_srd.json", OBJETOS_MAGICOS)):
    _p = _DATA / _archivo
    if _p.exists():
        try:
            try:
                _texto = _p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                _texto = _p.read_text(encoding="cp1252")  # escrito en Windows
            for _k, _v in _json.loads(_texto).items():
                _destino.setdefault(_k, _v)
        except Exception as _e:  # un JSON roto no debe tirar el server
            print(f"[content] no pude cargar {_archivo}: {_e}")

# XP por CR completa (tabla estándar; monstruos importados llegan a CR 30)
XP_POR_CR.update({
    "6": 2300, "7": 2900, "8": 3900, "9": 5000, "10": 5900,
    "11": 7200, "12": 8400, "13": 10000, "14": 11500, "15": 13000,
    "16": 15000, "17": 18000, "18": 20000, "19": 22000, "20": 25000,
    "21": 33000, "22": 41000, "23": 50000, "24": 62000, "25": 75000,
    "26": 90000, "27": 105000, "28": 120000, "29": 135000, "30": 155000,
})



# ---------------------------------------------------------------- nivel 5

# Clases con Ataque Extra a partir de nivel 5 (SRD)
ATAQUE_EXTRA_NV5 = {"guerrero", "barbaro", "paladin", "ranger", "monje"}


def ataques_por_accion(clase: str, nivel: int) -> int:
    """Cantidad de ataques con la acción de Ataque. El guerrero llega a 3 (nv11)
    y 4 (nv20); el resto de clases con Ataque Extra hacen 2 desde nivel 5."""
    if clase == "guerrero":
        if nivel >= 20:
            return 4
        if nivel >= 11:
            return 3
        if nivel >= 5:
            return 2
        return 1
    if clase in ATAQUE_EXTRA_NV5 and nivel >= 5:
        return 2
    return 1


# Conjuros conocidos máximos por nivel de personaje (SRD/PHB, niveles 1-20)
CONOCIDOS_MAX = {
    "bardo":     {1: 4, 2: 5, 3: 6, 4: 7, 5: 8, 6: 9, 7: 10, 8: 11, 9: 12,
                  10: 14, 11: 15, 12: 15, 13: 16, 14: 18, 15: 19, 16: 19,
                  17: 20, 18: 22, 19: 22, 20: 22},
    "hechicero": {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10,
                  10: 11, 11: 12, 12: 12, 13: 13, 14: 13, 15: 14, 16: 14,
                  17: 15, 18: 15, 19: 15, 20: 15},
    "brujo":     {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10,
                  10: 10, 11: 11, 12: 11, 13: 12, 14: 12, 15: 13, 16: 13,
                  17: 14, 18: 14, 19: 15, 20: 15},
    "ranger":    {1: 0, 2: 2, 3: 3, 4: 3, 5: 4, 6: 4, 7: 5, 8: 5, 9: 6,
                  10: 6, 11: 7, 12: 7, 13: 8, 14: 8, 15: 9, 16: 9, 17: 10,
                  18: 10, 19: 11, 20: 11},
}


def limite_conjuros(clase: str, nivel: int, mod_magico: int) -> tuple[str, int]:
    """Devuelve (sistema, límite): sistema = "conocidos" | "preparados" | "ninguno".

    - Conocidos (bardo/hechicero/brujo/ranger): tabla fija.
    - Preparados (mago/clérigo/druida): mod + nivel (mín 1).
    - Paladín (preparado, medio): mod CAR + nivel//2 (mín 1), desde nv2.
    """
    if clase in CONOCIDOS_MAX:
        return "conocidos", CONOCIDOS_MAX[clase].get(min(max(nivel, 1), 20), 0)
    if clase in ("mago", "clerigo", "druida"):
        return "preparados", max(1, mod_magico + nivel)
    if clase == "paladin":
        return ("preparados", max(1, mod_magico + nivel // 2)) if nivel >= 2             else ("preparados", 0)
    return "ninguno", 0


def nivel_max_conjuro(clase: str, nivel: int) -> int:
    """Nivel de conjuro más alto lanzable según los slots de la clase/nivel."""
    slots = slots_iniciales(clase, nivel)
    return max((int(n) for n in slots), default=0)


# Subclases del SRD por clase (elección narrativa v1: el DM la respeta,
# la mecánica fina de cada una queda para una versión futura)
SUBCLASES_SRD = {
    "barbaro": ["senda_del_berserker"],
    "bardo": ["colegio_del_saber"],
    "clerigo": ["dominio_de_la_vida"],
    "druida": ["circulo_de_la_tierra"],
    "guerrero": ["campeon"],
    "monje": ["camino_de_la_mano_abierta"],
    "paladin": ["juramento_de_devocion"],
    "picaro": ["ladron"],
    "ranger": ["cazador"],
    "hechicero": ["linaje_draconico"],
    "brujo": ["patron_infernal"],
    "mago": ["escuela_de_evocacion"],
}
# Nivel en el que cada clase elige subclase (SRD)
NIVEL_SUBCLASE = {"clerigo": 1, "hechicero": 1, "brujo": 1,
                  "barbaro": 3, "bardo": 3, "guerrero": 3, "monje": 3,
                  "paladin": 3, "picaro": 3, "ranger": 3, "druida": 2,
                  "mago": 2}

# ---------------------------------------------------------------- multiclase
# Requisitos de atributo para multiclasear a/desde cada clase (PHB).
MULTICLASE_REQUISITOS: dict[str, dict[str, int]] = {
    "barbaro": {"FUE": 13},
    "bardo": {"CAR": 13},
    "clerigo": {"SAB": 13},
    "druida": {"SAB": 13},
    "guerrero": {"FUE_O_DES": 13},   # FUE 13 o DES 13
    "monje": {"DES": 13, "SAB": 13},
    "paladin": {"FUE": 13, "CAR": 13},
    "ranger": {"DES": 13, "SAB": 13},
    "picaro": {"DES": 13},
    "hechicero": {"CAR": 13},
    "mago": {"INT": 13},
    "brujo": {"CAR": 13},
}

# Aporte al "nivel de lanzador" combinado para los espacios de multiclase (PHB):
# lanzadores completos aportan su nivel entero; medios (paladín/ranger) la mitad
# redondeada abajo. El brujo NO cuenta acá (Magia de Pacto es aparte).
_APORTE_LANZADOR = {
    "bardo": 1.0, "clerigo": 1.0, "druida": 1.0, "hechicero": 1.0, "mago": 1.0,
    "paladin": 0.5, "ranger": 0.5,
}


def cumple_requisitos_multiclase(clase: str, atributos: dict) -> tuple[bool, str]:
    """¿Cumple los atributos mínimos para (multi)clasear en 'clase'?"""
    reqs = MULTICLASE_REQUISITOS.get(clase, {})
    for atr, minimo in reqs.items():
        if atr == "FUE_O_DES":
            if atributos.get("FUE", 0) < minimo and atributos.get("DES", 0) < minimo:
                return False, "FUE 13 o DES 13"
        elif atributos.get(atr, 0) < minimo:
            return False, f"{atr} {minimo}"
    return True, ""


def nivel_lanzador_multiclase(clases: dict[str, int]) -> int:
    """Nivel de lanzador combinado (PHB) a partir de {clase: nivel}."""
    total = 0.0
    for cls, lvl in clases.items():
        total += _APORTE_LANZADOR.get(cls, 0.0) * lvl
    return int(total)


def slots_multiclase(clases: dict[str, int]) -> dict:
    """Espacios de conjuro combinados (PHB) para una mezcla de clases.
    Usa la tabla de lanzador completo con el nivel de lanzador combinado, y
    agrega los espacios de Magia de Pacto del brujo por separado (aprox v1:
    se suman al mismo nivel; se recuperan con descanso largo)."""
    cl = nivel_lanzador_multiclase(clases)
    slots: dict[str, dict] = {}
    if cl >= 1:
        slots = {nv: {"usados": 0, "max": m}
                 for nv, m in SLOTS_COMPLETO[min(max(cl, 1), 20)].items()}
    nv_brujo = clases.get("brujo", 0)
    if nv_brujo:
        cant, nivel_pacto = SLOTS_BRUJO[min(max(nv_brujo, 1), 20)]
        clave = str(nivel_pacto)
        if clave in slots:
            slots[clave]["max"] += cant
        else:
            slots[clave] = {"usados": 0, "max": cant}
    return slots
