"""Hechicero: upcasting, Conjuro Empoderado, costos de metamagia."""
from engine.content import (COSTO_SLOT_EN_PH, costo_metamagia,
                            metamagias_conocidas_max)
from engine.rules import tirar_danio_conjuro


def test_upcasting_suma_dados():
    # manos_ardientes 3d6 base, +1d6 por nivel extra; con 2 niveles extra => 5d6
    d = tirar_danio_conjuro("3d6", "1d6", niveles_extra=2)
    assert len(d["dados"]) == 5
    assert d["niveles_extra"] == 2
    # sin escalado no suma dados
    base = tirar_danio_conjuro("3d6", "1d6", niveles_extra=0)
    assert len(base["dados"]) == 3


def test_upcasting_curacion():
    # curar_heridas 1d8 base, +1d8 por nivel extra; 3 niveles extra => 4 dados
    d = tirar_danio_conjuro("1d8", "1d8", niveles_extra=3)
    assert len(d["dados"]) == 4


def test_empoderado_sube_el_promedio():
    # re-tirar los dados más bajos debe subir el promedio de daño
    base = sum(sum(tirar_danio_conjuro("6d6")["dados"]) for _ in range(400))
    emp = sum(sum(tirar_danio_conjuro("6d6", empoderar=3)["dados"])
              for _ in range(400))
    assert emp > base
    # empoderar no cambia la cantidad de dados
    assert len(tirar_danio_conjuro("6d6", empoderar=3)["dados"]) == 6


def test_costo_slot_en_ph():
    assert COSTO_SLOT_EN_PH[1] == 2
    assert COSTO_SLOT_EN_PH[3] == 5
    assert COSTO_SLOT_EN_PH[5] == 7


def test_costo_metamagia_gemelo_es_nivel():
    # gemelo cuesta el nivel del conjuro (mín 1)
    assert costo_metamagia("gemelo", 3) == 3
    assert costo_metamagia("gemelo", 0) == 1
    # empoderado cuesta 1 fijo
    assert costo_metamagia("empoderado", 5) == 1
    assert costo_metamagia("elevado", 2) == 3


def test_metamagias_conocidas_por_nivel():
    assert metamagias_conocidas_max(2) == 0
    assert metamagias_conocidas_max(3) == 2
    assert metamagias_conocidas_max(10) == 3
    assert metamagias_conocidas_max(17) == 4
