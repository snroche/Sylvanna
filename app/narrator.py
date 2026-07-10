"""Narrador: cliente OpenRouter + contrato JSON de salida.

El LLM narra y puede declarar efectos de mundo en un bloque JSON final.
El backend parsea, valida contra el schema permitido y aplica. Campos
fuera del contrato se ignoran: el schema ES el límite de poder del narrador.
"""
from __future__ import annotations

import json
import re

import httpx

from .config import get_settings

SYSTEM_PROMPT = """Sos el narrador (DM) de una campaña de D&D 5e en español rioplatense.
Recibís el estado del mundo y resultados mecánicos YA RESUELTOS por el sistema.

REGLAS ESTRICTAS:
- Nunca inventes números, tiradas, daño ni cambios de PG/recursos: solo narrás lo que el sistema resolvió.
- Si el resultado es un fallo, el primer párrafo describe qué salió mal, sin suavizar.
- El mundo es duro y consecuente. Los NPCs solo saben lo que dice su ficha.
- No guíes al jugador ni insinúes la opción correcta.
- Respondé en 1-3 párrafos de narración, sin listas ni encabezados.

CONTRATO DE SALIDA:
Después de la narración, si (y solo si) corresponde algún efecto de mundo, agregá al final un bloque:
```json
{...}
```
Campos permitidos (todos opcionales):
- "nuevos_npcs": [{"nombre": str, "rol": str, "personalidad": str, "motivacion": str, "actitud": "amistoso|neutral|desconfiado|hostil", "secretos": str}]
- "actualizar_npc": [{"npc_id": int, "actitud": str, "nota_sabe_del_grupo": str}]
- "nueva_quest": {"titulo": str, "descripcion": str, "principal": bool, "npc_origen_id": int|null}
- "completar_quest": {"quest_id": int, "resultado": "completada|fallida"}
- "consecuencia_pendiente": {"evento": str, "efecto": str, "activacion": str}
- "resolver_consecuencia": {"consecuencia_id": int}
- "inicia_combate": {"monstruos": ["goblin", ...]}  (opciones: goblin, lobo, bandido, esqueleto, zombi, orco)
- "npcs_salen_de_escena": [int, ...]
- "otorgar_xp": int  (solo hitos narrativos; el XP de combate lo calcula el sistema)
- "loot": [{"nombre": str, "cantidad": int}]  (objetos que el grupo encuentra/recibe; máx 5)
- "otorgar_monedas": int  (monedas de oro encontradas/pagadas; usá con mesura)
- "avanzar_tiempo_min": int
- "nueva_ubicacion": str
No declares efectos que no correspondan a lo que acaba de pasar."""


async def completar(prompt: str, modelo: str | None = None,
                    system: str | None = None, max_tokens: int = 700) -> str | None:
    """Llamada genérica a OpenRouter. None si no hay key o falla."""
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.openrouter_api_key}"},
                json={"model": modelo or s.openrouter_model,
                      "max_tokens": max_tokens, "messages": messages},
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"[narrador] error OpenRouter: {e}")
        return None


CAMPOS_PERMITIDOS = {
    "nuevos_npcs", "actualizar_npc", "nueva_quest", "completar_quest",
    "consecuencia_pendiente", "resolver_consecuencia", "inicia_combate",
    "npcs_salen_de_escena", "otorgar_xp", "avanzar_tiempo_min",
    "nueva_ubicacion", "loot", "otorgar_monedas",
}

_JSON_BLOQUE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_SUELTO = re.compile(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})\s*$", re.DOTALL)


def parsear_salida(texto: str) -> tuple[str, dict]:
    """Separa narración de efectos. Efectos inválidos → dict vacío (fail-safe)."""
    if not texto:
        return "", {}
    m = _JSON_BLOQUE.search(texto)
    if not m:
        m = _JSON_SUELTO.search(texto.strip())
    if not m:
        return texto.strip(), {}
    try:
        crudo = json.loads(m.group(1))
    except json.JSONDecodeError:
        return texto.replace(m.group(0), "").strip(), {}
    if not isinstance(crudo, dict):
        return texto.replace(m.group(0), "").strip(), {}
    efectos = {k: v for k, v in crudo.items() if k in CAMPOS_PERMITIDOS}
    narracion = texto.replace(m.group(0), "").strip()
    return narracion, efectos


async def narrar(contexto: str, accion: str) -> tuple[str, dict]:
    """Devuelve (narración, efectos). Con dummy: narración mínima, sin efectos."""
    crudo = await completar(f"{contexto}\n\n---\nACCIÓN A NARRAR:\n{accion}",
                            system=SYSTEM_PROMPT)
    if crudo is None:
        return f"[DM dummy] Resuelto: {accion[:200]}", {}
    return parsear_salida(crudo)
