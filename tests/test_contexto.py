"""Ventana de contexto del DM: no debe haber hueco entre resumen y verbatim."""
import pytest

from app.context import MENSAJES_RECIENTES, construir_contexto
from app.models import Campaign, Message


@pytest.mark.anyio
async def test_ventana_muestra_todos_los_no_resumidos(db_session):
    db = db_session
    camp = Campaign(nombre="t", ubicacion_actual="La Raíz Podrida")
    db.add(camp)
    await db.flush()
    # más mensajes que la vieja ventana de 12, pero todos sin resumir
    for i in range(25):
        db.add(Message(campaign_id=camp.id, autor="dm", autor_nombre="DM",
                       contenido=f"evento numero {i}"))
    await db.flush()

    ctx = await construir_contexto(db, camp)
    # el más viejo (0) y el más nuevo (24) están ambos: no hay hueco de memoria
    assert "evento numero 0" in ctx
    assert "evento numero 24" in ctx


@pytest.mark.anyio
async def test_piso_de_ventana(db_session):
    db = db_session
    camp = Campaign(nombre="t")
    db.add(camp)
    await db.flush()
    for i in range(5):
        db.add(Message(campaign_id=camp.id, autor="dm", autor_nombre="DM",
                       contenido=f"linea {i}"))
    await db.flush()
    ctx = await construir_contexto(db, camp)
    assert "linea 0" in ctx and "linea 4" in ctx
    assert MENSAJES_RECIENTES >= 30   # ventana amplia
