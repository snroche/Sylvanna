"""Rituales, componentes materiales, sintonía y monturas (API)."""
import pytest

CLERIGO = {
    "nombre": "Piadoso", "raza": "humano", "subraza": "estandar",
    "clase": "clerigo", "metodo": "libre", "subclase": "dominio_de_la_vida",
    "atributos": {"FUE": 10, "DES": 10, "CON": 12, "INT": 10, "SAB": 15, "CAR": 10},
    "habilidades": ["religion", "medicina"],
    "preparados": ["detect_magic"],
    "arma_equipada": "mazo",
    "inventario": [{"nombre": "perla", "cantidad": 1},
                   {"nombre": "anillo_de_proteccion", "cantidad": 1},
                   {"nombre": "amuleto_de_salud", "cantidad": 1},
                   {"nombre": "capa_elfica", "cantidad": 1}],
}


async def _crear(client, body=CLERIGO):
    r = await client.post("/api/campaigns", json={
        "nombre": "C", "nombre_jugador": "S"})
    d = r.json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    r = await client.post("/api/characters", json=body, headers=h)
    assert r.status_code == 200, r.text
    return cid, h


@pytest.mark.anyio
async def test_ritual_no_gasta_slot(client):
    cid, h = await _crear(client)
    ficha0 = (await client.get("/api/campaigns/%d/state" % cid, headers=h)).json()
    t0 = ficha0["tiempo_juego_min"]
    r = await client.post(f"/api/campaigns/{cid}/spells/ritual",
                          json={"conjuro": "detect_magic"}, headers=h)
    assert r.status_code == 200, r.text
    # avanzó 10 minutos de juego
    t1 = (await client.get(f"/api/campaigns/{cid}/state", headers=h)).json()[
        "tiempo_juego_min"]
    assert t1 == t0 + 10


@pytest.mark.anyio
async def test_ritual_de_conjuro_no_ritual_falla(client):
    cid, h = await _crear(client)
    r = await client.post(f"/api/campaigns/{cid}/spells/ritual",
                          json={"conjuro": "cure_wounds"}, headers=h)
    assert r.status_code == 400


# identify es de mago (no de clérigo) y pide un componente costoso (perla)
MAGO_RITUAL = {
    "nombre": "Elrimar", "raza": "humano", "subraza": "estandar", "clase": "mago",
    "metodo": "libre",
    "atributos": {"FUE": 8, "DES": 12, "CON": 12, "INT": 15, "SAB": 10, "CAR": 10},
    "habilidades": ["arcanos", "historia"], "arma_equipada": "daga",
    "preparados": ["detect_magic", "identify"],
    "inventario": [{"nombre": "perla", "cantidad": 1}],
}


@pytest.mark.anyio
async def test_componente_material_requerido(client):
    # con la perla en el inventario, identify (ritual) se puede lanzar
    cid, h = await _crear(client, MAGO_RITUAL)
    r = await client.post(f"/api/campaigns/{cid}/spells/ritual",
                          json={"conjuro": "identify"}, headers=h)
    assert r.status_code == 200, r.text
    # sin la perla, falla
    cid2, h2 = await _crear(client, {**MAGO_RITUAL, "inventario": []})
    r = await client.post(f"/api/campaigns/{cid2}/spells/ritual",
                          json={"conjuro": "identify"}, headers=h2)
    assert r.status_code == 400
    assert "componente" in r.text.lower()


@pytest.mark.anyio
async def test_sintonia_max_tres(client):
    cid, h = await _crear(client)
    for item in ("anillo_de_proteccion", "amuleto_de_salud", "capa_elfica"):
        r = await client.post(f"/api/campaigns/{cid}/attunement/attune",
                              json={"item": item}, headers=h)
        assert r.status_code == 200, r.text
    # una cuarta sintonía (usando la perla) debe fallar
    r = await client.post(f"/api/campaigns/{cid}/attunement/attune",
                          json={"item": "perla"}, headers=h)
    assert r.status_code == 400
    # terminar una y volver a sintonizar
    r = await client.post(f"/api/campaigns/{cid}/attunement/end",
                          json={"item": "capa_elfica"}, headers=h)
    assert r.status_code == 200
    assert len(r.json()["sintonia"]) == 2


@pytest.mark.anyio
async def test_montura(client):
    cid, h = await _crear(client)
    r = await client.post(f"/api/campaigns/{cid}/mount",
                          json={"bestia": "caballo_de_guerra"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["montura"]["velocidad_m"] == 18
    # no se puede montar dos veces
    r = await client.post(f"/api/campaigns/{cid}/mount",
                          json={"bestia": "pantera"}, headers=h)
    assert r.status_code == 409
    # desmontar
    r = await client.post(f"/api/campaigns/{cid}/dismount", headers=h)
    assert r.status_code == 200
