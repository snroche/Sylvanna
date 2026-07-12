"""Dotes (feats): ASI, competencia de salvación, PG (Vigoroso), iniciativa."""
import pytest

from engine.content import FEATS, efectos_feats
from app.feats import aplicar_feat
from app.models import Character
from app.hydration import hidratar_personaje
from engine.rules import iniciativa


def _char(**kw) -> Character:
    base = dict(
        nombre="Test", raza="humano (variante)", clase="guerrero", nivel=4,
        atributos={"FUE": 16, "DES": 13, "CON": 14, "INT": 10, "SAB": 10, "CAR": 8},
        pg_actual=36, pg_max=36, velocidad_m=9, dado_golpe="d10", dados_golpe_disp=4,
        competencias={"habilidades": [], "salvaciones": ["FUE", "CON"],
                      "armas": ["marcial", "simple"], "armaduras": ["pesada"]},
        condiciones=[], armadura=None, escudo=False, arma_equipada="espada_larga",
        inventario=[], monedas={}, slots={}, conocidos=[], preparados=[],
        recursos_clase={}, opciones_clase={}, feats=[],
    )
    base.update(kw)
    return Character(**base)


def test_catalogo_feats():
    for clave in ("resistente", "vigoroso", "alerta", "atleta", "actor"):
        assert clave in FEATS


def test_vigoroso_suma_pg_por_nivel():
    char = _char(nivel=4)
    res = aplicar_feat(char, "vigoroso")
    assert res["pg_ganados"] == 8         # +2 por nivel × 4
    assert char.pg_max == 44


def test_resistente_da_asi_y_competencia_salvacion():
    char = _char()
    aplicar_feat(char, "resistente", atributo="DES")
    assert char.atributos["DES"] == 14    # +1
    assert "DES" in char.competencias["salvaciones"]


def test_resistente_requiere_atributo_valido():
    char = _char()
    with pytest.raises(ValueError):
        aplicar_feat(char, "resistente", atributo=None)


def test_no_se_repite_una_dote():
    char = _char()
    aplicar_feat(char, "vigoroso")
    with pytest.raises(ValueError):
        aplicar_feat(char, "vigoroso")


def test_alerta_suma_iniciativa_via_hidratacion():
    char = _char()
    aplicar_feat(char, "alerta")
    assert efectos_feats(char.feats)["bono_iniciativa"] == 5
    cr = hidratar_personaje(char)
    assert cr.bono_iniciativa == 5
    # la iniciativa incluye el +5 (mín DES mod -? ; con DES 13 => +1, +5 => bono 6)
    r = iniciativa(cr)
    assert r["bono"] == 6


def test_requisito_de_atributo():
    # Grappler requiere FUE 13; un personaje con FUE 10 no puede tomarlo
    char = _char(atributos={"FUE": 10, "DES": 13, "CON": 14,
                            "INT": 10, "SAB": 10, "CAR": 8})
    with pytest.raises(ValueError):
        aplicar_feat(char, "luchador_agarrador")
