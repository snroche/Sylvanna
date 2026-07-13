"""Economía: se puede pagar con plata/cobre (no solo oro) y el DM otorga mixto."""
import pytest

from app.effects import aplicar_efectos
from app.models import Campaign, Character

GUERRERO = {
    "nombre": "Thorin", "raza": "enano", "subraza": "enano_de_las_montanas",
    "clase": "guerrero", "metodo": "libre", "estilo_combate": "duelo",
    "atributos": {"FUE": 16, "DES": 12, "CON": 14, "INT": 8, "SAB": 10, "CAR": 13},
    "habilidades": ["atletismo", "intimidacion"],
    "armadura": "coraza", "escudo": True, "arma_equipada": "espada_larga",
}


async def _campania_con_pj(client):
    d = (await client.post("/api/campaigns", json={
        "nombre": "t", "nombre_jugador": "s"})).json()
    h = {"X-Player-Token": d["player_token"]}
    cid = d["campaign_id"]
    char_id = (await client.post("/api/characters", json=GUERRERO,
                                 headers=h)).json()["character_id"]
    return cid, char_id


@pytest.mark.anyio
async def test_pagar_con_plata_precio_en_oro(client):
    from app.db import SessionLocal
    cid, char_id = await _campania_con_pj(client)
    async with SessionLocal() as db:
        camp = await db.get(Campaign, cid)
        char = await db.get(Character, char_id)
        char.monedas = {"mo": 0, "mp": 50, "mc": 0}   # 5 PO en plata, 0 en oro
        log = await aplicar_efectos(db, camp, {"quitar_monedas": 3}, char)
        await db.commit()
        assert ("quitar_monedas", 3) in log["aplicados"]
        # 500 cp - 300 cp = 200 cp → 2 mo
        assert char.monedas == {"mo": 2, "mp": 0, "mc": 0}


@pytest.mark.anyio
async def test_da_cambio_en_denominaciones(client):
    from app.db import SessionLocal
    cid, char_id = await _campania_con_pj(client)
    async with SessionLocal() as db:
        camp = await db.get(Campaign, cid)
        char = await db.get(Character, char_id)
        char.monedas = {"mo": 0, "mp": 0, "mc": 250}   # 2.5 PO en cobre
        await aplicar_efectos(db, camp, {"quitar_monedas": 1}, char)
        await db.commit()
        assert char.monedas == {"mo": 1, "mp": 5, "mc": 0}   # 150 cp de cambio


@pytest.mark.anyio
async def test_fondos_insuficientes_no_dejan_negativo(client):
    from app.db import SessionLocal
    cid, char_id = await _campania_con_pj(client)
    async with SessionLocal() as db:
        camp = await db.get(Campaign, cid)
        char = await db.get(Character, char_id)
        char.monedas = {"mo": 0, "mp": 5, "mc": 0}   # 0.5 PO
        log = await aplicar_efectos(db, camp, {"quitar_monedas": 1}, char)
        await db.commit()
        assert any(x[0] == "quitar_monedas" for x in log["rechazados"])
        assert char.monedas == {"mo": 0, "mp": 5, "mc": 0}   # intacto


@pytest.mark.anyio
async def test_dm_otorga_monedas_mixtas(client):
    from app.db import SessionLocal
    cid, char_id = await _campania_con_pj(client)
    async with SessionLocal() as db:
        camp = await db.get(Campaign, cid)
        char = await db.get(Character, char_id)
        char.monedas = {"mo": 0, "mp": 0, "mc": 0}
        await aplicar_efectos(
            db, camp, {"otorgar_monedas": {"mo": 1, "mp": 5, "mc": 5}}, char)
        await db.commit()
        await db.refresh(char)
        assert char.monedas == {"mo": 1, "mp": 5, "mc": 5}
