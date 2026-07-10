"""Configuración compartida de tests.

IMPORTANTE: el engine de SQLAlchemy es un singleton creado en el primer
import de app.db, por lo que TODOS los tests de API comparten la misma DB.
Este conftest fija el entorno ANTES de cualquier import de la app y provee
fixtures que limpian la DB entre tests.
"""
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_suite.db"
os.environ["OPENROUTER_API_KEY"] = ""   # narrador dummy en tests

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _db_limpia():
    from app.db import engine, crear_tablas
    from app.db import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await crear_tablas()


@pytest.fixture
async def client():
    """Cliente HTTP contra la app con DB limpia."""
    await _db_limpia()
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_session():
    """Sesión directa a DB limpia (para tests de effects/context)."""
    await _db_limpia()
    from app.db import SessionLocal
    async with SessionLocal() as s:
        yield s
