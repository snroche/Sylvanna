"""Test de integración de la API completa con SQLite en memoria.

Simula el flujo real: crear campaña → 2 jugadores → 2 personajes →
skill check → combate contra goblins hasta que termine.
"""
import os
import pytest
from httpx import ASGITransport, AsyncClient

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_e2e.db"
os.environ["OPENROUTER_API_KEY"] = ""  # fuerza narrador dummy

from app.db import crear_tablas, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
async def client():
    if os.path.exists("test_e2e.db"):
        os.remove("test_e2e.db")
    await crear_tablas()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await engine.dispose()
    if os.path.exists("test_e2e.db"):
        os.remove("test_e2e.db")


GUERRERO = {
    "nombre": "Thorin", "raza": "enano", "clase": "guerrero",
    "atributos": {"FUE": 16, "DES": 12, "CON": 14, "INT": 8, "SAB": 10, "CAR": 13},
    "habilidades": ["atletismo", "intimidacion"],
    "armadura": "coraza", "escudo": True, "arma_equipada": "espada_larga",
}
MAGO = {
    "nombre": "Elara", "raza": "elfa", "clase": "mago",
    "atributos": {"FUE": 8, "DES": 14, "CON": 12, "INT": 16, "SAB": 10, "CAR": 10},
    "habilidades": ["arcanos", "investigacion"],
    "arma_equipada": "daga",
    "preparados": ["proyectil_magico", "escudo"],
}


@pytest.mark.anyio
async def test_flujo_completo(client):
    # 1. crear campaña
    r = await client.post("/api/campaigns", json={
        "nombre": "La cripta", "nombre_jugador": "Santi"})
    assert r.status_code == 200, r.text
    d = r.json()
    camp_id, token1, invite = d["campaign_id"], d["player_token"], d["invite_code"]

    # 2. segundo jugador se une
    r = await client.post("/api/campaigns/join", json={
        "invite_code": invite, "nombre_jugador": "Amigo"})
    assert r.status_code == 200
    token2 = r.json()["player_token"]

    # código inválido
    r = await client.post("/api/campaigns/join", json={
        "invite_code": "nope", "nombre_jugador": "X"})
    assert r.status_code == 404

    h1, h2 = {"X-Player-Token": token1}, {"X-Player-Token": token2}

    # 3. crear personajes
    r = await client.post("/api/characters", json=GUERRERO, headers=h1)
    assert r.status_code == 200, r.text
    assert r.json()["pg_max"] == 12   # d10 máx + CON+2
    assert r.json()["ca"] == 17       # coraza 14 + DES(cap 2→+1) + escudo 2
    char1 = r.json()["character_id"]

    r = await client.post("/api/characters", json=MAGO, headers=h2)
    assert r.status_code == 200
    assert r.json()["pg_max"] == 7    # d6 máx + CON+1

    # no puede crear dos personajes
    r = await client.post("/api/characters", json=GUERRERO, headers=h1)
    assert r.status_code == 409

    # clase inválida
    r = await client.post("/api/characters", json={**GUERRERO, "clase": "jedi"},
                          headers=h2)
    assert r.status_code in (400, 409)

    # 4. ficha
    r = await client.get(f"/api/characters/{char1}/sheet", headers=h1)
    assert r.status_code == 200
    ficha = r.json()
    assert ficha["atributos"]["FUE"] == {"valor": 16, "mod": 3}
    assert ficha["slots"] == {}  # guerrero no tiene magia

    # token inválido rechazado
    r = await client.get(f"/api/characters/{char1}/sheet",
                         headers={"X-Player-Token": "falso"})
    assert r.status_code == 401

    # 5. skill check
    r = await client.post(f"/api/campaigns/{camp_id}/skill-check", json={
        "habilidad": "atletismo", "cd": 12,
        "descripcion": "escalar el muro de la cripta"}, headers=h1)
    assert r.status_code == 200
    reso = r.json()["resolucion"]
    assert reso["bono"] == 5 and "narracion" in r.json()

    # 6. combate
    r = await client.post(f"/api/campaigns/{camp_id}/combat/start", json={
        "monstruos": ["goblin", "goblin"]}, headers=h1)
    assert r.status_code == 200, r.text
    combate = r.json()

    # no se puede iniciar otro combate
    r = await client.post(f"/api/campaigns/{camp_id}/combat/start", json={
        "monstruos": ["orco"]}, headers=h1)
    assert r.status_code == 409

    # jugar el combate hasta el final (tope 60 intentos)
    r = await client.get(f"/api/campaigns/{camp_id}", headers=h1)
    estado = r.json()

    for _ in range(60):
        r = await client.get(f"/api/campaigns/{camp_id}", headers=h1)
        estado = r.json()
        if estado["estado"] != "combate":
            break
        turno = estado["combate"]["orden"][estado["combate"]["turno_idx"]]
        assert turno["tipo"] == "pj", "el server debe auto-resolver turnos de NPC"
        pj_id = int(turno["id"].split("_")[1])
        token = h1 if pj_id == char1 else h2
        # buscar un goblin vivo en el orden
        goblins = [e for e in estado["combate"]["orden"] if e["tipo"] == "npc"]
        assert goblins
        npc_id = int(goblins[0]["id"].split("_")[1])
        r = await client.post(f"/api/campaigns/{camp_id}/combat/attack", json={
            "objetivo_npc_id": npc_id}, headers=token)
        if r.status_code == 400 and "muerto" in r.text:
            # el personaje de este jugador murió; el otro sigue
            continue
        assert r.status_code == 200, r.text

    assert estado["estado"] == "exploracion", "el combate debe terminar"

    # 7. historial de mensajes registrado
    r = await client.get(f"/api/campaigns/{camp_id}/messages", headers=h1)
    assert r.status_code == 200
    autores = {m["autor"] for m in r.json()}
    assert "dm" in autores and "jugador" in autores
