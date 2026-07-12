"""Forma Salvaje (druida): tope de CR por nivel, swap de stats y reversión."""
from engine.content import (cr_a_numero, cr_max_forma_salvaje,
                            formas_salvajes_disponibles, MONSTRUOS)


def test_cr_a_numero():
    assert cr_a_numero("1/8") == 0.125
    assert cr_a_numero("1/4") == 0.25
    assert cr_a_numero("1/2") == 0.5
    assert cr_a_numero("2") == 2.0


def test_cr_max_por_nivel():
    assert cr_max_forma_salvaje(2) == 0.25
    assert cr_max_forma_salvaje(4) == 0.5
    assert cr_max_forma_salvaje(8) == 1.0
    assert cr_max_forma_salvaje(20) == 1.0


def test_formas_disponibles_escalan_con_nivel():
    n2 = formas_salvajes_disponibles(2)
    n8 = formas_salvajes_disponibles(8)
    # a nivel 2 no debe haber bestias de CR > 1/4
    assert all(cr_a_numero(MONSTRUOS[b]["cr"]) <= 0.25 for b in n2)
    # a nivel 8 aparecen bestias de CR 1
    assert "oso_pardo" in n8
    assert set(n2).issubset(set(n8))


def test_transformar_y_revertir_round_trip():
    from app.routers.actions import _revertir_forma_salvaje
    from app.models import Character

    # druida nivel 8 en su forma normal
    char = Character(
        nombre="Faelar", raza="humano (estandar)", clase="druida", nivel=8,
        atributos={"FUE": 10, "DES": 14, "CON": 12, "INT": 12, "SAB": 16, "CAR": 10},
        pg_actual=44, pg_max=52, velocidad_m=9, dado_golpe="d8", dados_golpe_disp=8,
        competencias={"habilidades": [], "salvaciones": ["INT", "SAB"],
                      "armas": ["simple"], "armaduras": ["ligera", "media"]},
        condiciones=[], armadura="cuero", escudo=False, arma_equipada="baston",
        inventario=[], monedas={}, slots={}, conocidos=[], preparados=[],
        recursos_clase={"forma_salvaje": {"usados": 0, "max": 2, "reset": "corto"}},
    )

    # transformación (misma lógica que el endpoint)
    beast = MONSTRUOS["oso_pardo"]
    char.recursos_clase = {
        **char.recursos_clase,
        "_forma_salvaje": {
            "beast": "oso_pardo", "nombre": beast["nombre"],
            "ca_fija": beast["ca_fija"],
            "backup": {"pg_actual": char.pg_actual, "pg_max": char.pg_max,
                       "atributos": dict(char.atributos),
                       "arma_equipada": char.arma_equipada,
                       "armadura": char.armadura, "escudo": char.escudo,
                       "velocidad_m": char.velocidad_m}}}
    char.atributos = {**char.atributos,
                      **{k: beast["atributos"][k] for k in ("FUE", "DES", "CON")}}
    char.pg_max = char.pg_actual = beast["pg"]
    char.armadura = None
    char.arma_equipada = beast["armas"][0]
    char.velocidad_m = beast["velocidad_m"]

    # en forma de oso: FUE de la bestia, SAB conservada
    assert char.atributos["FUE"] == 19
    assert char.atributos["SAB"] == 16
    assert char.pg_max == 34

    # hidratación aplica la CA de la bestia
    from app.hydration import hidratar_personaje
    from engine.rules import calcular_ca
    assert calcular_ca(hidratar_personaje(char)) == beast["ca_fija"]

    # revertir restaura la forma original
    forma = _revertir_forma_salvaje(char)
    assert forma["beast"] == "oso_pardo"
    assert char.atributos["FUE"] == 10
    assert char.pg_max == 52
    assert char.pg_actual == 44
    assert char.arma_equipada == "baston"
    assert char.velocidad_m == 9
    assert "_forma_salvaje" not in char.recursos_clase
