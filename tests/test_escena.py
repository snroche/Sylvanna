"""Los NPCs dejan la escena cuando el grupo cambia de ubicación."""
import pytest
from sqlalchemy import select

from app.effects import aplicar_efectos
from app.models import NPC, Campaign


@pytest.mark.anyio
async def test_cambio_de_ubicacion_saca_npcs_de_escena(db_session):
    db = db_session
    camp = Campaign(nombre="t", ubicacion_actual="Mercado")
    db.add(camp)
    await db.flush()
    db.add(NPC(campaign_id=camp.id, nombre="Vieja de los hongos",
               tipo="personaje", en_escena=True))
    await db.flush()

    await aplicar_efectos(db, camp, {"nueva_ubicacion": "Taberna La Raíz Podrida"})
    await db.commit()

    res = await db.execute(select(NPC).where(NPC.campaign_id == camp.id))
    npcs = res.scalars().all()
    assert all(not n.en_escena for n in npcs)   # se quedaron en el mercado
    assert camp.ubicacion_actual == "Taberna La Raíz Podrida"


@pytest.mark.anyio
async def test_npcs_nuevos_del_lugar_nuevo_siguen_en_escena(db_session):
    db = db_session
    camp = Campaign(nombre="t", ubicacion_actual="Mercado")
    db.add(camp)
    await db.flush()
    db.add(NPC(campaign_id=camp.id, nombre="Vieja", tipo="personaje",
               en_escena=True))
    await db.flush()

    # el grupo se muda Y aparece un NPC del lugar nuevo en el mismo lote
    await aplicar_efectos(db, camp, {
        "nueva_ubicacion": "Taberna",
        "nuevos_npcs": [{"nombre": "Arnak el tabernero", "rol": "dueño"}]})
    await db.commit()

    res = await db.execute(select(NPC).where(
        NPC.campaign_id == camp.id, NPC.en_escena == True))  # noqa: E712
    en_escena = [n.nombre for n in res.scalars().all()]
    assert en_escena == ["Arnak el tabernero"]   # la vieja salió, Arnak entró


@pytest.mark.anyio
async def test_misma_ubicacion_no_vacia_la_escena(db_session):
    db = db_session
    camp = Campaign(nombre="t", ubicacion_actual="Mercado")
    db.add(camp)
    await db.flush()
    db.add(NPC(campaign_id=camp.id, nombre="Vieja", tipo="personaje",
               en_escena=True))
    await db.flush()

    await aplicar_efectos(db, camp, {"nueva_ubicacion": "Mercado"})  # igual
    await db.commit()

    res = await db.execute(select(NPC).where(
        NPC.campaign_id == camp.id, NPC.en_escena == True))  # noqa: E712
    assert len(res.scalars().all()) == 1   # sigue en escena
