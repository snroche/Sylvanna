"""Linajes infernales de tiefling: bonos de atributo y resistencias."""
import pytest

from engine.content import (RAZAS, aplicar_bonos_raciales,
                            resistencias_de_raza)

BASE = {"FUE": 10, "DES": 12, "CON": 12, "INT": 13, "SAB": 10, "CAR": 13}


def test_tiefling_tiene_linajes():
    subs = RAZAS["tiefling"]["subrazas"]
    for linaje in ("asmodeus", "zariel", "levistus", "glasya", "fierna"):
        assert linaje in subs


def test_asmodeus_car2_int1():
    finales, _, _ = aplicar_bonos_raciales(BASE, "tiefling", "asmodeus")
    assert finales["CAR"] == 15   # +2
    assert finales["INT"] == 14   # +1


def test_zariel_da_fuerza():
    finales, _, _ = aplicar_bonos_raciales(BASE, "tiefling", "zariel")
    assert finales["FUE"] == 11   # +1 FUE
    assert finales["CAR"] == 15


def test_levistus_resiste_frio_y_fuego():
    res = resistencias_de_raza("tiefling (levistus)")
    assert "fuego" in res and "frio" in res


def test_tiefling_requiere_linaje():
    # al tener subrazas, elegir tiefling sin linaje es error
    with pytest.raises(ValueError):
        aplicar_bonos_raciales(BASE, "tiefling", None)
