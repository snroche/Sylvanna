"""Punto de entrada.

Start command en Render:  uvicorn main:app --host 0.0.0.0 --port $PORT
Local:                    uvicorn main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import crear_tablas
from app.routers import admin, actions, campaigns, characters


@asynccontextmanager
async def lifespan(app: FastAPI):
    await crear_tablas()
    yield


app = FastAPI(title="DnD AI DM", lifespan=lifespan)

app.include_router(admin.router)
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
    from engine.content import (NIVEL_SUBCLASE, RAZAS, SUBCLASES_SRD)
    razas = {}
    for k, r in RAZAS.items():
        if k == "tiflin":   # alias de compatibilidad: no listar
            continue
        razas[k] = {
            "bonos": r["bonos"], "velocidad_m": r.get("velocidad_m", 9),
            "rasgo": r["rasgo"],
            "bonos_a_eleccion": r.get("bonos_a_eleccion", 0),
            "subrazas": {sk: {"bonos": sv.get("bonos", {}),
                              "rasgo": sv.get("rasgo", ""),
                              "velocidad_m": sv.get("velocidad_m"),
                              "bonos_a_eleccion": sv.get("bonos_a_eleccion")}
                         for sk, sv in r["subrazas"].items()},
        }
    return {
        "conjuros": {k: {"nivel": v["nivel"],
                         "nombre": v.get("nombre", k.replace("_", " "))}
                     for k, v in CONJUROS.items()},
        "monstruos": sorted(MONSTRUOS),
        "armas": sorted(set(ARMAS)),
        "armaduras": oficiales,
        "razas": razas,
        "subclases": SUBCLASES_SRD,
        "objetos_magicos": len(__import__("engine.content",
                                          fromlist=["x"]).OBJETOS_MAGICOS),
        "nivel_subclase": NIVEL_SUBCLASE,
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
