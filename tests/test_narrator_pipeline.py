"""Tests del pipeline del narrador (paso 3): parser, efectos, conjuros."""
import os

import pytest
from httpx import ASGITransport, AsyncClient


from app.effects import aplicar_efectos  # noqa: E402
from app.models import NPC, Campaign, Character, PendingConsequence, Quest  # noqa: E402
from app.narrator import parsear_salida  # noqa: E402
from main import app  # noqa: E402
from sqlalchemy import select  # noqa: E402


# ---------------------------------------------------------------- parser

def test_parser_sin_json():
    n, e = parsear_salida("El goblin cae al suelo, muerto.")
    assert n == "El goblin cae al suelo, muerto."
    assert e == {}


def test_parser_bloque_json():
    texto = ('La anciana les entrega un mapa.\n\n```json\n'
             '{"nueva_quest": {"titulo": "El mapa", "descripcion": "x", '
             '"principal": true, "npc_origen_id": null}, '
             '"campo_invalido": "hackeo", "otorgar_xp": 25}\n```')
    n, e = parsear_salida(texto)
    assert n == "La anciana les entrega un mapa."
    assert "nueva_quest" in e and "otorgar_xp" in e
    assert "campo_invalido" not in e  # el schema filtra


def test_parser_json_suelto_al_final():
    texto = 'Narración.\n{"avanzar_tiempo_min": 30}'
    n, e = parsear_salida(texto)
    assert n == "Narración."
    assert e == {"avanzar_tiempo_min": 30}


def test_parser_json_roto_no_rompe():
    n, e = parsear_salida('Narración.\n```json\n{esto no es json}\n```')
    assert "Narración" in n
    assert e == {}


def test_parser_pg_no_esta_en_el_contrato():
    _, e = parsear_salida('X\n```json\n{"pg_actual": 999, "oro": 5000}\n```')
    assert e == {}  # el LLM no puede tocar recursos de PJs


# ---------------------------------------------------------------- efectos

# fixture db_session: ver conftest.py


@pytest.mark.anyio
async def test_efectos_completos(db_session):
    db = db_session
    camp = Campaign(nombre="test")
    db.add(camp)
    await db.flush()
    char = Character(campaign_id=camp.id, player_id=1, nombre="A", raza="x",
                     clase="guerrero", nivel=2,
                     atributos={"FUE": 10, "DES": 10, "CON": 10,
                                "INT": 10, "SAB": 10, "CAR": 10},
                     pg_actual=10, pg_max=10, dado_golpe="d10")
    db.add(char)
    await db.flush()

    log = await aplicar_efectos(db, camp, {
        "nuevos_npcs": [{"nombre": "Marlok", "rol": "herrero",
                         "actitud": "desconfiado", "secretos": "esconde algo"}],
        "nueva_quest": {"titulo": "La espada rota", "descripcion": "d",
                        "principal": True, "npc_origen_id": None},
        "consecuencia_pendiente": {"evento": "mintieron al guardia",
                                   "efecto": "los buscarán",
                                   "activacion": "al volver al pueblo"},
        "otorgar_xp": 5000,               # debe toparse a 50 × nivel(2) = 100
        "avanzar_tiempo_min": 120,
        "nueva_ubicacion": "Taberna del Jabalí",
    })
    await db.commit()

    npcs = (await db.execute(select(NPC))).scalars().all()
    assert any(n.nombre == "Marlok" and n.actitud == "desconfiado" for n in npcs)
    quests = (await db.execute(select(Quest))).scalars().all()
    assert any(q.titulo == "La espada rota" and q.principal for q in quests)
    cons = (await db.execute(select(PendingConsequence))).scalars().all()
    assert len(cons) == 1 and not cons[0].resuelta
    await db.refresh(char)
    assert char.xp == 100  # topeado
    assert camp.tiempo_juego_min == 120
    assert camp.ubicacion_actual == "Taberna del Jabalí"
    assert ("xp_excedente", 4900) in log["rechazados"]


@pytest.mark.anyio
async def test_efectos_rechaza_npc_de_otra_campania(db_session):
    db = db_session
    c1, c2 = Campaign(nombre="a"), Campaign(nombre="b")
    db.add_all([c1, c2])
    await db.flush()
    ajeno = NPC(campaign_id=c2.id, nombre="Intruso")
    db.add(ajeno)
    await db.flush()
    log = await aplicar_efectos(db, c1, {
        "actualizar_npc": [{"npc_id": ajeno.id, "actitud": "hostil"}]})
    assert log["aplicados"] == []
    assert len(log["rechazados"]) == 1


