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
    "artes_marciales": Arma("artes_marciales", "1d4", "contundente", "simple",
                            finura=True),
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
    "explosion_sobrenatural": {  # eldritch blast (SRD)
        "nivel": 0, "resolucion": "ataque", "danio": "1d10",
        "tipo_danio": "fuerza", "concentracion": False,
    },
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


# ---------------------------------------------------------------- razas

# bonos: se suman a los atributos base elegidos por el jugador.
# velocidad_m: sobreescribe la base de 9m si difiere.
RAZAS: dict[str, dict] = {
    "humano": {
        "bonos": {"FUE": 1, "DES": 1, "CON": 1, "INT": 1, "SAB": 1, "CAR": 1},
        "velocidad_m": 9, "rasgo": "Versátil: +1 a todos los atributos",
        "subrazas": {},
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
        "rasgo": "+1 a DOS atributos a elección (además del +2 CAR)",
        "bonos_a_eleccion": 2,   # el jugador elige 2 atributos distintos de CAR
        "subrazas": {},
    },
    "semiorco": {
        "bonos": {"FUE": 2, "CON": 1}, "velocidad_m": 9,
        "rasgo": "Aguante implacable: 1 vez por descanso largo, queda a 1 PG en vez de 0",
        "subrazas": {},
    },
    "draconido": {
        "bonos": {"FUE": 2, "CAR": 1}, "velocidad_m": 9,
        "rasgo": "Aliento de dragón (narrativo v1), resistencia elemental",
        "subrazas": {},
    },
    "tiefling": {
        "bonos": {"CAR": 2, "INT": 1}, "velocidad_m": 9,
        "rasgo": "Resistencia al fuego, visión en la oscuridad",
        "subrazas": {},
    },
}
RAZAS["tiflin"] = RAZAS["tiefling"]  # alias de compatibilidad

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
}

# ---------------------------------------------------------------- recursos de clase (SRD, niveles 1-4)
# tipo: "corto" se recupera con descanso corto; "largo" con descanso largo.

def recursos_clase_iniciales(clase: str, nivel: int, mod_car: int = 0) -> dict:
    """Recursos activos de clase para clase/nivel. Se guarda en Character."""
    r: dict = {}
    if clase == "barbaro":
        r["furia"] = {"usados": 0, "max": 3 if nivel >= 3 else 2,
                      "reset": "largo"}
    if clase == "guerrero":
        r["nuevo_aliento"] = {"usados": 0, "max": 1, "reset": "corto"}
        if nivel >= 2:
            r["oleada_de_accion"] = {"usados": 0, "max": 1, "reset": "corto"}
    if clase == "clerigo" and nivel >= 2:
        r["canalizar_divinidad"] = {"usados": 0, "max": 1, "reset": "corto"}
    if clase == "paladin":
        r["imposicion_de_manos"] = {"pool": 5 * nivel, "pool_max": 5 * nivel,
                                    "reset": "largo"}
    if clase == "bardo":
        r["inspiracion_bardica"] = {"usados": 0, "max": max(1, mod_car),
                                    "reset": "largo"}
    if clase == "mago":
        r["recuperacion_arcana"] = {"usados": 0, "max": 1, "reset": "largo"}
    return r


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
}

# ---------------------------------------------------------------- feats
# El SRD 5.1 solo incluye UN feat (Grappler). Los demás (PHB, Tasha's,
# Xanathar's) son contenido con copyright: cargalos vos como data acá,
# siguiendo el formato. Efectos soportados por el motor v1:
#   {"asi": {"ATR": 1}}                      → suma al atributo (tope 20)
#   {"pasivo": "texto"}                      → narrativo (va al contexto del DM)
# Los efectos mecánicos complejos requieren código; empezá por los simples.

FEATS: dict[str, dict] = {
    "luchador_agarrador": {  # Grappler (SRD)
        "nombre": "Luchador agarrador",
        "requisito": {"FUE": 13},
        "efectos": {"pasivo": "Ventaja en ataques contra criaturas que "
                              "agarraste; podés intentar inmovilizarlas."},
    },
    # ejemplo de formato para que agregues los tuyos:
    # "resistente": {
    #     "nombre": "Resistente",
    #     "requisito": {},
    #     "efectos": {"asi": {"CON": 1},
    #                 "pasivo": "Competencia en salvaciones de CON"},
    # },
}


# ---------------------------------------------------------------- contenido importado
# scripts/importar_srd.py genera data/*.json desde Open5e (SRD, CC-BY).
# Se mergean sin pisar el contenido curado de arriba.

import json as _json
import pathlib as _pathlib

_DATA = _pathlib.Path(__file__).resolve().parent.parent / "data"
for _archivo, _destino in (("monstruos_srd.json", MONSTRUOS),
                           ("conjuros_srd.json", CONJUROS)):
    _p = _DATA / _archivo
    if _p.exists():
        try:
            for _k, _v in _json.loads(_p.read_text()).items():
                _destino.setdefault(_k, _v)
        except Exception as _e:  # un JSON roto no debe tirar el server
            print(f"[content] no pude cargar {_archivo}: {_e}")

# XP por CR extendida (para monstruos importados de CR alto)
XP_POR_CR.update({
    "6": 2300, "7": 2900, "8": 3900, "9": 5000, "10": 5900,
})


# ---------------------------------------------------------------- nivel 5

# Clases con Ataque Extra a partir de nivel 5 (SRD)
ATAQUE_EXTRA_NV5 = {"guerrero", "barbaro", "paladin", "ranger", "monje"}

# Conjuros conocidos máximos por nivel de personaje (SRD, lanzadores "conocidos")
CONOCIDOS_MAX = {
    "bardo":     {1: 4, 2: 5, 3: 6, 4: 7, 5: 8},
    "hechicero": {1: 2, 2: 3, 3: 4, 4: 5, 5: 6},
    "brujo":     {1: 2, 2: 3, 3: 4, 4: 5, 5: 6},
    "ranger":    {1: 0, 2: 2, 3: 3, 4: 3, 5: 4},
}


def limite_conjuros(clase: str, nivel: int, mod_magico: int) -> tuple[str, int]:
    """Devuelve (sistema, límite): sistema = "conocidos" | "preparados" | "ninguno".

    - Conocidos (bardo/hechicero/brujo/ranger): tabla fija.
    - Preparados (mago/clérigo/druida): mod + nivel (mín 1).
    - Paladín (preparado, medio): mod CAR + nivel//2 (mín 1), desde nv2.
    """
    if clase in CONOCIDOS_MAX:
        return "conocidos", CONOCIDOS_MAX[clase].get(min(nivel, 5), 0)
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
