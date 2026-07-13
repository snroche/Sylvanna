"""Combate: log visible de ataques enemigos y limpieza al terminar el combate."""
import pytest

from app.models import Campaign, Character

CAMPO = {"nombre": "La cripta", "nombre_jugador": "A"}
GUERRERO = {
    "nombre": "Thorin", "raza": "enano", "subraza": "enano_de_las_montanas",
    "clase": "guerrero", "metodo": "libre", "estilo_combate": "duelo",
    "atributos": {"FUE": 16, "DES": 12, "CON": 14, "INT": 8, "SAB": 10, "CAR": 13},
    "habilidades": ["atletismo", "intimidacion"],
    "armadura": "coraza", "escudo": True, "arma_equipada": "espada_larga",
}


async def _jugar_combate(client, camp_id, char_id, h):
    """Ataca hasta que el combate termina (o se agota el tope)."""
    for _ in range(80):
        est = (await client.get(f"/api/campaigns/{camp_id}", headers=h)).json()
        if est["estado"] != "combate":
            return est
        turno = est["combate"]["orden"][est["combate"]["turno_idx"]]
        if turno["tipo"] != "pj":
            continue
        goblins = [e for e in est["combate"]["orden"] if e["tipo"] == "npc"]
        if not goblins:
            continue
        npc_id = int(goblins[0]["id"].split("_")[1])
        r = await client.post(f"/api/campaigns/{camp_id}/combat/attack",
                              json={"objetivo_npc_id": npc_id}, headers=h)
        if r.status_code == 400 and "muerto" in r.text:
            return (await client.get(f"/api/campaigns/{camp_id}",
                                     headers=h)).json()
    return (await client.get(f"/api/campaigns/{camp_id}", headers=h)).json()


@pytest.mark.anyio
async def test_ataque_enemigo_deja_log_visible(client):
    d = (await client.post("/api/campaigns", json=CAMPO)).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    (await client.post("/api/characters", json=GUERRERO, headers=h)).json()
    # tres goblins: el guerrero solo mata uno por turno, así que los otros
    # llegan a atacar y el log queda registrado.
    await client.post(f"/api/campaigns/{cid}/combat/start",
                      json={"monstruos": ["goblin", "goblin", "goblin"]},
                      headers=h)
    await _jugar_combate(client, cid, None, h)

    msgs = (await client.get(f"/api/campaigns/{cid}/messages", headers=h)).json()
    sistema = [m["contenido"] for m in msgs if m["autor"] == "sistema"]
    # algún goblin ataca en algún momento y queda registrado con daño o fallo
    assert any("ataca a" in c for c in sistema), sistema


@pytest.mark.anyio
async def test_descripcion_de_ataque_queda_en_el_log(client):
    d = (await client.post("/api/campaigns", json=CAMPO)).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    await client.post("/api/characters", json=GUERRERO, headers=h)
    await client.post(f"/api/campaigns/{cid}/combat/start",
                      json={"monstruos": ["goblin", "goblin", "goblin"]},
                      headers=h)
    est = (await client.get(f"/api/campaigns/{cid}", headers=h)).json()
    turno = est["combate"]["orden"][est["combate"]["turno_idx"]]
    assert turno["tipo"] == "pj"   # el server auto-resuelve NPCs hasta el PJ
    goblins = [e for e in est["combate"]["orden"] if e["tipo"] == "npc"]
    npc_id = int(goblins[0]["id"].split("_")[1])
    r = await client.post(f"/api/campaigns/{cid}/combat/attack",
                          json={"objetivo_npc_id": npc_id,
                                "descripcion": "finto y le tiro al cuello"},
                          headers=h)
    assert r.status_code == 200, r.text
    msgs = (await client.get(f"/api/campaigns/{cid}/messages", headers=h)).json()
    assert any("finto y le tiro al cuello" in m["contenido"] for m in msgs), msgs


@pytest.mark.anyio
async def test_concentracion_se_limpia_al_terminar_el_combate(client):
    from app.db import SessionLocal
    d = (await client.post("/api/campaigns", json=CAMPO)).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    r = await client.post("/api/characters", json=GUERRERO, headers=h)
    char_id = r.json()["character_id"]

    # el personaje entra en combate concentrado en un conjuro
    async with SessionLocal() as s:
        ch = await s.get(Character, char_id)
        ch.concentracion = {"hechizo": "bless", "desde_ronda": 1}
        await s.commit()

    await client.post(f"/api/campaigns/{cid}/combat/start",
                      json={"monstruos": ["goblin"]}, headers=h)
    est = await _jugar_combate(client, cid, char_id, h)
    assert est["estado"] == "exploracion", "el combate debe terminar"

    async with SessionLocal() as s:
        ch = await s.get(Character, char_id)
        assert ch.concentracion is None, "la concentración cae al terminar el combate"
