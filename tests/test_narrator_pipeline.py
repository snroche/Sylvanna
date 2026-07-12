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
    "preparados": ["proyectil_magico", "manos_ardientes", "escudo", "dormir"],
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
            "conjuro": "escudo"}, headers=h)
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
            "conjuro": "escudo"}, headers=h)
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


# ---------------------------------------------------------------- clase + party (API)

GUERRERO2 = {
    "nombre": "Borin", "raza": "enano", "subraza": "enano_de_las_montanas",
    "clase": "guerrero", "metodo": "libre", "estilo_combate": "duelo",
    "alineamiento": "legal_bueno",
    "atributos": {"FUE": 14, "DES": 12, "CON": 14, "INT": 8, "SAB": 10, "CAR": 10},
    "habilidades": ["atletismo"], "armadura": "coraza",
    "arma_equipada": "espada_larga",
}


@pytest.mark.anyio
async def test_habilidades_clase_y_party(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    r = await c.post("/api/characters", json=GUERRERO2, headers=h)
    assert r.status_code == 200, r.text

    # party info en el GET de campaña
    est = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
    p = est["personajes"][0]
    assert p["alineamiento"] == "legal_bueno"
    assert "enano" in p["raza"]

    # recursos de clase en la ficha
    ficha = (await c.get(f"/api/characters/{p['id']}/sheet", headers=h)).json()
    assert "nuevo_aliento" in ficha["recursos_clase"]
    assert ficha["estilo_combate"] == "duelo"

    # nuevo aliento fuera de combate
    r = await c.post(f"/api/campaigns/{cid}/class-ability",
                     json={"nombre": "nuevo_aliento"}, headers=h)
    assert r.status_code == 200 and r.json()["curado"] >= 0
    r = await c.post(f"/api/campaigns/{cid}/class-ability",
                     json={"nombre": "nuevo_aliento"}, headers=h)
    assert r.status_code == 400  # agotado hasta descanso corto

    # descanso corto lo resetea
    r = await c.post(f"/api/campaigns/{cid}/rest/short",
                     json={"dados": 0}, headers=h)
    assert r.status_code == 200
    r = await c.post(f"/api/campaigns/{cid}/class-ability",
                     json={"nombre": "nuevo_aliento"}, headers=h)
    assert r.status_code == 200

    # habilidad de otra clase rebota
    r = await c.post(f"/api/campaigns/{cid}/class-ability",
                     json={"nombre": "furia"}, headers=h)
    assert r.status_code == 400


@pytest.mark.anyio
async def test_guerrero_sin_estilo_rebota(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    body = {**GUERRERO2}
    del body["estilo_combate"]
    r = await c.post("/api/characters", json=body, headers=h)
    assert r.status_code == 400 and "estilo" in r.text


@pytest.mark.anyio
async def test_asi_nivel_4(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    r = await c.post("/api/characters", json=GUERRERO2, headers=h)
    char_id = r.json()["character_id"]

    # forzar XP de nivel 4 directo en DB
    from app.db import SessionLocal
    from app.models import Character
    async with SessionLocal() as db:
        ch = await db.get(Character, char_id)
        ch.xp = 2700
        ch.nivel = 3
        await db.commit()

    # subir a 4 sin ASI → rebota pidiendo el reparto
    r = await c.post(f"/api/campaigns/{cid}/level-up",
                     json={"metodo": "fijo"}, headers=h)
    assert r.status_code == 400 and "asi" in r.text.lower()

    # con ASI válido
    r = await c.post(f"/api/campaigns/{cid}/level-up",
                     json={"metodo": "fijo", "asi": {"FUE": 1, "CON": 1}},
                     headers=h)
    assert r.status_code == 200
    ficha = (await c.get(f"/api/characters/{char_id}/sheet", headers=h)).json()
    assert ficha["nivel"] == 4
    assert ficha["atributos"]["FUE"]["valor"] == 17  # 14+2 racial +1 ASI
    assert ficha["atributos"]["CON"]["valor"] == 17


@pytest.mark.anyio
async def test_party_say_no_narra(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s",
        "descripcion": "Transcurre en Baldur's Gate."})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    await c.post("/api/characters", json=GUERRERO2, headers=h)
    r = await c.post(f"/api/campaigns/{cid}/say",
                     json={"texto": "che, ¿vamos por la izquierda?",
                           "entre_jugadores": True}, headers=h)
    assert r.status_code == 200 and r.json()["narrando"] is False
    msgs = (await c.get(f"/api/campaigns/{cid}/messages?since=0",
                        headers=h)).json()
    party = [m for m in msgs if m["autor"] == "party"]
    assert len(party) == 1
    # el DM (dummy en tests) NO respondió a la charla de party
    dm_sobre_party = [m for m in msgs if m["autor"] == "dm"
                      and "izquierda" in m["contenido"]]
    assert not dm_sobre_party


@pytest.mark.anyio
async def test_apertura_de_campania(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "BG", "nombre_jugador": "s",
        "descripcion": "Baldur's Gate, tono oscuro."})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    await c.post("/api/characters", json=GUERRERO2, headers=h)
    msgs = (await c.get(f"/api/campaigns/{cid}/messages?since=0",
                        headers=h)).json()
    # con narrador dummy la apertura llega como mensaje del dm
    assert any(m["autor"] == "dm" and "APERTURA" in m["contenido"]
               for m in msgs)


# ---------------------------------------------------------------- nivel 5

async def _subir_a(client, h, cid, char_id, nivel_objetivo, clase="guerrero"):
    """Setea XP y sube nivel a nivel, resolviendo ASI y subclase."""
    from app.db import SessionLocal
    from app.models import Character
    from engine.rules import XP_POR_NIVEL
    async with SessionLocal() as db:
        ch = await db.get(Character, char_id)
        ch.xp = XP_POR_NIVEL[nivel_objetivo]
        await db.commit()
    while True:
        ficha = (await client.get(f"/api/characters/{char_id}/sheet",
                                  headers=h)).json()
        if ficha["nivel"] >= nivel_objetivo:
            return ficha
        body = {"metodo": "fijo"}
        from engine.content import NIVEL_SUBCLASE, SUBCLASES_SRD
        if ficha["nivel"] + 1 == NIVEL_SUBCLASE.get(clase):
            body["subclase"] = SUBCLASES_SRD[clase][0]
        if ficha["nivel"] + 1 in (4, 8):
            body["asi"] = {"FUE": 2}
        r = await client.post(f"/api/campaigns/{cid}/level-up",
                              json=body, headers=h)
        assert r.status_code == 200, r.text


@pytest.mark.anyio
async def test_ataque_extra_nivel_5(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    char_id = (await c.post("/api/characters", json=GUERRERO2,
                            headers=h)).json()["character_id"]
    ficha = await _subir_a(c, h, cid, char_id, 5)
    assert ficha["nivel"] == 5 and ficha["subclase"] == "campeon"

    # combate contra un ogro (aguanta varios golpes)
    r = await c.post(f"/api/campaigns/{cid}/combat/start",
                     json={"monstruos": ["ogro"]}, headers=h)
    assert r.status_code == 200
    for _ in range(3):
        est = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
        if est["estado"] != "combate":
            pytest.skip("combate terminó por azar")
        turno = est["combate"]["orden"][est["combate"]["turno_idx"]]
        if turno["id"] != f"pj_{char_id}":
            pytest.skip("azar de iniciativa")
        npc_id = int([e for e in est["combate"]["orden"]
                      if e["tipo"] == "npc"][0]["id"].split("_")[1])
        # primer ataque: NO debe consumir el turno (ataque extra nv5)
        r1 = await c.post(f"/api/campaigns/{cid}/combat/attack",
                          json={"objetivo_npc_id": npc_id}, headers=h)
        assert r1.status_code == 200
        d1 = r1.json()
        if d1["fin_combate"]:
            pytest.skip("mató al ogro de un golpe (crítico), no verifica extra")
        assert d1["turnos_npc"] == [], "el primer ataque no debe pasar el turno"
        est2 = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
        t2 = est2["combate"]["orden"][est2["combate"]["turno_idx"]]
        assert t2["id"] == f"pj_{char_id}", "sigue siendo mi turno"
        # segundo ataque: ahora sí consume el turno
        r2 = await c.post(f"/api/campaigns/{cid}/combat/attack",
                          json={"objetivo_npc_id": npc_id}, headers=h)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["fin_combate"] or d2["turnos_npc"], \
            "el segundo ataque debe pasar el turno (el ogro responde)"
        return


MAGO5 = {
    "nombre": "Zim", "raza": "gnomo", "subraza": "gnomo_de_las_rocas",
    "clase": "mago", "metodo": "libre",
    "atributos": {"FUE": 8, "DES": 14, "CON": 14, "INT": 16, "SAB": 10, "CAR": 10},
    "arma_equipada": "daga", "preparados": ["rayo_de_escarcha", "proyectil_magico"],
}


@pytest.mark.anyio
async def test_gestion_de_conjuros(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    char_id = (await c.post("/api/characters", json=MAGO5,
                            headers=h)).json()["character_id"]

    # nivel 1: máx lanzable 1 → rayo_abrasador (nv2) rebota
    r = await c.post(f"/api/campaigns/{cid}/spells/manage",
                     json={"lista": ["rayo_abrasador"]}, headers=h)
    assert r.status_code == 400 and "nivel 2" in r.text

    # límite de preparados: INT 16 +2 gnomo = 18 → mod +4, + nivel 1 = 5.
    # Seis conjuros con nivel deben rebotar.
    r = await c.post(f"/api/campaigns/{cid}/spells/manage",
                     json={"lista": ["proyectil_magico", "escudo",
                                     "manos_ardientes", "dormir",
                                     "hechizar_persona", "onda_atronadora"]},
                     headers=h)
    assert r.status_code == 400 and "Máximo 5" in r.text

    # válido: 3 con nivel + 1 truco
    r = await c.post(f"/api/campaigns/{cid}/spells/manage",
                     json={"lista": ["rayo_de_escarcha", "proyectil_magico",
                                     "escudo", "dormir"]}, headers=h)
    assert r.status_code == 200
    ficha = (await c.get(f"/api/characters/{char_id}/sheet", headers=h)).json()
    assert "dormir" in ficha["preparados"]

    # a nivel 5: máx lanzable 3, límite 8
    ficha = await _subir_a(c, h, cid, char_id, 5, clase="mago")
    r = await c.post(f"/api/campaigns/{cid}/spells/manage",
                     json={"lista": ["rayo_abrasador", "invisibilidad",
                                     "proyectil_magico"]}, headers=h)
    assert r.status_code == 200 and r.json()["nivel_max"] == 3


@pytest.mark.anyio
async def test_content_razas_completas(client):
    r = await client.get("/api/content")
    d = r.json()
    assert "razas" in d and "tiflin" not in d["razas"]
    elfo = d["razas"]["elfo"]
    assert elfo["bonos"] == {"DES": 2}
    assert "alto_elfo" in elfo["subrazas"]
    assert elfo["subrazas"]["alto_elfo"]["rasgo"]  # info completa, no placeholder
    assert d["razas"]["semielfo"]["bonos_a_eleccion"] == 2
    assert "campeon" in d["subclases"]["guerrero"]


# ---------------------------------------------------------------- fixes del testeo

@pytest.mark.anyio
async def test_skill_check_se_broadcastea(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    await c.post("/api/characters", json=GUERRERO2, headers=h)
    await c.post(f"/api/campaigns/{cid}/skill-check",
                 json={"habilidad": "atletismo", "cd": 10,
                       "descripcion": "trepo el muro"}, headers=h)
    msgs = (await c.get(f"/api/campaigns/{cid}/messages?since=0",
                        headers=h)).json()
    broadcast = [m for m in msgs if m["autor"] == "sistema"
                 and "🎲" in m["contenido"] and "atletismo" in m["contenido"]]
    assert broadcast, "la tirada debe verse como mensaje de sistema para todos"
    assert "d20=" in broadcast[0]["contenido"]


@pytest.mark.anyio
async def test_undo_y_regenerate(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    await c.post("/api/characters", json=GUERRERO2, headers=h)
    await c.post(f"/api/campaigns/{cid}/say",
                 json={"texto": "miro el cielo"}, headers=h)
    n_antes = len((await c.get(f"/api/campaigns/{cid}/messages?since=0",
                               headers=h)).json())
    # regenerar: borra el dm y re-narra (dummy: instantáneo)
    r = await c.post(f"/api/campaigns/{cid}/narration/regenerate",
                     json={}, headers=h)
    assert r.status_code == 200
    # deshacer el par acción→dm
    r = await c.post(f"/api/campaigns/{cid}/narration/undo",
                     json={}, headers=h)
    assert r.status_code == 200
    msgs = (await c.get(f"/api/campaigns/{cid}/messages?since=0",
                        headers=h)).json()
    assert not any(m["contenido"] == "miro el cielo" for m in msgs)


@pytest.mark.anyio
async def test_typing_heartbeat(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    await c.post("/api/characters", json=GUERRERO2, headers=h)
    await c.post(f"/api/campaigns/{cid}/typing", json={}, headers=h)
    est = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
    assert "Borin" in est["escribiendo"]


@pytest.mark.anyio
async def test_efecto_quitar_item(client):
    from app.effects import aplicar_efectos
    from app.db import SessionLocal
    from app.models import Campaign, Character
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    char_id = (await c.post("/api/characters", json=GUERRERO2,
                            headers=h)).json()["character_id"]
    async with SessionLocal() as db:
        camp = await db.get(Campaign, cid)
        char = await db.get(Character, char_id)
        char.inventario = [{"nombre": "Antorcha", "cantidad": 2},
                           {"nombre": "Cuerda de cáñamo (15m)", "cantidad": 1}]
        # match exacto + match por inclusión + inexistente ignorado
        log = await aplicar_efectos(db, camp, {
            "quitar_item": [{"nombre": "antorcha", "cantidad": 1},
                            {"nombre": "cuerda", "cantidad": 1},
                            {"nombre": "banjo", "cantidad": 1}]}, char)
        await db.commit()
        aplicados = [a for a in log["aplicados"] if a[0] == "quitar_item"]
        assert len(aplicados) == 2
        assert ("quitar_item", "banjo") in log["rechazados"]
    ficha = (await c.get(f"/api/characters/{char_id}/sheet", headers=h)).json()
    inv = {i["nombre"]: i["cantidad"] for i in ficha["inventario"]}
    assert inv.get("Antorcha") == 1 and "Cuerda de cáñamo (15m)" not in inv


# ---------------------------------------------------------------- dracónido

DRACONIDO = {
    "nombre": "Rhogar", "raza": "draconido", "subraza": "oro",
    "clase": "guerrero", "metodo": "libre", "estilo_combate": "duelo",
    "atributos": {"FUE": 15, "DES": 12, "CON": 14, "INT": 8, "SAB": 10,
                  "CAR": 10},
    "armadura": "coraza", "arma_equipada": "espada_larga",
}


@pytest.mark.anyio
async def test_aliento_de_dragon(client):
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    r = await c.post("/api/characters", json=DRACONIDO, headers=h)
    assert r.status_code == 200, r.text
    char_id = r.json()["character_id"]
    ficha = (await c.get(f"/api/characters/{char_id}/sheet", headers=h)).json()
    assert "aliento_de_dragon" in ficha["recursos_clase"]
    assert any(x["nombre"] == "aliento_de_dragon"
               for x in ficha["habilidades_activas"])

    # fuera de combate rebota
    r = await c.post(f"/api/campaigns/{cid}/class-ability",
                     json={"nombre": "aliento_de_dragon",
                           "objetivo_npc_id": 1}, headers=h)
    assert r.status_code == 409

    await c.post(f"/api/campaigns/{cid}/combat/start",
                 json={"monstruos": ["ogro"]}, headers=h)
    est = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
    if est["estado"] != "combate":
        pytest.skip("azar")
    turno = est["combate"]["orden"][est["combate"]["turno_idx"]]
    if turno["id"] != f"pj_{char_id}":
        pytest.skip("iniciativa del ogro")
    npc_id = int([e for e in est["combate"]["orden"]
                  if e["tipo"] == "npc"][0]["id"].split("_")[1])
    r = await c.post(f"/api/campaigns/{cid}/class-ability",
                     json={"nombre": "aliento_de_dragon",
                           "objetivo_npc_id": npc_id}, headers=h)
    assert r.status_code == 200, r.text
    d2 = r.json()
    assert d2["elemento"] == "fuego" and d2["cd"] == 8 + 2 + 2
    assert d2["danio_final"] >= 1
    # segundo uso agotado
    r = await c.post(f"/api/campaigns/{cid}/class-ability",
                     json={"nombre": "aliento_de_dragon",
                           "objetivo_npc_id": npc_id}, headers=h)
    assert r.status_code == 400


def test_resistencia_mitad_de_danio():
    from engine.entities import Criatura
    from engine.rules import danio_con_resistencia
    c = Criatura(id="x", nombre="x", nivel=1,
                 atributos={"FUE": 10, "DES": 10, "CON": 10,
                            "INT": 10, "SAB": 10, "CAR": 10},
                 pg_actual=20, pg_max=20, resistencias=["fuego"])
    assert danio_con_resistencia(c, 10, "fuego") == (5, True)
    assert danio_con_resistencia(c, 10, "cortante") == (10, False)
    assert danio_con_resistencia(c, 1, "fuego") == (1, True)  # mínimo 1


# ---------------------------------------------------------------- admin + condiciones + economía

@pytest.mark.anyio
async def test_admin_panel(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ADMIN_TOKEN", "secreto123")
    get_settings.cache_clear()
    try:
        c = client
        d = (await c.post("/api/campaigns", json={
            "nombre": "t", "nombre_jugador": "s"})).json()
        h = {"X-Player-Token": d["player_token"]}
        cid = d["campaign_id"]
        char_id = (await c.post("/api/characters", json=GUERRERO2,
                                headers=h)).json()["character_id"]

        # sin token / token malo
        r = await c.get(f"/api/admin/campaigns/{cid}/full")
        assert r.status_code == 401
        r = await c.get(f"/api/admin/campaigns/{cid}/full",
                        headers={"X-Admin-Token": "nop"})
        assert r.status_code == 401

        ha = {"X-Admin-Token": "secreto123"}
        d2 = (await c.get(f"/api/admin/campaigns/{cid}/full",
                          headers=ha)).json()
        assert d2["personajes"][0]["nombre"] == "Borin"

        # patch de PJ con whitelist
        r = await c.post(f"/api/admin/campaigns/{cid}/character/{char_id}",
                         json={"campos": {"oro": 500, "pg_actual": 5}},
                         headers=ha)
        assert r.status_code == 200
        r = await c.post(f"/api/admin/campaigns/{cid}/character/{char_id}",
                         json={"campos": {"nombre": "Hackeado"}}, headers=ha)
        assert r.status_code == 400  # campo fuera de whitelist

        ficha = (await c.get(f"/api/characters/{char_id}/sheet",
                             headers=h)).json()
        assert ficha["monedas"]["mo"] == 500 and ficha["pg_actual"] == 5

        # hablar como DM
        r = await c.post(f"/api/admin/campaigns/{cid}/say-as-dm",
                         json={"texto": "Un trueno parte el cielo."},
                         headers=ha)
        assert r.status_code == 200
        msgs = (await c.get(f"/api/campaigns/{cid}/messages?since=0",
                            headers=h)).json()
        assert any(m["autor"] == "dm" and "trueno" in m["contenido"]
                   for m in msgs)

        # forzar fin de combate
        await c.post(f"/api/campaigns/{cid}/combat/start",
                     json={"monstruos": ["goblin"]}, headers=h)
        r = await c.post(f"/api/admin/campaigns/{cid}/end-combat",
                         headers=ha)
        assert r.status_code == 200
        est = (await c.get(f"/api/campaigns/{cid}", headers=h)).json()
        assert est["estado"] == "exploracion"
    finally:
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
        get_settings.cache_clear()


@pytest.mark.anyio
async def test_condiciones_dm_y_economia(client):
    from app.db import SessionLocal
    from app.models import NPC, Campaign, Character
    from app.effects import aplicar_efectos
    c = client
    d = (await c.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    char_id = (await c.post("/api/characters", json=GUERRERO2,
                            headers=h)).json()["character_id"]
    async with SessionLocal() as db:
        camp = await db.get(Campaign, cid)
        char = await db.get(Character, char_id)
        char.monedas = {"mo": 100, "mp": 0, "mc": 0}
        npc = NPC(campaign_id=cid, nombre="Grog", tipo="monstruo",
                  actitud="hostil", en_escena=True,
                  stats={"pg": 20, "ca_fija": 12})
        db.add(npc)
        await db.flush()

        # aplicar condición al NPC + tienda: pagar 60, luego 80 (no alcanza)
        log = await aplicar_efectos(db, camp, {
            "aplicar_condicion": {"objetivo": "Grog", "tipo": "aturdido",
                                  "rondas": 9},   # se capea a 3
            "quitar_monedas": 60,
        }, char)
        await db.commit()
        assert ("quitar_monedas", 60) in log["aplicados"]
        cond = [x for x in npc.condiciones if x["tipo"] == "aturdido"]
        assert cond and cond[0]["rondas"] == 3
        assert char.monedas["mo"] == 40

        log2 = await aplicar_efectos(db, camp, {"quitar_monedas": 80}, char)
        await db.commit()
        assert any(x[0] == "quitar_monedas" for x in log2["rechazados"])
        assert char.monedas["mo"] == 40  # no se fue en negativo

        # condición inválida rechazada
        log3 = await aplicar_efectos(db, camp, {
            "aplicar_condicion": {"objetivo": "Grog", "tipo": "petrificado"}},
            char)
        assert any(x[0] == "aplicar_condicion" for x in log3["rechazados"])

        # quitar_condicion la limpia
        await aplicar_efectos(db, camp, {
            "quitar_condicion": {"objetivo": "Grog", "tipo": "aturdido"}},
            char)
        await db.commit()
        assert not any(x["tipo"] == "aturdido" for x in npc.condiciones)


def test_tick_y_matriz_de_condiciones():
    from engine.entities import Criatura
    from engine.rules import (resolver_ataque, tick_condiciones,
                              tirada_salvacion)
    from engine.content import ARMAS
    base = {a: 10 for a in ("FUE", "DES", "CON", "INT", "SAB", "CAR")}

    # tick: 2 rondas → 1 → expira; sin rondas persiste
    c = Criatura(id="x", nombre="x", nivel=1, atributos=base,
                 pg_actual=10, pg_max=10,
                 condiciones=[{"tipo": "aturdido", "rondas": 2},
                              {"tipo": "envenenado"}])
    assert tick_condiciones(c) == []
    assert tick_condiciones(c) == ["aturdido"]
    assert c.tiene_condicion("envenenado")

    # aturdido: auto-fallo FUE/DES, ventaja para el atacante
    v = Criatura(id="v", nombre="v", nivel=1, atributos=base,
                 pg_actual=10, pg_max=10,
                 condiciones=[{"tipo": "aturdido"}])
    s = tirada_salvacion(v, "DES", 10)
    assert not s["exito"] and s.get("auto_fallo")
    assert tirada_salvacion(v, "SAB", 1)["exito"] in (True, False)  # no auto

    a = Criatura(id="a", nombre="a", nivel=1, atributos=base,
                 pg_actual=10, pg_max=10)
    r = resolver_ataque(a, v, ARMAS["mazo"])
    assert r["ventaja"] == 1

    # restringido: desventaja atacando
    a2 = Criatura(id="a2", nombre="a2", nivel=1, atributos=base,
                  pg_actual=10, pg_max=10,
                  condiciones=[{"tipo": "restringido"}])
    v2 = Criatura(id="v2", nombre="v2", nivel=1, atributos=base,
                  pg_actual=10, pg_max=10)
    r2 = resolver_ataque(a2, v2, ARMAS["mazo"])
    assert r2["ventaja"] == -1
