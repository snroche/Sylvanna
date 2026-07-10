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


@app.get("/api/content")
async def catalogo():
    """Catálogo para la UI: conjuros (con nivel), monstruos, armas, armaduras."""
    from engine.content import ARMADURAS, ARMAS, CONJUROS, MONSTRUOS
    oficiales = ["cuero", "cuero_tachonado", "camisa_de_mallas", "coraza",
                 "media_armadura", "ring_mail", "cota_de_mallas",
                 "armadura_de_placas"]
    return {
        "conjuros": {k: {"nivel": v["nivel"],
                         "nombre": v.get("nombre", k.replace("_", " "))}
                     for k, v in CONJUROS.items()},
        "monstruos": sorted(MONSTRUOS),
        "armas": sorted(set(ARMAS)),
        "armaduras": oficiales,
    }


@app.get("/api/health/narrator")
async def health_narrator():
    """Test unitario del narrador: una llamada real mínima a OpenRouter.
    Devuelve la causa exacta si falla. No requiere auth (no expone la key)."""
    from app.config import get_settings
    from app.narrator import NarradorError, completar
    s = get_settings()
    if not s.openrouter_api_key:
        return {"ok": False, "narrador": "dummy",
                "detalle": "OPENROUTER_API_KEY no configurada"}
    try:
        r = await completar("Respondé exactamente: OK", max_tokens=10,
                            reintentos=0)
        return {"ok": True, "modelos": s.modelos, "respuesta": (r or "")[:50]}
    except NarradorError as e:
        return {"ok": False, "status": e.status, "modelos": s.modelos,
                "detalle": e.mensaje_humano(), "crudo": e.detalle[:300]}


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
