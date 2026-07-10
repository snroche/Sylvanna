"""Sistema de dados. Único punto del proyecto donde se genera azar.

Todas las funciones devuelven dicts serializables: se guardan en la tabla Roll,
se broadcastean por WebSocket y se inyectan al prompt del narrador.
"""
from __future__ import annotations

import random
import re

_RNG = random.SystemRandom()  # RNG criptográfico: nadie puede predecir el seed

_EXPR_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")


def roll(expr: str) -> dict:
    """Resuelve una expresión tipo '2d6+3'.

    Returns:
        {"expr": "2d6+3", "dados": [4, 2], "mod": 3, "total": 9}
    """
    m = _EXPR_RE.fullmatch(expr.replace(" ", ""))
    if not m:
        raise ValueError(f"Expresión de dados inválida: {expr!r}")
    n, caras, mod = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if not (1 <= n <= 100) or caras not in (2, 4, 6, 8, 10, 12, 20, 100):
        raise ValueError(f"Expresión fuera de rango: {expr!r}")
    dados = [_RNG.randint(1, caras) for _ in range(n)]
    return {"expr": expr, "dados": dados, "mod": mod, "total": sum(dados) + mod}


def d20(ventaja: int = 0) -> dict:
    """Tirada de d20 con ventaja (1), desventaja (-1) o normal (0).

    Returns:
        {"tiradas": [14, 6], "natural": 14, "critico": False, "pifia": False,
         "ventaja": 1}
    """
    if ventaja not in (-1, 0, 1):
        raise ValueError("ventaja debe ser -1, 0 o 1")
    tiradas = [_RNG.randint(1, 20) for _ in range(2 if ventaja else 1)]
    natural = max(tiradas) if ventaja > 0 else min(tiradas)
    return {
        "tiradas": tiradas,
        "natural": natural,
        "critico": natural == 20,
        "pifia": natural == 1,
        "ventaja": ventaja,
    }
