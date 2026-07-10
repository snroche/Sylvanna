"""Contenido 5e hardcodeado para v1. Migrable a Open5e API más adelante.

Todo es data pura (dicts) para poder eventualmente moverlo a la DB o a JSON.
"""
from __future__ import annotations

from .entities import Arma, Armadura

# ---------------------------------------------------------------- armas

ARMAS: dict[str, Arma] = {
    "daga": Arma("daga", "1d4", "perforante", "simple", finura=True,
                 arrojadiza=True, alcance_m=6),
    "espada_corta": Arma("espada_corta", "1d6", "perforante", "marcial", finura=True),
    "espada_larga": Arma("espada_larga", "1d8", "cortante", "marcial", dos_manos="1d10"),
    "hacha_de_mano": Arma("hacha_de_mano", "1d6", "cortante", "simple",
                          arrojadiza=True, alcance_m=6),
    "hacha_de_batalla": Arma("hacha_de_batalla", "1d8", "cortante", "marcial",
                             dos_manos="1d10"),
    "arco_corto": Arma("arco_corto", "1d6", "perforante", "simple",
                       distancia=True, alcance_m=24),
    "arco_largo": Arma("arco_largo", "1d8", "perforante", "marcial",
                       distancia=True, alcance_m=45),
    "ballesta_de_mano": Arma("ballesta_de_mano", "1d6", "perforante", "marcial",
                             distancia=True, alcance_m=9),
    "lanza": Arma("lanza", "1d6", "perforante", "simple", dos_manos="1d8",
                  arrojadiza=True, alcance_m=6),
    "mazo": Arma("mazo", "1d6", "contundente", "simple"),
    "mandoble": Arma("mandoble", "2d6", "cortante", "marcial"),
    "baston": Arma("baston", "1d6", "contundente", "simple", dos_manos="1d8"),
    "cimitarra": Arma("cimitarra", "1d6", "cortante", "marcial", finura=True),
    "garrote": Arma("garrote", "1d4", "contundente", "simple"),
    # armas naturales de monstruos
    "mordida": Arma("mordida", "1d6", "perforante", "simple"),
    "garra": Arma("garra", "1d6", "cortante", "simple"),
    "mordida_grande": Arma("mordida_grande", "2d4", "perforante", "simple"),
    "clava_grande": Arma("clava_grande", "2d8", "contundente", "simple"),
}

ARMADURAS: dict[str, Armadura] = {
    "cuero": Armadura("cuero", "ligera", 11, des_max=None),
    "cuero_tachonado": Armadura("cuero_tachonado", "ligera", 12, des_max=None),
    "cota_de_malla_camisa": Armadura("cota_de_malla_camisa", "media", 13, des_max=2),
    "coraza": Armadura("coraza", "media", 14, des_max=2),
    "media_armadura": Armadura("media_armadura", "media", 15, des_max=2),
    "cota_de_anillas": Armadura("cota_de_anillas", "pesada", 14, des_max=0),
    "cota_de_malla": Armadura("cota_de_malla", "pesada", 16, des_max=0),
    "cota_de_placas": Armadura("cota_de_placas", "pesada", 18, des_max=0),
}

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

# Slots de lanzador completo por nivel de personaje (niveles 1-10)
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
}

# Slots de medio lanzador (Paladín / Ranger) por nivel de personaje
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
}

# Brujo: (cantidad de slots, nivel de esos slots) por nivel de personaje
SLOTS_BRUJO: dict[int, tuple[int, int]] = {
    1: (1, 1), 2: (1, 1), 3: (2, 2), 4: (2, 2), 5: (2, 3),
    6: (2, 3), 7: (2, 4), 8: (2, 4), 9: (2, 5), 10: (2, 5),
}


