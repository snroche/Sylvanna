import pytest

from engine.content import ARMADURAS, ARMAS, slots_iniciales
from engine.entities import Criatura, SpellState
from engine.rules import (
    aplicar_danio,
    bc,
    calcular_ca,
    check_concentracion,
    curar,
    descanso_corto,
    descanso_largo,
    gastar_slot,
    mod,
    nivel_por_xp,
    puede_lanzar,
    resolver_ataque,
    salvacion_muerte,
    tirada_habilidad,
    tirada_salvacion,
)


def pj(**kw) -> Criatura:
    base = dict(
        id="pj1", nombre="Thorin", nivel=1,
        atributos={"FUE": 16, "DES": 12, "CON": 14, "INT": 8, "SAB": 10, "CAR": 13},
        pg_actual=12, pg_max=12, dados_golpe_disp=1, dado_golpe="d10",
        competencias={"habilidades": ["atletismo"], "salvaciones": ["FUE", "CON"],
                      "armas": ["marcial", "simple"], "armaduras": ["ligera", "media"]},
    )
    base.update(kw)
    return Criatura(**base)


def goblin() -> Criatura:
    return Criatura(
        id="npc1", nombre="Goblin", nivel=1,
        atributos={"FUE": 8, "DES": 14, "CON": 10, "INT": 10, "SAB": 8, "CAR": 8},
        pg_actual=7, pg_max=7, ca_fija=15,
    )


# ---------------------------------------------------------------- básicos

@pytest.mark.parametrize("puntaje,esperado", [
    (8, -1), (10, 0), (12, 1), (14, 2), (16, 3), (18, 4), (20, 5), (7, -2), (9, -1),
])
def test_mod(puntaje, esperado):
    assert mod(puntaje) == esperado


