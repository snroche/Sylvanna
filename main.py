"""Punto de entrada.

Start command en Render:  uvicorn main:app --host 0.0.0.0 --port $PORT
Local:                    uvicorn main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import crear_tablas
from app.routers import actions, campaigns, characters


@asynccontextmanager
async def lifespan(app: FastAPI):
    await crear_tablas()
    yield


app = FastAPI(title="DnD AI DM", lifespan=lifespan)

app.include_router(campaigns.router)
app.include_router(characters.router)
app.include_router(actions.router)


@app.get("/api/health")
async def health():
    from app.config import get_settings
    s = get_settings()
    return {"ok": True,
            "narrador": "openrouter" if s.openrouter_api_key else "dummy",
            "modelo": s.openrouter_model if s.openrouter_api_key else None}


# El frontend se sirve desde la misma app: sin CORS, un solo servicio en Render.
# IMPORTANTE: montar al final para que /api/* tenga prioridad.
app.mount("/", StaticFiles(directory="static", html=True), name="frontend")