def slots_iniciales(clase: str, nivel: int) -> dict:
    """Devuelve el dict de slots {'1': {'usados': 0, 'max': X}, ...} para clase/nivel."""
    info = CLASES[clase]
    tipo = info["lanzador"]
    if tipo is None:
        return {}
    if tipo == "completo":
        tabla = SLOTS_COMPLETO[min(nivel, 10)]
    elif tipo == "medio":
        tabla = SLOTS_MEDIO[min(nivel, 10)]
    else:  # brujo
        cant, nv = SLOTS_BRUJO[min(nivel, 10)]
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
        "armas": ["espada_corta", "arco_corto"],
    },
    "zombi": {
        "nombre": "Zombi", "cr": "1/4", "pg": 22, "ca_fija": 8, "velocidad_m": 6,
        "atributos": {"FUE": 13, "DES": 6, "CON": 16, "INT": 3, "SAB": 6, "CAR": 5},
        "armas": ["garrote"],
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
    "rayo_de_escarcha": {
        "nivel": 0, "resolucion": "ataque", "danio": "1d8", "tipo_danio": "frio",
        "concentracion": False, "efecto_extra": "velocidad_objetivo -3m 1 turno",
    },
    "descarga_sagrada": {
        "nivel": 0, "resolucion": "salvacion", "salvacion": "DES",
        "danio": "1d8", "tipo_danio": "radiante", "en_salvacion_exitosa": "nada",
        "concentracion": False,
    },
    "llama_sagrada": {  # alias común
        "nivel": 0, "resolucion": "salvacion", "salvacion": "DES",
        "danio": "1d8", "tipo_danio": "radiante", "en_salvacion_exitosa": "nada",
        "concentracion": False,
    },
    "toque_helado": {
        "nivel": 0, "resolucion": "ataque", "danio": "1d8", "tipo_danio": "necrotico",
        "concentracion": False, "efecto_extra": "no puede recuperar PG 1 turno",
    },
    "luz": {"nivel": 0, "resolucion": "auto", "concentracion": False},
    "prestidigitacion": {"nivel": 0, "resolucion": "auto", "concentracion": False},

    # Nivel 1
    "proyectil_magico": {
        "nivel": 1, "resolucion": "auto", "danio": "1d4+1", "proyectiles": 3,
        "tipo_danio": "fuerza", "concentracion": False,
        "escalado": "+1 proyectil por nivel de slot extra",
    },
    "curar_heridas": {
        "nivel": 1, "resolucion": "curacion", "curacion": "1d8",
        "suma_mod_magico": True, "concentracion": False,
        "escalado": "+1d8 por nivel de slot extra",
    },
    "palabra_de_curacion": {
        "nivel": 1, "resolucion": "curacion", "curacion": "1d4",
        "suma_mod_magico": True, "concentracion": False, "accion": "adicional",
    },
    "manos_ardientes": {
        "nivel": 1, "resolucion": "salvacion", "salvacion": "DES",
        "danio": "3d6", "tipo_danio": "fuego", "en_salvacion_exitosa": "mitad",
        "area": "cono 4.5m", "concentracion": False,
        "escalado": "+1d6 por nivel de slot extra",
    },
    "escudo": {
        "nivel": 1, "resolucion": "auto", "concentracion": False,
        "accion": "reaccion", "efecto": "+5 CA hasta inicio de su próximo turno",
    },
    "armadura_de_mago": {
        "nivel": 1, "resolucion": "auto", "concentracion": False,
        "efecto": "CA base = 13 + DES por 8 horas (sin armadura)",
    },
    "bendecir": {
        "nivel": 1, "resolucion": "auto", "concentracion": True,
        "efecto": "hasta 3 aliados suman 1d4 a ataques y salvaciones",
    },
    "perdicion": {
        "nivel": 1, "resolucion": "salvacion", "salvacion": "CAR",
        "concentracion": True,
        "efecto": "hasta 3 enemigos restan 1d4 a ataques y salvaciones",
    },
    "dormir": {
        "nivel": 1, "resolucion": "auto", "concentracion": False,
        "efecto": "5d8 PG de criaturas caen dormidas, de menor a mayor PG actual",
        "escalado": "+2d8 por nivel de slot extra",
    },
    "onda_atronadora": {
        "nivel": 1, "resolucion": "salvacion", "salvacion": "CON",
        "danio": "2d8", "tipo_danio": "trueno", "en_salvacion_exitosa": "mitad",
        "area": "cubo 4.5m", "concentracion": False,
        "efecto_extra": "empuja 3m si falla la salvación",
    },
    "hechizar_persona": {
        "nivel": 1, "resolucion": "salvacion", "salvacion": "SAB",
        "concentracion": False, "efecto": "hechizado 1 hora (humanoide)",
    },
    "fe_militante": {  # heroism
        "nivel": 1, "resolucion": "auto", "concentracion": True,
        "efecto": "objetivo inmune a asustado, gana PG temporales = mod mágico por turno",
    },
    "marca_del_cazador": {
        "nivel": 1, "resolucion": "auto", "concentracion": True,
        "efecto": "+1d6 de daño contra el objetivo marcado",
    },
    "rociada_de_color": {
        "nivel": 1, "resolucion": "auto", "concentracion": False,
        "efecto": "6d10 PG de criaturas quedan cegadas 1 ronda, de menor a mayor",
    },

    # Nivel 2
    "rayo_abrasador": {
        "nivel": 2, "resolucion": "ataque", "danio": "2d6", "tipo_danio": "fuego",
        "proyectiles": 3, "concentracion": False,
        "escalado": "+1 rayo por nivel de slot extra",
    },
    "inmovilizar_persona": {
        "nivel": 2, "resolucion": "salvacion", "salvacion": "SAB",
        "concentracion": True, "efecto": "paralizado; repite salvación cada turno",
    },
    "invisibilidad": {
        "nivel": 2, "resolucion": "auto", "concentracion": True,
        "efecto": "invisible hasta atacar o lanzar conjuro",
    },
    "paso_brumoso": {
        "nivel": 2, "resolucion": "auto", "concentracion": False,
        "accion": "adicional", "efecto": "teleport 9m a punto visible",
    },
    "ayuda_divina": {  # aid
        "nivel": 2, "resolucion": "auto", "concentracion": False,
        "efecto": "+5 PG max y actuales a 3 criaturas por 8 horas",
    },
}
