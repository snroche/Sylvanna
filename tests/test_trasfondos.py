"""Trasfondos: competencias, equipo y oro inicial al crear personaje."""
import pytest

from engine.content import TRASFONDOS, aplicar_trasfondo


def test_catalogo_trasfondos():
    # los 13 trasfondos del PHB (incluye el Acólito del SRD)
    assert "acolito" in TRASFONDOS
    assert len(TRASFONDOS) >= 13
    for clave, t in TRASFONDOS.items():
        assert len(t["competencias"]) == 2
        assert "rasgo" in t


def test_aplicar_trasfondo_invalido():
    with pytest.raises(ValueError):
        aplicar_trasfondo("panadero")


@pytest.mark.anyio
async def test_creacion_con_trasfondo(client):
    r = await client.post("/api/campaigns", json={
        "nombre": "Camp", "nombre_jugador": "Santi"})
    token = r.json()["player_token"]
    h = {"X-Player-Token": token}
    r = await client.post("/api/characters", json={
        "nombre": "Seldon", "raza": "humano", "subraza": "estandar",
        "clase": "mago", "metodo": "libre",
        "atributos": {"FUE": 8, "DES": 14, "CON": 12,
                      "INT": 15, "SAB": 10, "CAR": 10},
        "habilidades": ["arcanos", "investigacion"],
        "arma_equipada": "daga", "trasfondo": "sabio",
    }, headers=h)
    assert r.status_code == 200, r.text
    cid = r.json()["character_id"]
    ficha = (await client.get(f"/api/characters/{cid}/sheet", headers=h)).json()
    # el sabio otorga competencia en arcanos e historia
    assert "historia" in ficha["competencias"]["habilidades"]
    # oro inicial: riqueza de clase (mago 4d4×10, mín 40) + trasfondo (sabio 10)
    assert ficha["monedas"]["mo"] >= 50
    # el rasgo del trasfondo queda registrado
    assert ficha["opciones_clase"]["trasfondo"] == "sabio"
    assert ficha["opciones_clase"]["rasgo_trasfondo"] == "Investigador"
