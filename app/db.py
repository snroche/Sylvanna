"""Engine y sesiones async de SQLAlchemy.

Funciona igual con sqlite+aiosqlite (dev local) y postgresql+asyncpg (Neon).
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

_kwargs = {}
if settings.db_es_postgres:
    _kwargs = {
        "connect_args": {"ssl": True},   # Neon requiere SSL
        "pool_size": 3,                  # free tier: pocas conexiones
        "max_overflow": 2,
        "pool_pre_ping": True,           # Neon suspende la DB inactiva; esto la despierta
    }

engine = create_async_engine(settings.db_url_normalizada, **_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def crear_tablas():
    from . import models  # noqa: F401  (registra los modelos)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