@pytest.mark.parametrize("nivel,esperado", [
    (1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (13, 5), (17, 6),
])
def test_bc(nivel, esperado):
    assert bc(nivel) == esperado


def test_nivel_por_xp():
    assert nivel_por_xp(0) == 1
    assert nivel_por_xp(299) == 1
    assert nivel_por_xp(300) == 2
    assert nivel_por_xp(900) == 3
    assert nivel_por_xp(70_000) == 10


# ---------------------------------------------------------------- CA

def test_ca_sin_armadura():
    assert calcular_ca(pj()) == 11  # 10 + DES(+1)


def test_ca_ligera_sin_limite_des():
    c = pj(atributos={"FUE": 10, "DES": 18, "CON": 10, "INT": 10, "SAB": 10, "CAR": 10},
           armadura=ARMADURAS["cuero_tachonado"])
    assert calcular_ca(c) == 16  # 12 + 4


def test_ca_media_limita_des_a_2():
    c = pj(atributos={"FUE": 10, "DES": 18, "CON": 10, "INT": 10, "SAB": 10, "CAR": 10},
           armadura=ARMADURAS["coraza"])
    assert calcular_ca(c) == 16  # 14 + min(4, 2)


def test_ca_pesada_ignora_des():
    c = pj(atributos={"FUE": 10, "DES": 18, "CON": 10, "INT": 10, "SAB": 10, "CAR": 10},
           armadura=ARMADURAS["cota_de_placas"])
    assert calcular_ca(c) == 18


def test_ca_escudo():
    c = pj(escudo=True)
    assert calcular_ca(c) == 13  # 10 + 1 + 2


def test_ca_fija_monstruo():
    assert calcular_ca(goblin()) == 15


# ---------------------------------------------------------------- ataques

def test_ataque_estructura_y_matematica():
    a, o = pj(), goblin()
    r = resolver_ataque(a, o, ARMAS["espada_larga"])
    assert r["atributo"] == "FUE"
    assert r["bono_ataque"] == 5  # FUE +3, BC +2 (competente en marcial)
    assert r["total"] == r["natural"] + 5
    assert r["ca_objetivo"] == 15
    if r["impacta"]:
        assert r["danio"]["total_final"] >= 1
        assert o.pg_actual < 7 or o.pg_actual == 0
    else:
        assert o.pg_actual == 7


def test_ataque_finura_usa_des_si_conviene():
    c = pj(atributos={"FUE": 8, "DES": 16, "CON": 10, "INT": 10, "SAB": 10, "CAR": 10})
    r = resolver_ataque(c, goblin(), ARMAS["daga"])
    assert r["atributo"] == "DES"


def test_ataque_distancia_siempre_des():
    r = resolver_ataque(pj(), goblin(), ARMAS["arco_largo"])
    assert r["atributo"] == "DES"


def test_ataque_sin_competencia_no_suma_bc():
    c = pj(competencias={"habilidades": [], "salvaciones": [], "armas": [],
                         "armaduras": []})
    r = resolver_ataque(c, goblin(), ARMAS["espada_larga"])
    assert r["bono_ataque"] == 3  # solo FUE


def test_critico_duplica_dados():
    # Fuerza estadística: sobre muchas corridas, todo crítico debe tener 2+ dados
    for _ in range(500):
        o = goblin()
        o.pg_actual = 1000
        o.pg_max = 1000
        r = resolver_ataque(pj(), o, ARMAS["mazo"])  # 1d6
        if r["critico"] and r["impacta"]:
            assert len(r["danio"]["dados"]) == 2
            return
    pytest.skip("no salió crítico en 500 corridas (improbable)")


def test_pifia_falla_aunque_bono_alcance():
    encontro_pifia = False
    for _ in range(500):
        o = goblin()
        o.ca_fija = 1  # cualquier total impactaría
        r = resolver_ataque(pj(), o, ARMAS["mazo"])
        if r["pifia"]:
            assert not r["impacta"]
            encontro_pifia = True
            break
    assert encontro_pifia, "no salió pifia en 500 corridas (improbable)"


def test_danio_minimo_1():
    debil = pj(atributos={"FUE": 4, "DES": 10, "CON": 10, "INT": 10, "SAB": 10,
                          "CAR": 10})  # FUE -3
    for _ in range(300):
        o = goblin()
        o.ca_fija = 1
        r = resolver_ataque(debil, o, ARMAS["daga"])  # 1d4-3 podría dar <= 0
        if r["impacta"]:
            assert r["danio"]["total_final"] >= 1


# ---------------------------------------------------------------- daño y muerte

def test_aplicar_danio_a_cero_agrega_condiciones():
    c = pj()
    res = aplicar_danio(c, 20)
    assert c.pg_actual == 0
    assert c.tiene_condicion("inconsciente")
    assert c.tiene_condicion("derribado")
    assert "cae_inconsciente" in res["eventos"]


def test_danio_no_negativo():
    with pytest.raises(ValueError):
        aplicar_danio(pj(), -5)


def test_danio_con_concentracion_pide_check():
    c = pj(spell_state=SpellState(concentracion_activa={"hechizo": "bendecir",
                                                        "desde_ronda": 1}))
    res = aplicar_danio(c, 3)
    assert "requiere_check_concentracion" in res["eventos"]
    assert c.spell_state.concentracion_activa is not None  # aún no se rompió


def test_caer_a_cero_rompe_concentracion_sin_tirada():
    c = pj(spell_state=SpellState(concentracion_activa={"hechizo": "bendecir",
                                                        "desde_ronda": 1}))
    res = aplicar_danio(c, 99)
    assert c.spell_state.concentracion_activa is None
    assert "concentracion_rota" in res["eventos"]


def test_check_concentracion_cd_minimo_10():
    c = pj(spell_state=SpellState(concentracion_activa={"hechizo": "bendecir",
                                                        "desde_ronda": 1}))
    r = check_concentracion(c, danio=4)
    assert r["cd"] == 10


def test_check_concentracion_cd_mitad_danio():
    c = pj(spell_state=SpellState(concentracion_activa={"hechizo": "bendecir",
                                                        "desde_ronda": 1}))
    r = check_concentracion(c, danio=30)
    assert r["cd"] == 15


def test_curar_despierta():
    c = pj()
    aplicar_danio(c, 20)
    res = curar(c, 5)
    assert c.pg_actual == 5
    assert not c.tiene_condicion("inconsciente")
    assert "recupera_consciencia" in res["eventos"]


def test_curar_no_supera_maximo():
    c = pj()
    c.pg_actual = 10
    curar(c, 100)
    assert c.pg_actual == c.pg_max


def test_salvaciones_muerte_acumulan():
    exitos_vistos = fallos_vistos = False
    for _ in range(300):
        c = pj()
        c.pg_actual = 0
        r = salvacion_muerte(c)
        if r["natural"] >= 10 and r["natural"] != 20:
            assert c.muerte_exitos == 1
            exitos_vistos = True
        elif r["natural"] == 1:
            assert c.muerte_fallos == 2
        elif r["natural"] < 10:
            assert c.muerte_fallos == 1
            fallos_vistos = True
        if exitos_vistos and fallos_vistos:
            break
    assert exitos_vistos and fallos_vistos


def test_tres_fallos_es_muerte():
    c = pj()
    c.pg_actual = 0
    c.muerte_fallos = 2
    for _ in range(500):
        c2 = pj()
        c2.pg_actual = 0
        c2.muerte_fallos = 2
        r = salvacion_muerte(c2)
        if r["evento"] == "muerte":
            assert not c2.vivo
            return
    pytest.skip("no salió fallo en 500 corridas")


def test_natural_20_despierta_con_1pg():
    for _ in range(1000):
        c = pj()
        c.pg_actual = 0
        c.condiciones.append({"tipo": "inconsciente", "origen": "0_pg"})
        r = salvacion_muerte(c)
        if r["natural"] == 20:
            assert c.pg_actual == 1
            assert not c.tiene_condicion("inconsciente")
            return
    pytest.skip("no salió 20 natural en 1000 corridas")


# ---------------------------------------------------------------- habilidades

def test_habilidad_suma_bc_si_competente():
    c = pj()  # competente en atletismo, FUE +3, BC +2
    r = tirada_habilidad(c, "atletismo", cd=10)
    assert r["bono"] == 5
    r2 = tirada_habilidad(c, "sigilo", cd=10)  # no competente, DES +1
    assert r2["bono"] == 1


def test_habilidad_desconocida():
    with pytest.raises(ValueError):
        tirada_habilidad(pj(), "hackear", cd=10)


def test_gradacion_de_fallos():
    grados = set()
    for _ in range(2000):
        r = tirada_habilidad(pj(), "sigilo", cd=16)
        grados.add(r["grado"])
    assert "fallo_simple" in grados or "fallo_con_complicacion" in grados
    assert "fallo_grave" in grados or "fallo_critico" in grados


def test_salvacion_auto_fallo_paralizado():
    c = pj(condiciones=[{"tipo": "paralizado", "origen": "test"}])
    r = tirada_salvacion(c, "DES", cd=10)
    assert r.get("auto_fallo") and not r["exito"]
    r2 = tirada_salvacion(c, "SAB", cd=10)  # SAB sí se tira
    assert "auto_fallo" not in r2


# ---------------------------------------------------------------- magia

def mago() -> Criatura:
    return pj(
        id="pj2", nombre="Elara", dado_golpe="d6",
        atributos={"FUE": 8, "DES": 14, "CON": 12, "INT": 16, "SAB": 10, "CAR": 10},
        spell_state=SpellState(
            slots=slots_iniciales("mago", 1),
            preparados=["proyectil_magico", "escudo"],
        ),
    )


def test_slots_iniciales_por_clase():
    assert slots_iniciales("mago", 1) == {"1": {"usados": 0, "max": 2}}
    assert slots_iniciales("mago", 5) == {"1": {"usados": 0, "max": 4},
                                          "2": {"usados": 0, "max": 3},
                                          "3": {"usados": 0, "max": 2}}
    assert slots_iniciales("guerrero", 5) == {}
    assert slots_iniciales("paladin", 1) == {}
    assert slots_iniciales("paladin", 2) == {"1": {"usados": 0, "max": 2}}
    assert slots_iniciales("brujo", 5) == {"3": {"usados": 0, "max": 2}}


def test_gastar_slot_descuenta_y_agota():
    m = mago()
    assert gastar_slot(m, 1)["ok"]
    assert gastar_slot(m, 1)["ok"]
    r = gastar_slot(m, 1)
    assert not r["ok"] and r["motivo"] == "slots_agotados"


def test_gastar_slot_nivel_inexistente():
    r = gastar_slot(mago(), 3)
    assert not r["ok"]


def test_no_lanzador_no_gasta():
    assert not gastar_slot(pj(), 1)["ok"]


def test_puede_lanzar_validaciones():
    m = mago()
    assert puede_lanzar(m, "proyectil_magico")["ok"]
    assert puede_lanzar(m, "bola_de_fuego")["motivo"] == "hechizo_no_disponible"
    m.condiciones.append({"tipo": "silenciado", "origen": "test"})
    assert puede_lanzar(m, "escudo")["motivo"] == "silenciado"


# ---------------------------------------------------------------- descansos

def test_descanso_corto_gasta_dados_y_cura():
    c = pj(nivel=3, dados_golpe_disp=3)
    c.pg_actual = 1
    r = descanso_corto(c, 2)
    assert r["ok"]
    assert c.dados_golpe_disp == 1
    assert c.pg_actual > 1
    assert len(r["tiradas"]) == 2


def test_descanso_corto_sin_dados():
    c = pj(dados_golpe_disp=0)
    assert not descanso_corto(c, 1)["ok"]


def test_descanso_largo_restaura_todo():
    m = mago()
    m.nivel = 4
    m.pg_actual = 2
    m.dados_golpe_disp = 0
    gastar_slot(m, 1)
    m.spell_state.concentracion_activa = {"hechizo": "bendecir", "desde_ronda": 1}
    descanso_largo(m)
    assert m.pg_actual == m.pg_max
    assert m.dados_golpe_disp == 2  # nivel 4 // 2
    assert m.spell_state.slots["1"]["usados"] == 0
    assert m.spell_state.concentracion_activa is None


# ---------------------------------------------------------------- razas y point buy

from engine.content import (COSTO_PUNTOS, RAZAS, aplicar_bonos_raciales,
                            validar_point_buy)


def test_point_buy_valido():
    ok, msg = validar_point_buy(
        {"FUE": 15, "DES": 14, "CON": 13, "INT": 12, "SAB": 10, "CAR": 8})
    assert ok, msg  # 9+7+5+4+2+0 = 27


def test_point_buy_excedido():
    # tres 15 = 27 puntos justos: válido
    ok, _ = validar_point_buy(
        {"FUE": 15, "DES": 15, "CON": 15, "INT": 8, "SAB": 8, "CAR": 8})
    assert ok
    # subir un 8 a 9 lo pasa a 28: inválido
    ok2, _ = validar_point_buy(
        {"FUE": 15, "DES": 15, "CON": 15, "INT": 9, "SAB": 8, "CAR": 8})
    assert not ok2


def test_point_buy_fuera_de_rango():
    ok, msg = validar_point_buy(
        {"FUE": 16, "DES": 8, "CON": 8, "INT": 8, "SAB": 8, "CAR": 8})
    assert not ok and "16" in msg


def test_bonos_raciales_enano_montanas():
    base = {"FUE": 14, "DES": 10, "CON": 14, "INT": 10, "SAB": 10, "CAR": 10}
    finales, vel, rasgos = aplicar_bonos_raciales(base, "enano",
                                                  "enano_de_las_montanas")
    assert finales["CON"] == 16 and finales["FUE"] == 16
    assert vel == 7
    assert "veneno" in rasgos


def test_raza_con_subrazas_la_requiere():
    base = {a: 10 for a in ("FUE", "DES", "CON", "INT", "SAB", "CAR")}
    with pytest.raises(ValueError):
        aplicar_bonos_raciales(base, "elfo", None)


def test_semielfo_eleccion():
    base = {a: 10 for a in ("FUE", "DES", "CON", "INT", "SAB", "CAR")}
    finales, _, _ = aplicar_bonos_raciales(base, "semielfo", "estandar",
                                           bonos_eleccion=["FUE", "INT"])
    assert finales["CAR"] == 12 and finales["FUE"] == 11 and finales["INT"] == 11
    with pytest.raises(ValueError):  # no puede elegir CAR (ya lo tiene)
        aplicar_bonos_raciales(base, "semielfo", "estandar",
                               bonos_eleccion=["CAR", "FUE"])
    with pytest.raises(ValueError):  # deben ser dos distintos
        aplicar_bonos_raciales(base, "semielfo", "estandar",
                               bonos_eleccion=["FUE", "FUE"])


def test_raza_desconocida():
    base = {a: 10 for a in ("FUE", "DES", "CON", "INT", "SAB", "CAR")}
    with pytest.raises(ValueError):
        aplicar_bonos_raciales(base, "tabaxi", None)


def test_tope_20():
    base = {"FUE": 18, "DES": 10, "CON": 18, "INT": 10, "SAB": 10, "CAR": 10}
    finales, _, _ = aplicar_bonos_raciales(base, "enano", "enano_de_las_montanas")
    assert finales["FUE"] == 20  # 18+2 topea en 20


# ---------------------------------------------------------------- rasgos de clase

from engine.content import ARMAS as _ARMAS
from engine.rules import resolver_ataque as _ra, calcular_ca as _ca


def test_ca_barbaro_sin_armadura():
    c = pj(atributos={"FUE": 16, "DES": 14, "CON": 16, "INT": 8, "SAB": 10,
                      "CAR": 10})
    c.ca_alternativa = "barbaro"
    assert _ca(c) == 15  # 10 + DES(+2) + CON(+3)


def test_ca_monje_no_aplica_con_escudo():
    c = pj(atributos={"FUE": 10, "DES": 16, "CON": 10, "INT": 10, "SAB": 16,
                      "CAR": 10})
    c.ca_alternativa = "monje"
    assert _ca(c) == 16  # 10 + 3 + 3
    c.escudo = True
    assert _ca(c) == 15  # vuelve a 10 + DES + escudo


def test_estilo_defensa_solo_con_armadura():
    c = pj(estilo_combate="defensa")
    ca_sin = _ca(c)
    c.armadura = ARMADURAS["cuero"]
    assert _ca(c) == 11 + 1 + 1  # cuero + DES(+1) + estilo


def test_furia_suma_2_melee_no_distancia():
    for arma, espera_extra in ((_ARMAS["mazo"], True), (_ARMAS["arco_corto"], False)):
        for _ in range(200):
            a = pj(condiciones=[{"tipo": "furia", "origen": "t"}])
            o = goblin(); o.ca_fija = 1; o.pg_actual = 100; o.pg_max = 100
            r = _ra(a, o, arma)
            if r["impacta"]:
                motivos = [e["motivo"] for e in r["danio"]["extras"]]
                assert ("furia" in motivos) == espera_extra
                break


def test_furtivo_agrega_dados_y_dobla_en_critico():
    vio_normal = vio_critico = False
    for _ in range(2000):
        a = pj(nivel=3)
        a.nivel_furtivo = 2  # nivel 3 → 2d6
        o = goblin(); o.ca_fija = 1; o.pg_actual = 999; o.pg_max = 999
        r = _ra(a, o, _ARMAS["daga"], furtivo=True)
        if not r["impacta"]:
            continue
        f = next((e for e in r["danio"]["extras"] if e["motivo"] == "furtivo"), None)
        assert f is not None
        if r["critico"]:
            assert len(f["dados"]) == 4; vio_critico = True
        else:
            assert len(f["dados"]) == 2; vio_normal = True
        if vio_normal and vio_critico:
            return
    assert vio_normal  # crítico puede no salir; normal sí o sí


def test_inspirado_suma_d6_y_se_consume():
    for _ in range(50):
        a = pj(condiciones=[{"tipo": "inspirado", "origen": "bardo"}])
        r = _ra(a, goblin(), _ARMAS["mazo"])
        assert r["inspiracion"] is not None and 1 <= r["inspiracion"] <= 6
        assert r["total"] == r["natural"] + r["bono_ataque"] + r["inspiracion"]
        assert not a.tiene_condicion("inspirado")


def test_ayudado_da_ventaja_y_se_consume():
    a = pj(condiciones=[{"tipo": "ayudado", "origen": "x"}])
    r = _ra(a, goblin(), _ARMAS["mazo"])
    assert len(r["tiradas"]) == 2 and r["natural"] == max(r["tiradas"])
    assert not a.tiene_condicion("ayudado")


def test_estilo_arqueria():
    a = pj(estilo_combate="arqueria")
    r = _ra(a, goblin(), _ARMAS["arco_largo"])
    assert r["bono_ataque"] == mod(a.atributos["DES"]) + 2 + 2  # DES+BC+estilo


# ---------------------------------------------------------------- statblock

from engine.rules import ataque_statblock


def test_ataque_statblock():
    o = pj()
    o.pg_actual = 100; o.pg_max = 100
    for _ in range(100):
        a = goblin()
        r = ataque_statblock(a, o, "Mordida", bono=4, danio_expr="1d6+2")
        assert r["total"] == r["natural"] + 4
        if r["impacta"]:
            assert r["danio"]["total_final"] >= 1
            return
    pytest.skip("no impactó en 100 (improbable)")


def test_statblock_respeta_esquivar():
    o = pj(condiciones=[{"tipo": "esquivando", "origen": "t"}])
    r = ataque_statblock(goblin(), o, "Mordida", 4, "1d6+2")
    assert r["ventaja"] == -1
