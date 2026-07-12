"""Progresión 6-20: XP, espacios de conjuro, ataques por acción, conocidos."""
import pytest

from engine.content import (ataques_por_accion, limite_conjuros,
                            slots_iniciales)
from engine.rules import nivel_por_xp


def test_nivel_por_xp_hasta_20():
    assert nivel_por_xp(85_000) == 11
    assert nivel_por_xp(195_000) == 16
    assert nivel_por_xp(354_999) == 19
    assert nivel_por_xp(355_000) == 20
    assert nivel_por_xp(10_000_000) == 20


def test_slots_completo_nivel_20():
    s = slots_iniciales("mago", 20)
    assert s["9"]["max"] == 1
    assert s["1"]["max"] == 4
    assert s["6"]["max"] == 2
    assert s["7"]["max"] == 2
    # un lanzador completo de nivel 20 tiene espacios de nivel 1 a 9
    assert set(s) == {"1", "2", "3", "4", "5", "6", "7", "8", "9"}


def test_slots_medio_paladin_nivel_20():
    s = slots_iniciales("paladin", 20)
    assert s["5"]["max"] == 2
    assert "6" not in s   # medio lanzador no llega a nivel 6 de conjuro


def test_slots_brujo_escala():
    assert slots_iniciales("brujo", 2)["1"]["max"] == 2
    s11 = slots_iniciales("brujo", 11)
    assert s11["5"]["max"] == 3   # 3 espacios de nivel 5
    s20 = slots_iniciales("brujo", 20)
    assert s20["5"]["max"] == 4


def test_ataques_por_accion_guerrero():
    assert ataques_por_accion("guerrero", 4) == 1
    assert ataques_por_accion("guerrero", 5) == 2
    assert ataques_por_accion("guerrero", 11) == 3
    assert ataques_por_accion("guerrero", 20) == 4
    # otras clases con Ataque Extra llegan a 2
    assert ataques_por_accion("barbaro", 11) == 2
    assert ataques_por_accion("mago", 20) == 1


def test_conocidos_escala_a_20():
    assert limite_conjuros("bardo", 20, 3) == ("conocidos", 22)
    assert limite_conjuros("hechicero", 20, 3) == ("conocidos", 15)
    assert limite_conjuros("brujo", 20, 3) == ("conocidos", 15)
    # preparados escalan con mod + nivel
    assert limite_conjuros("mago", 20, 5) == ("preparados", 25)
