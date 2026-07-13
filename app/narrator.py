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
- NUNCA hables, actúes ni decidas por los PERSONAJES DE LOS JUGADORES. Si un \
jugador se dirige a otro jugador, no respondas en su nombre: narrá a lo sumo \
la reacción del entorno o de los NPCs presentes, o dejá el espacio abierto.
- Usá los nombres de conjuros, armas y objetos tal como aparecen en el estado \
(pueden estar en inglés): no inventes traducciones rebuscadas de términos de juego.
- Si la acción declarada tiene resultado INCIERTO (buscar, convencer, trepar, \
notar, forzar cerraduras...) y NO vino con una tirada ya resuelta, NO decidas \
el resultado: narrá el intento y emití pedir_tirada. Cuando llegue la tirada \
resuelta, narrá según ese resultado.
- COMBATE INMINENTE: en cuanto haya hostilidad clara (enemigos que atacan, \
emboscada, alguien desenvaina, una amenaza que se lanza al ataque), NO estires \
la escena: emití inicia_combate EN ESA MISMA respuesta y describí solo el \
primer choque en 1-2 frases. No narres varios turnos de pelea "por tu cuenta": \
apenas empieza la violencia, el sistema toma la iniciativa. Es preferible \
arrancar el combate de más que hacer esperar a la mesa.
- Mantené el inventario coherente con la ficción: si un PJ deja, entrega, \
pierde, rompe o consume un objeto, emití quitar_item; si recibe o recupera \
algo, emití loot.
- MERCADERES: cuando un PJ compra, emití loot (el objeto) + quitar_monedas \
(el precio) EN LA MISMA respuesta. Precios coherentes con el SRD: poción de \
curación 50 PO, espada larga 15 PO, cota de mallas 75 PO. Si vende, emití \
quitar_item + otorgar_monedas (a mitad de precio). Nunca regales equipo caro.
- El bloque JSON va SIEMPRE al final, COMPLETO y BREVE (máximo 5 campos). Si \
te falta espacio, acortá la narración: el JSON no se corta jamás.
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
- "inicia_combate": {"monstruos": ["goblin", ...]}  (opciones: goblin, lobo, bandido, esqueleto, zombi, orco). EMITILO APENAS el combate sea obvio o inevitable, en la misma respuesta en que aparece la amenaza: no narres la pelea vos, dejá que el sistema tire iniciativa. No hace falta que los PJs "declaren" que atacan primero.
- "npcs_salen_de_escena": [int, ...]
- "otorgar_xp": int  (solo hitos narrativos; el XP de combate lo calcula el sistema)
- "loot": [{"nombre": str, "cantidad": int}]  (objetos que el grupo encuentra/recibe; máx 5)
- "quitar_item": [{"nombre": str, "cantidad": int}]  (objetos que el PJ actor deja, entrega, pierde o consume en la ficción)
- "pedir_tirada": {"habilidad": str, "a_quien": str, "cd": int}  (pedile una tirada al PJ nombrado o a "todos". Elegí la CD según la dificultad real: 5 muy fácil, 10 fácil, 15 media, 20 difícil, 25 muy difícil, 30 casi imposible. NUNCA narres el resultado en este mensaje: esperá a que tiren. Si es a "todos", el sistema junta las tiradas de TODOS y recién cuando estén todas te pide narrar el desenlace: no sigas la escena hasta entonces)
- "quitar_monedas": int  (el PJ actor PAGA ese oro: compras, sobornos, peajes. Si no le alcanza, el sistema lo rechaza y debés renegociar)
- "aplicar_condicion": {"objetivo": str, "tipo": str, "rondas": int}  (tipos válidos: envenenado, asustado, cegado, derribado, restringido, aturdido, paralizado, agarrado; máx 3 rondas; usalo con moderación y justificación en la ficción)
- "quitar_condicion": {"objetivo": str, "tipo": str}
- "otorgar_inspiracion": str  (nombre del PJ que gana Inspiración Heroica: ventaja en su próxima tirada; premiá buen rol o ideas creativas, con mesura)
- "otorgar_monedas": int  (monedas de oro encontradas/pagadas; usá con mesura)
- "avanzar_tiempo_min": int
- "nueva_ubicacion": str
No declares efectos que no correspondan a lo que acaba de pasar."""


class NarradorError(Exception):
    """Error real del narrador (la key existe pero la llamada falló)."""

    def __init__(self, status: int | None, detalle: str):
        self.status = status
        self.detalle = detalle
        super().__init__(f"{status}: {detalle}")

    def mensaje_humano(self) -> str:
        if self.status == 401:
            return "API key de OpenRouter inválida (revisá OPENROUTER_API_KEY)."
        if self.status == 402:
            return "Sin créditos en OpenRouter (o balance negativo)."
        if self.status == 404:
            return ("El modelo no existe o no está disponible "
                    "(revisá OPENROUTER_MODEL, incluido el sufijo :free).")
        if self.status == 429:
            if "rpd" in self.detalle or "per day" in self.detalle:
                return ("Límite DIARIO del free tier de OpenRouter alcanzado "
                        "(50 requests/día sin créditos; comprar USD 10 una vez "
                        "lo sube a 1000/día para siempre). Se resetea a "
                        "medianoche UTC.")
            return ("Modelo gratuito saturado o límite de 20 req/min alcanzado. "
                    "Reintentá en un rato, o configurá modelos fallback "
                    "separados por coma en OPENROUTER_MODEL.")
        return f"Error del narrador ({self.status}): {self.detalle[:200]}"


async def completar(prompt: str, modelo: str | None = None,
                    system: str | None = None, max_tokens: int = 700,
                    reintentos: int = 2) -> str | None:
    """Llamada a OpenRouter con reintentos y fallback de modelos.

    - None solo si NO hay API key (modo dummy explícito).
    - NarradorError si la key existe pero la llamada falla (el caller decide
      cómo mostrarlo; nunca más errores silenciosos).
    - Reintenta en 429 por minuto / 5xx con backoff. NO reintenta el límite
      diario (rpd): los intentos fallidos también consumen cuota.
    """
    import asyncio

    s = get_settings()
    if not s.openrouter_api_key:
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    modelos = [modelo] if modelo else s.modelos
    payload: dict = {"max_tokens": max_tokens, "messages": messages,
                     "model": modelos[0]}
    if len(modelos) > 1:
        payload["models"] = modelos  # routing con fallback de OpenRouter

    ultimo_error: NarradorError | None = None
    for intento in range(reintentos + 1):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {s.openrouter_api_key}"},
                    json=payload)
            cuerpo = r.text
            if r.status_code != 200:
                ultimo_error = NarradorError(r.status_code, cuerpo[:400])
                print(f"[narrador] HTTP {r.status_code}: {cuerpo[:200]}")
                es_diario = "rpd" in cuerpo or "per day" in cuerpo
                if r.status_code in (429, 500, 502, 503) and not es_diario \
                        and intento < reintentos:
                    await asyncio.sleep(3 * (intento + 1))
                    continue
                raise ultimo_error
            data = r.json()
            # OpenRouter a veces devuelve 200 con {"error": {...}}
            if "error" in data:
                err = data["error"]
                raise NarradorError(err.get("code"), str(err.get("message", err)))
            contenido = data["choices"][0]["message"]["content"]
            if not contenido or not contenido.strip():
                raise NarradorError(200, "respuesta vacía del modelo")
            return contenido
        except NarradorError:
            raise
        except (httpx.HTTPError, KeyError, IndexError,
                json.JSONDecodeError) as e:
            ultimo_error = NarradorError(None, f"{type(e).__name__}: {e}")
            print(f"[narrador] {ultimo_error}")
            if intento < reintentos:
                await asyncio.sleep(3 * (intento + 1))
                continue
            raise ultimo_error
    raise ultimo_error  # inalcanzable, por claridad


CAMPOS_PERMITIDOS = {
    "nuevos_npcs", "actualizar_npc", "nueva_quest", "completar_quest",
    "consecuencia_pendiente", "resolver_consecuencia", "inicia_combate",
    "npcs_salen_de_escena", "otorgar_xp", "avanzar_tiempo_min",
    "nueva_ubicacion", "loot", "otorgar_monedas",
    "quitar_item", "pedir_tirada", "quitar_monedas",
    "aplicar_condicion", "quitar_condicion", "otorgar_inspiracion",
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
        return _limpiar_json_colgado(texto), {}
    try:
        crudo = json.loads(m.group(1))
    except json.JSONDecodeError:
        return _limpiar_json_colgado(texto.replace(m.group(0), "")), {}
    if not isinstance(crudo, dict):
        return _limpiar_json_colgado(texto.replace(m.group(0), "")), {}
    efectos = {k: v for k, v in crudo.items() if k in CAMPOS_PERMITIDOS}
    narracion = texto.replace(m.group(0), "").strip()
    return _limpiar_json_colgado(narracion), efectos


_JSON_COLGADO = re.compile(r"```(?:json)?\s*\{[^`]*$", re.S)


def _limpiar_json_colgado(texto: str) -> str:
    """Si el modelo se quedó sin tokens a mitad del bloque JSON, el fence
    queda sin cerrar y no matchea el parser: acá lo amputamos para que
    nunca se filtre JSON crudo a la mesa."""
    texto = _JSON_COLGADO.sub("", texto)
    return texto.replace("```", "").strip()


async def narrar(contexto: str, accion: str) -> tuple[str, dict]:
    """Devuelve (narración, efectos).

    - Sin API key → narración dummy (modo desarrollo).
    - Con API key y error → propaga NarradorError (el caller lo muestra).
    """
    crudo = await completar(f"{contexto}\n\n---\nACCIÓN A NARRAR:\n{accion}",
                            system=SYSTEM_PROMPT, max_tokens=1100)
    if crudo is None:
        return f"[DM dummy] Resuelto: {accion[:200]}", {}
    return parsear_salida(crudo)
