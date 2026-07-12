"""Tests de las mecánicas de combate agregadas: Castigo Divino, Ataque
Temerario, resistencia de Furia, estilos Gran Arma / Dos Armas."""
from engine.content import ARMAS
from engine.entities import Criatura
from engine.rules import (dados_castigo_divino, mod, resolver_ataque)


def pj(**kw) -> Criatura:
    base = dict(
        id="pj1", nombre="Aric", nivel=5,
        atributos={"FUE": 18, "DES": 12, "CON": 14, "INT": 8, "SAB": 10, "CAR": 16},
        pg_actual=40, pg_max=40, dado_golpe="d10",
        competencias={"habilidades": [], "salvaciones": ["FUE", "CON"],
                      "armas": ["marcial", "simple"], "armaduras": []},
    )
    base.update(kw)
    return Criatura(**base)


def maniqui(ca=1, pg=200, **kw) -> Criatura:
    base = dict(id="npc1", nombre="Maniquí", nivel=1,
                atributos={"FUE": 10, "DES": 10, "CON": 10,
                           "INT": 10, "SAB": 10, "CAR": 10},
                pg_actual=pg, pg_max=pg, ca_fija=ca)
    base.update(kw)
    return Criatura(**base)


# ---------------------------------------------------------------- Castigo Divino

def test_dados_castigo_escala_por_slot():
    obj = maniqui()
    assert dados_castigo_divino(1, obj) == "2d8"
    assert dados_castigo_divino(2, obj) == "3d8"
    assert dados_castigo_divino(4, obj) == "5d8"
    assert dados_castigo_divino(5, obj) == "5d8"   # tope 5d8


def test_dados_castigo_extra_vs_no_muerto():
    no_muerto = maniqui(tipo_criatura="no_muerto")
    assert dados_castigo_divino(1, no_muerto) == "3d8"
    assert dados_castigo_divino(5, no_muerto) == "6d8"  # tope 6d8
    infernal = maniqui(tipo_criatura="Fiend")
    assert dados_castigo_divino(1, infernal) == "3d8"


def test_castigo_divino_suma_danio_radiante():
    atk = pj()
    obj = maniqui(ca=1)   # CA 1: siempre impacta
    r = resolver_ataque(atk, obj, ARMAS["espada_larga"], smite_dados="10d8")
    assert r["impacta"]
    smite = r["danio"]["castigo_divino"]
    assert smite is not None
    assert smite["tipo_danio"] == "radiante"
    # 10d8 => al menos 10 de daño radiante encima del arma
    assert smite["valor"] >= 10


def test_castigo_divino_no_aplica_a_distancia():
    for _ in range(50):
        r = resolver_ataque(pj(), maniqui(ca=1), ARMAS["arco_largo"],
                            smite_dados="5d8")
        if r["danio"]:
            assert r["danio"]["castigo_divino"] is None
            return
    raise AssertionError("nunca impactó con el arco")


# ---------------------------------------------------------------- Ataque Temerario

def test_imprudente_da_ventaja_al_atacante():
    # con CA alta, la ventaja del temerario debe subir la tasa de impacto
    impactos_normal = 0
    impactos_imprudente = 0
    for _ in range(400):
        if resolver_ataque(pj(), maniqui(ca=20), ARMAS["espada_larga"])["impacta"]:
            impactos_normal += 1
        if resolver_ataque(pj(), maniqui(ca=20), ARMAS["espada_larga"],
                           imprudente=True)["impacta"]:
            impactos_imprudente += 1
    assert impactos_imprudente > impactos_normal


def test_objetivo_imprudente_recibe_ventaja():
    barbaro = pj()
    barbaro.condiciones = [{"tipo": "imprudente"}]
    impactos = sum(
        resolver_ataque(maniqui(ca=10), barbaro, ARMAS["espada_larga"])["impacta"]
        for _ in range(200))
    impactos_base = sum(
        resolver_ataque(maniqui(ca=10), pj(), ARMAS["espada_larga"])["impacta"]
        for _ in range(200))
    assert impactos > impactos_base


# ---------------------------------------------------------------- Furia (resistencia)

def test_furia_resistencia_via_resistencias():
    # el bárbaro en furia lleva las resistencias físicas en su lista
    barbaro = pj(resistencias=["contundente", "perforante", "cortante"])
    r = resolver_ataque(maniqui(ca=1, atributos={"FUE": 20, "DES": 10, "CON": 10,
                                                 "INT": 10, "SAB": 10, "CAR": 10}),
                        barbaro, ARMAS["mandoble"])
    if r["impacta"]:
        assert r["danio"]["resistido"] is True


# ---------------------------------------------------------------- estilos

def test_gran_arma_retira_unos_y_doses():
    # promedio de daño con gran_arma debe superar al normal a dos manos
    total_normal = total_gwf = 0
    for _ in range(400):
        rn = resolver_ataque(pj(), maniqui(ca=1), ARMAS["mandoble"])
        if rn["danio"]:
            total_normal += sum(rn["danio"]["dados"])
        atk = pj(estilo_combate="gran_arma")
        rg = resolver_ataque(atk, maniqui(ca=1), ARMAS["mandoble"])
        if rg["danio"]:
            total_gwf += sum(rg["danio"]["dados"])
    assert total_gwf > total_normal


def _primer_impacto(atk_factory, **kw):
    for _ in range(50):
        r = resolver_ataque(atk_factory(), maniqui(ca=1),
                            ARMAS["espada_corta"], **kw)
        if r["danio"]:
            return r
    raise AssertionError("nunca impactó contra CA 1")


def test_mano_secundaria_no_suma_mod_sin_estilo():
    r = _primer_impacto(pj, mano_secundaria=True)   # FUE 18 => +4
    assert r["danio"]["mod_atributo"] == 0   # sin estilo, no suma el +4


def test_mano_secundaria_suma_mod_con_estilo_dos_armas():
    r = _primer_impacto(lambda: pj(estilo_combate="dos_armas"),
                        mano_secundaria=True)
    assert r["danio"]["mod_atributo"] == mod(pj().atributos["FUE"])
