"""Invocaciones del brujo (Explosión Agonizante, competencias) y Expertise."""
from engine.content import invocaciones_conocidas_max
from engine.entities import Criatura
from engine.rules import ataque_magico, tirada_habilidad
from app.models import Character
from app.hydration import hidratar_personaje


def _char(**kw) -> Character:
    base = dict(
        nombre="Test", raza="humano (estandar)", clase="picaro", nivel=6,
        atributos={"FUE": 10, "DES": 16, "CON": 12, "INT": 13, "SAB": 10, "CAR": 16},
        pg_actual=30, pg_max=30, velocidad_m=9, dado_golpe="d8", dados_golpe_disp=6,
        competencias={"habilidades": ["sigilo", "juego_de_manos"],
                      "salvaciones": ["DES", "INT"], "armas": ["simple"],
                      "armaduras": ["ligera"]},
        condiciones=[], armadura="cuero", escudo=False, arma_equipada="daga",
        inventario=[], monedas={}, slots={}, conocidos=[], preparados=[],
        recursos_clase={}, opciones_clase={},
    )
    base.update(kw)
    return Character(**base)


def maniqui(ca=1) -> Criatura:
    return Criatura(id="n1", nombre="M", nivel=1,
                    atributos={"FUE": 10, "DES": 10, "CON": 10,
                               "INT": 10, "SAB": 10, "CAR": 10},
                    pg_actual=200, pg_max=200, ca_fija=ca)


def test_invocaciones_por_nivel():
    assert invocaciones_conocidas_max(1) == 0
    assert invocaciones_conocidas_max(2) == 2
    assert invocaciones_conocidas_max(5) == 3
    assert invocaciones_conocidas_max(9) == 5
    assert invocaciones_conocidas_max(18) == 8


def test_expertise_duplica_competencia():
    # pícaro nv6 => bc 3. Con expertise en sigilo, el bono es mod DES + 2*bc
    picaro = _char(opciones_clase={"expertise": ["sigilo"]})
    cr = hidratar_personaje(picaro)
    # forzamos muchas tiradas y comparamos el bono reportado (constante)
    r = tirada_habilidad(cr, "sigilo", cd=10)
    # DES 16 => +3 ; bc(6)=3 ; expertise => +3 más => bono total 9
    assert r["bono"] == 9
    # sin expertise: 3 + 3 = 6
    cr2 = hidratar_personaje(_char())
    r2 = tirada_habilidad(cr2, "sigilo", cd=10)
    assert r2["bono"] == 6


def test_invocacion_otorga_competencias():
    # Influencia Seductora otorga competencia en engaño y persuasión
    brujo = _char(clase="brujo", nivel=2, conocidos=[],
                  competencias={"habilidades": [], "salvaciones": ["SAB", "CAR"],
                                "armas": ["simple"], "armaduras": ["ligera"]},
                  opciones_clase={"invocaciones": ["influencia_seductora"]})
    cr = hidratar_personaje(brujo)
    assert "engano" in cr.competencias["habilidades"]
    assert "persuasion" in cr.competencias["habilidades"]


def test_explosion_agonizante_suma_car_al_danio():
    # CAR 16 => +3. bono_danio del ataque debe reflejarse en el daño final.
    lanzador = Criatura(id="w", nombre="Brujo", nivel=5,
                        atributos={"FUE": 8, "DES": 12, "CON": 12,
                                   "INT": 10, "SAB": 10, "CAR": 16},
                        pg_actual=30, pg_max=30, armadura=None)
    for _ in range(50):
        r = ataque_magico(lanzador, maniqui(ca=1), "CAR", "1d10", "fuerza",
                          bono_danio=3)
        if r["danio"]:
            # el total_final = dados + 3
            assert r["danio"]["total_final"] == sum(r["danio"]["dados"]) + 3
            assert r["danio"]["bono_danio"] == 3
            return
    raise AssertionError("nunca impactó")
