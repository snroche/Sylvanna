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


# ALTERs idempotentes para columnas agregadas después del primer deploy.
# create_all solo crea tablas nuevas, no altera existentes.
MIGRACIONES = [
    "ALTER TABLE campaigns ADD COLUMN narrando BOOLEAN DEFAULT FALSE",
    "ALTER TABLE campaigns ADD COLUMN ultimo_descanso_largo_min INTEGER DEFAULT -10000",
    "ALTER TABLE characters ADD COLUMN alineamiento VARCHAR(30) DEFAULT 'neutral'",
    "ALTER TABLE characters ADD COLUMN estilo_combate VARCHAR(30)",
    "ALTER TABLE characters ADD COLUMN recursos_clase JSON",
    "ALTER TABLE characters ADD COLUMN feats JSON",
    "ALTER TABLE campaigns ADD COLUMN descripcion TEXT DEFAULT ''",
    "ALTER TABLE characters ADD COLUMN subclase VARCHAR(60)",
    "ALTER TABLE campaigns ADD COLUMN typing JSON",
    "ALTER TABLE characters ADD COLUMN opciones_clase JSON",
    "ALTER TABLE characters ADD COLUMN genero VARCHAR(20) DEFAULT ''",
    "ALTER TABLE campaigns ADD COLUMN tiradas_pendientes JSON",
]


async def crear_tablas():
    from sqlalchemy import text

    from . import models  # noqa: F401  (registra los modelos)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for sql in MIGRACIONES:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
        except Exception:
            pass  # la columna ya existe
