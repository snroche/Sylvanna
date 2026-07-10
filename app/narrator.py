"""Narrador: OpenRouter si hay API key, dummy si no (dev/testing).

En este paso el contexto es simple (estado + últimos mensajes).
El pipeline completo con resumen rodante llega en el paso 3.
"""
from __future__ import annotations

import httpx

from .config import get_settings

SYSTEM_PROMPT = """Sos el narrador (DM) de una campaña de D&D 5e en español rioplatense.
Recibís resultados mecánicos YA RESUELTOS por el sistema. Reglas estrictas:
- Nunca inventes números, tiradas, daño ni cambios de estado: solo narrás lo que \
el sistema resolvió.
- Si el resultado es un fallo, el primer párrafo describe qué salió mal, sin suavizar.
- El mundo es duro y consecuente. Nada de narración complaciente.
- Los NPCs solo saben lo que está en su ficha provista.
- Respondé en 1-3 párrafos, sin listas ni encabezados.
"""


async def narrar(contexto: str, accion: str) -> str:
    s = get_settings()
    if not s.openrouter_api_key:
        return _dummy(accion)
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.openrouter_api_key}"},
                json={
                    "model": s.openrouter_model,
                    "max_tokens": 600,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"{contexto}\n\n---\n{accion}"},
                    ],
                },
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError) as e:
        # el juego no se cae si OpenRouter falla: narración mínima + log
        print(f"[narrador] error OpenRouter: {e}")
        return _dummy(accion) + "\n\n_(narrador IA no disponible, resultado mecánico arriba)_"


def _dummy(accion: str) -> str:
    return f"[DM dummy] Resuelto: {accion}"
