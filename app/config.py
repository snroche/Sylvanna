"""Configuración. Lee variables de entorno (o .env local en desarrollo).

Variables en Render:
  OPENROUTER_API_KEY
  OPENROUTER_MODEL
  OPENROUTER_MODEL_SUMMARIZER
  DATABASE_URL
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str = ""          # vacío → narrador dummy (útil en dev)
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_model_summarizer: str = ""  # vacío → usa openrouter_model
    database_url: str = "sqlite+aiosqlite:///./local.db"  # default para dev local

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def db_url_normalizada(self) -> str:
        """Neon da 'postgresql://...' — lo convertimos a driver asyncpg."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg no acepta sslmode en el query string
        return url.replace("?sslmode=require", "").replace("&sslmode=require", "")

    @property
    def db_es_postgres(self) -> bool:
        return "postgresql" in self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
