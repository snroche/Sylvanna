"""Listas de conjuros por clase y riqueza inicial de clase."""
import pytest

from engine.content import (PLATA_INICIAL_CLASE, clases_de_conjuro,
                            oro_inicial_clase, puede_aprender_conjuro, CONJUROS)


def test_normaliza_clases_ingles_y_espanol():
    # conjuro importado con clases en inglés
    assert clases_de_conjuro({"clases": ["druid", "wizard"]}) == ["druida", "mago"]
    # curado con clases en español
    assert "mago" in clases_de_conjuro(CONJUROS["magic_missile"])


def test_puede_aprender_por_clase():
    assert puede_aprender_conjuro("mago", "magic_missile")
    assert not puede_aprender_conjuro("mago", "cure_wounds")   # no es de mago
    assert puede_aprender_conjuro("clerigo", "cure_wounds")
    # druida no aprende proyectil mágico (mago/hechicero)
    assert not puede_aprender_conjuro("druida", "magic_missile")


def test_oro_inicial_por_clase():
    for clase, (n, mult) in PLATA_INICIAL_CLASE.items():
        oro = oro_inicial_clase(clase)
        assert n * mult <= oro <= n * 4 * mult   # entre NdM mín y máx


MAGO = {
    "nombre": "E", "raza": "elfo", "subraza": "alto_elfo", "clase": "mago",
    "metodo": "libre",
    "atributos": {"FUE": 8, "DES": 14, "CON": 12, "INT": 15, "SAB": 10, "CAR": 10},
    "habilidades": ["arcanos", "historia"], "arma_equipada": "daga",
}


async def _crear(client, body):
    d = (await client.post("/api/campaigns", json={
        "nombre": "C", "nombre_jugador": "S"})).json()
    h = {"X-Player-Token": d["player_token"]}
    return d["campaign_id"], h, await client.post("/api/characters",
                                                  json=body, headers=h)


@pytest.mark.anyio
async def test_mago_no_aprende_conjuro_de_otra_clase(client):
    _, _, r = await _crear(client, {**MAGO, "preparados": ["cure_wounds"]})
    assert r.status_code == 400
    assert "no puede aprender" in r.text.lower()


@pytest.mark.anyio
async def test_druida_no_aprende_conjuro_de_mago(client):
    druida = {"nombre": "D", "raza": "humano", "subraza": "estandar",
              "clase": "druida", "metodo": "libre",
              "atributos": {"FUE": 10, "DES": 12, "CON": 13, "INT": 10,
                            "SAB": 15, "CAR": 8},
              "habilidades": ["naturaleza", "percepcion"],
              "arma_equipada": "baston", "conocidos": ["magic_missile"]}
    _, _, r = await _crear(client, druida)
    assert r.status_code == 400


@pytest.mark.anyio
async def test_alto_elfo_puede_truco_de_mago(client):
    # alto elfo (aunque sea de otra clase) puede un truco de mago
    guerrero_elfo = {"nombre": "G", "raza": "elfo", "subraza": "alto_elfo",
                     "clase": "guerrero", "metodo": "libre",
                     "estilo_combate": "defensa",
                     "atributos": {"FUE": 15, "DES": 13, "CON": 14, "INT": 10,
                                   "SAB": 10, "CAR": 8},
                     "habilidades": ["atletismo"], "arma_equipada": "espada_larga",
                     "conocidos": ["ray_of_frost"]}   # truco de mago
    _, _, r = await _crear(client, guerrero_elfo)
    assert r.status_code == 200, r.text


@pytest.mark.anyio
async def test_content_conjuros_traen_clases(client):
    d = (await client.get("/api/content")).json()
    assert "mago" in d["conjuros"]["magic_missile"]["clases"]
    assert "clerigo" in d["conjuros"]["cure_wounds"]["clases"]
