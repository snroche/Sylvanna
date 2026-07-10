import pytest

from engine.dice import d20, roll


def test_roll_rango_y_estructura():
    for _ in range(200):
        r = roll("2d6+3")
        assert len(r["dados"]) == 2
        assert all(1 <= d <= 6 for d in r["dados"])
        assert r["total"] == sum(r["dados"]) + 3
        assert r["mod"] == 3


def test_roll_sin_modificador():
    r = roll("1d20")
    assert 1 <= r["total"] <= 20
    assert r["mod"] == 0


def test_roll_modificador_negativo():
    r = roll("1d4-2")
    assert r["total"] == r["dados"][0] - 2


@pytest.mark.parametrize("expr", ["d6", "2d7", "0d6", "abc", "1d6+", "101d6"])
def test_roll_expresiones_invalidas(expr):
    with pytest.raises(ValueError):
        roll(expr)


def test_d20_normal():
    r = d20()
    assert len(r["tiradas"]) == 1
    assert r["natural"] == r["tiradas"][0]
    assert r["critico"] == (r["natural"] == 20)
    assert r["pifia"] == (r["natural"] == 1)


def test_d20_ventaja_usa_mayor():
    for _ in range(100):
        r = d20(ventaja=1)
        assert len(r["tiradas"]) == 2
        assert r["natural"] == max(r["tiradas"])


def test_d20_desventaja_usa_menor():
    for _ in range(100):
        r = d20(ventaja=-1)
        assert r["natural"] == min(r["tiradas"])


def test_d20_ventaja_invalida():
    with pytest.raises(ValueError):
        d20(ventaja=2)
