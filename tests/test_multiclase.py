"""Multiclase: requisitos, nivel de lanzador combinado y espacios del PHB."""
from engine.content import (cumple_requisitos_multiclase,
                            nivel_lanzador_multiclase, slots_multiclase)


def test_requisitos_multiclase():
    ok, _ = cumple_requisitos_multiclase("mago", {"INT": 13})
    assert ok
    ok, falta = cumple_requisitos_multiclase("mago", {"INT": 12})
    assert not ok and "INT" in falta
    # guerrero acepta FUE o DES
    assert cumple_requisitos_multiclase("guerrero", {"FUE": 13, "DES": 8})[0]
    assert cumple_requisitos_multiclase("guerrero", {"FUE": 8, "DES": 13})[0]
    assert not cumple_requisitos_multiclase("guerrero", {"FUE": 8, "DES": 8})[0]
    # paladín necesita FUE y CAR
    assert not cumple_requisitos_multiclase("paladin", {"FUE": 13, "CAR": 10})[0]


def test_nivel_lanzador_combinado():
    # guerrero 4 (no lanza) + mago 3 (completo) => nivel de lanzador 3
    assert nivel_lanzador_multiclase({"guerrero": 4, "mago": 3}) == 3
    # paladín 6 (medio) => 3
    assert nivel_lanzador_multiclase({"paladin": 6}) == 3
    # clérigo 5 + druida 5 (dos completos) => 10
    assert nivel_lanzador_multiclase({"clerigo": 5, "druida": 5}) == 10


def test_slots_multiclase_full_y_marcial():
    # Guerrero 4 / Mago 3 => slots como lanzador completo de nivel 3
    s = slots_multiclase({"guerrero": 4, "mago": 3})
    assert s["1"]["max"] == 4
    assert s["2"]["max"] == 2   # lanzador nivel 3 => {1:4, 2:2}
    assert "3" not in s   # nivel de lanzador 3 aún no da espacios de nivel 3


def test_slots_multiclase_incluye_pacto_brujo():
    # Hechicero 2 (lanzador completo) + Brujo 2 (magia de pacto nivel 1)
    s = slots_multiclase({"hechicero": 2, "brujo": 2})
    # lanzador combinado = 2 => tiene espacios de nivel 1
    assert s["1"]["max"] >= 3   # 3 del hechicero + 2 de pacto sumados aparte