@pytest.mark.anyio
async def test_efectos_inicia_combate_valida_monstruos(db_session):
    db = db_session
    camp = Campaign(nombre="t")
    db.add(camp)
    await db.flush()
    log = await aplicar_efectos(db, camp, {
        "inicia_combate": {"monstruos": ["goblin", "dragon_inventado", "orco"]}})
    assert log["inicia_combate"] == ["goblin", "orco"]  # filtra el inválido


# ---------------------------------------------------------------- API: conjuros

MAGO = {
    "nombre": "Elara", "raza": "elfo", "subraza": "alto_elfo",
    "clase": "mago", "metodo": "libre",
    "atributos": {"FUE": 8, "DES": 14, "CON": 12, "INT": 16, "SAB": 10, "CAR": 10},
    "habilidades": ["arcanos"], "arma_equipada": "daga",
    "preparados": ["proyectil_magico", "manos_ardientes", "curar_heridas",
                   "bendecir"],
}


# fixture client: ver conftest.py


async def _setup_combate(c):
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    r = await c.post("/api/characters", json=MAGO, headers=h)
    assert r.status_code == 200, r.text
    r = await c.post(f"/api/campaigns/{cid}/combat/start",
                     json={"monstruos": ["zombi"]}, headers=h)  # CA 8, lento
    assert r.status_code == 200, r.text
    return c, h, cid


async def _esperar_mi_turno(c, h, cid):
    est = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
    return est


@pytest.mark.anyio
async def test_cast_proyectil_magico_gasta_slot(client):
    c, h, cid = await _setup_combate(client)
    est = await _esperar_mi_turno(c, h, cid)
    if est["estado"] != "combate":
        pytest.skip("el zombi mató al mago antes de su turno (azar)")
    npc_id = int([e for e in est["combate"]["orden"]
                  if e["tipo"] == "npc"][0]["id"].split("_")[1])
    r = await c.post(f"/api/campaigns/{cid}/combat/cast", json={
        "conjuro": "proyectil_magico", "objetivo_npc_id": npc_id}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["gasto_slot"]["ok"] and d["gasto_slot"]["restantes"] == 1
    dmg = [x for x in d["resoluciones"] if x["tipo"] == "danio_auto"]
    assert dmg and dmg[0]["total_final"] >= 6  # 3 proyectiles de 1d4+1: mínimo 6


@pytest.mark.anyio
async def test_cast_conjuro_no_preparado(client):
    c, h, cid = await _setup_combate(client)
    est = await _esperar_mi_turno(c, h, cid)
    if est["estado"] != "combate":
        pytest.skip("azar")
    npc_id = int([e for e in est["combate"]["orden"]
                  if e["tipo"] == "npc"][0]["id"].split("_")[1])
    r = await c.post(f"/api/campaigns/{cid}/combat/cast", json={
        "conjuro": "rayo_abrasador", "objetivo_npc_id": npc_id}, headers=h)
    assert r.status_code == 400
    assert "hechizo_no_disponible" in r.text


@pytest.mark.anyio
async def test_cast_slots_se_agotan(client):
    c, h, cid = await _setup_combate(client)
    usados = 0
    for _ in range(10):
        est = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
        if est["estado"] != "combate":
            break
        npcs = [e for e in est["combate"]["orden"] if e["tipo"] == "npc"]
        if not npcs:
            break
        npc_id = int(npcs[0]["id"].split("_")[1])
        r = await c.post(f"/api/campaigns/{cid}/combat/cast", json={
            "conjuro": "curar_heridas",
            "objetivo_character_id": None}, headers=h)
        if r.status_code == 200:
            usados += 1
        elif r.status_code == 400 and "Sin espacios" in r.text:
            assert usados == 2  # mago nv1: 2 slots
            return
        elif r.status_code == 400 and "muerto" in r.text:
            pytest.skip("el mago murió (azar)")
    if usados < 2:
        pytest.skip("combate terminó antes de agotar slots (azar)")
    # si usó los 2 y el combate sigue, el tercero debe fallar
    est = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
    if est["estado"] == "combate":
        r = await c.post(f"/api/campaigns/{cid}/combat/cast", json={
            "conjuro": "curar_heridas"}, headers=h)
        assert r.status_code == 400


@pytest.mark.anyio
async def test_state_endpoint(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    await c.post("/api/characters", json=MAGO, headers=h)
    r = await c.get(f"/api/campaigns/{cid}/state", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["quests"] == [] and d["npcs_conocidos"] == []
    assert d["consecuencias_pendientes"] == 0
