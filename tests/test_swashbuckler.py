"""Swashbuckler (pícaro): +CAR a la iniciativa y Furtivo en duelo."""
import pytest

from engine.content import SUBCLASES_INFO, SUBCLASES_SRD
from engine.rules import iniciativa
from app.models import Character
from app.hydration import hidratar_personaje


def _picaro(sub=None, car=16) -> Character:
    return Character(
        nombre="Sly", raza="humano (estandar)", clase="picaro", nivel=3,
        atributos={"FUE": 10, "DES": 16, "CON": 12, "INT": 12, "SAB": 10, "CAR": car},
        pg_actual=20, pg_max=20, velocidad_m=9, dado_golpe="d8", dados_golpe_disp=3,
        competencias={"habilidades": [], "salvaciones": ["DES", "INT"],
                      "armas": ["simple"], "armaduras": ["ligera"]},
        condiciones=[], armadura="cuero", escudo=False, arma_equipada="espada_corta",
        inventario=[], monedas={}, slots={}, conocidos=[], preparados=[],
        recursos_clase={}, opciones_clase={}, subclase=sub, feats=[])


def test_swashbuckler_en_catalogo():
    assert "swashbuckler" in SUBCLASES_SRD["picaro"]
    assert "swashbuckler" in SUBCLASES_INFO


def test_swashbuckler_suma_car_a_iniciativa():
    cr = hidratar_personaje(_picaro("swashbuckler", car=16))   # CAR +3
    assert cr.bono_iniciativa == 3
    # iniciativa = mod(DES)=+3 + Audacia Temeraria CAR +3 = +6
    assert iniciativa(cr)["bono"] == 6


def test_ladron_no_suma_car_a_iniciativa():
    cr = hidratar_personaje(_picaro("ladron", car=16))
    assert cr.bono_iniciativa == 0
    assert iniciativa(cr)["bono"] == 3   # solo DES


@pytest.mark.anyio
async def test_content_ofrece_swashbuckler(client):
    d = (await client.get("/api/content")).json()
    assert "swashbuckler" in d["subclases"]["picaro"]
