"""Inspiración Heroica (ventaja que se consume) y helpers de clérigo."""
from engine.content import ARMAS
from engine.entities import Criatura
from engine.rules import resolver_ataque, tirada_habilidad


def pj(**kw) -> Criatura:
    base = dict(
        id="pj1", nombre="Aric", nivel=5,
        atributos={"FUE": 16, "DES": 12, "CON": 14, "INT": 8, "SAB": 12, "CAR": 10},
        pg_actual=40, pg_max=40, dado_golpe="d10",
        competencias={"habilidades": ["medicina"], "salvaciones": ["FUE"],
                      "armas": ["marcial", "simple"], "armaduras": []},
    )
    base.update(kw)
    return Criatura(**base)


def maniqui(ca=20) -> Criatura:
    return Criatura(id="n", nombre="M", nivel=1,
                    atributos={"FUE": 10, "DES": 10, "CON": 10,
                               "INT": 10, "SAB": 10, "CAR": 10},
                    pg_actual=100, pg_max=100, ca_fija=ca)


def test_inspiracion_heroica_da_ventaja_al_atacar_y_se_consume():
    c = pj(condiciones=[{"tipo": "inspiracion_heroica"}])
    r = resolver_ataque(c, maniqui(), ARMAS["espada_larga"])
    assert r["ventaja"] == 1                     # tiró con ventaja
    assert not c.tiene_condicion("inspiracion_heroica")  # se consumió


def test_inspiracion_heroica_da_ventaja_en_habilidad_y_se_consume():
    c = pj(condiciones=[{"tipo": "inspiracion_heroica"}])
    r = tirada_habilidad(c, "medicina", cd=10)
    assert r["ventaja"] == 1
    assert not c.tiene_condicion("inspiracion_heroica")


def test_sin_inspiracion_no_hay_ventaja():
    c = pj()
    r = resolver_ataque(c, maniqui(), ARMAS["espada_larga"])
    assert r["ventaja"] == 0


def test_medicina_es_habilidad_valida():
    # estabilizar usa una tirada de Medicina (SAB)
    c = pj()
    r = tirada_habilidad(c, "medicina", cd=10)
    assert r["atributo"] == "SAB"


def test_es_no_muerto_detecta_tipo():
    from app.routers.actions import _es_no_muerto
    from app.models import NPC
    esq = NPC(nombre="Esqueleto", tipo="monstruo",
              stats={"tipo_criatura": "no_muerto"})
    goblin = NPC(nombre="Goblin", tipo="monstruo",
                 stats={"tipo_criatura": "humanoide"})
    assert _es_no_muerto(esq) is True
    assert _es_no_muerto(goblin) is False
