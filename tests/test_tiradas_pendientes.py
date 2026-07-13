"""Pedidos de tirada del DM: CD adaptable y espera al grupo antes de narrar."""
import pytest

from sqlalchemy import select

from app.effects import aplicar_efectos
from app.models import Campaign, Character


@pytest.mark.anyio
async def test_pedir_tirada_grupo_crea_pendiente_con_cd(db_session):
    db = db_session
    camp = Campaign(nombre="t")
    db.add(camp)
    await db.flush()
    for nombre in ("Aria", "Bruno"):
        db.add(Character(campaign_id=camp.id, player_id=1, nombre=nombre,
                         raza="x", clase="picaro", nivel=1,
                         atributos={"FUE": 10, "DES": 12, "CON": 10,
                                    "INT": 10, "SAB": 10, "CAR": 10},
                         pg_actual=8, pg_max=8, dado_golpe="d8"))
    await db.flush()

    log = await aplicar_efectos(db, camp, {
        "pedir_tirada": {"habilidad": "percepcion", "a_quien": "todos", "cd": 18}})
    await db.commit()

    assert camp.tiradas_pendientes and len(camp.tiradas_pendientes) == 1
    p = camp.tiradas_pendientes[0]
    assert p["habilidad"] == "percepcion" and p["cd"] == 18
    assert len(p["pendientes"]) == 2   # ambos PJs vivos
    assert ("pedir_tirada", "percepcion CD18 → todo el grupo") in log["aplicados"]


@pytest.mark.anyio
async def test_pedir_tirada_cd_fuera_de_rango_se_clampa(db_session):
    db = db_session
    camp = Campaign(nombre="t")
    db.add(camp)
    await db.flush()
    db.add(Character(campaign_id=camp.id, player_id=1, nombre="Solo", raza="x",
                     clase="mago", nivel=1,
                     atributos={"FUE": 10, "DES": 10, "CON": 10,
                                "INT": 10, "SAB": 10, "CAR": 10},
                     pg_actual=6, pg_max=6, dado_golpe="d6"))
    await db.flush()
    await aplicar_efectos(db, camp, {
        "pedir_tirada": {"habilidad": "arcanos", "a_quien": "Solo", "cd": 99}})
    await db.commit()
    assert camp.tiradas_pendientes[0]["cd"] == 30   # clamp a 30


@pytest.mark.anyio
async def test_pedir_tirada_habilidad_invalida_se_rechaza(db_session):
    db = db_session
    camp = Campaign(nombre="t")
    db.add(camp)
    await db.flush()
    log = await aplicar_efectos(db, camp, {
        "pedir_tirada": {"habilidad": "vibras", "cd": 15}})
    assert not camp.tiradas_pendientes
    assert ("pedir_tirada", "vibras") in log["rechazados"]


CAMPO = {"nombre": "La cripta", "nombre_jugador": "A"}
PJ = {"nombre": "Aria", "raza": "humano", "subraza": "estandar", "clase": "picaro",
      "metodo": "libre", "subclase": "ladron",
      "atributos": {"FUE": 10, "DES": 14, "CON": 12, "INT": 12, "SAB": 13, "CAR": 10},
      "habilidades": ["sigilo", "percepcion"], "arma_equipada": "daga"}


@pytest.mark.anyio
async def test_skill_check_usa_cd_del_dm_y_espera_al_grupo(client):
    # dos jugadores con personaje
    d = (await client.post("/api/campaigns", json=CAMPO)).json()
    h1 = {"X-Player-Token": d["player_token"]}
    cid, invite = d["campaign_id"], d["invite_code"]
    d2 = (await client.post("/api/campaigns/join", json={
        "invite_code": invite, "nombre_jugador": "B"})).json()
    h2 = {"X-Player-Token": d2["player_token"]}
    c1 = (await client.post("/api/characters", json=PJ, headers=h1)).json()["character_id"]
    c2 = (await client.post("/api/characters",
                            json={**PJ, "nombre": "Bruno"}, headers=h2)).json()["character_id"]

    # inyectar un pedido de tirada del DM (CD 20) a todo el grupo
    from app.db import SessionLocal
    async with SessionLocal() as s:
        camp = await s.get(Campaign, cid)
        camp.tiradas_pendientes = [{"habilidad": "percepcion", "cd": 20,
                                    "pendientes": [c1, c2], "tiradas": []}]
        await s.commit()

    # el estado le dice a cada jugador que le toca tirar y con qué CD
    est = (await client.get(f"/api/campaigns/{cid}", headers=h1)).json()
    assert est["tiradas_pendientes"][0]["cd"] == 20
    assert est["tiradas_pendientes"][0]["me_toca"] is True

    # primer jugador tira: usa CD 20 (no 12) y todavía NO se narra
    r = await client.post(f"/api/campaigns/{cid}/skill-check",
                          json={"habilidad": "percepcion"}, headers=h1)
    assert r.status_code == 200, r.text
    assert r.json()["resolucion"]["cd"] == 20      # CD del DM, no 12
    assert r.json()["narrando"] is False
    assert r.json()["faltan"] == 1

    # segundo jugador tira: ahora sí se narra el desenlace grupal
    r = await client.post(f"/api/campaigns/{cid}/skill-check",
                          json={"habilidad": "percepcion"}, headers=h2)
    assert r.json()["resolucion"]["cd"] == 20
    assert r.json()["narrando"] is True

    # ya no quedan pedidos pendientes
    est = (await client.get(f"/api/campaigns/{cid}", headers=h1)).json()
    assert est["tiradas_pendientes"] == []
