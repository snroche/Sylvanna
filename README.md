# DnD AI DM — Servicio multijugador con narrador IA

Estado: **Paso 2 completo** — motor de reglas + API REST deployable en Render.

## Correr local

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# → http://localhost:8000/docs  (API interactiva)
# Sin variables de entorno usa SQLite local y narrador dummy.
```

Tests: `pip install pytest && python -m pytest tests/ -q` (77 tests)

## Deploy en Render (Web Service)

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment variables:**
  - `OPENROUTER_API_KEY` — key de openrouter.ai
  - `OPENROUTER_MODEL` — ej: `meta-llama/llama-3.3-70b-instruct:free`
  - `OPENROUTER_MODEL_SUMMARIZER` — (opcional, default = OPENROUTER_MODEL)
  - `DATABASE_URL` — connection string de Neon (pegalo tal cual, el código
    normaliza el driver asyncpg y el SSL solo)

Las tablas se crean automáticamente al primer boot.

## Flujo de la API (probalo desde /docs)

1. `POST /api/campaigns` `{nombre, nombre_jugador}` → devuelve `invite_code` y `player_token`
2. `POST /api/campaigns/join` `{invite_code, nombre_jugador}` → token del segundo jugador
3. `POST /api/characters` (header `X-Player-Token`) → crea personaje; el server
   calcula PG, CA, slots según clase
4. `GET /api/characters/{id}/sheet` → ficha completa
5. `POST /api/campaigns/{id}/say` `{texto}` → acción narrativa, responde el DM (IA)
6. `POST /api/campaigns/{id}/skill-check` `{habilidad, cd, descripcion}` → tirada
   resuelta por el server + narración
7. `POST /api/campaigns/{id}/combat/start` `{monstruos: ["goblin","goblin"]}` →
   iniciativa del server; turnos de NPC se auto-resuelven (IA simple v1)
8. `POST /api/campaigns/{id}/combat/attack` `{objetivo_npc_id}` → solo en tu turno
9. `GET /api/campaigns/{id}/messages?since=0` → historial (polling; WS en paso 4)

Toda tirada queda auditada en la tabla `rolls` con el dict de resolución completo.

## Arquitectura

```
engine/    Motor 5e puro (dados, reglas, combate, contenido SRD) — 0 dependencias
app/
  config.py     pydantic-settings (4 env vars)
  db.py         SQLAlchemy async: SQLite dev / Neon prod (SSL + pool free-tier)
  models.py     Campaign, Player, Character, NPC, Quest, PendingConsequence,
                Message, Roll
  hydration.py  Puente DB ↔ entidades del motor
  narrator.py   OpenRouter con fallback dummy si no hay key / falla la red
  routers/      campaigns, characters, actions (say, skill-check, combat)
main.py    FastAPI + frontend estático montado en /
static/    Placeholder (frontend real = paso 5)
```

Principio: el LLM solo narra. Tiradas, validación de turnos, recursos y reglas
viven en el servidor. El cliente nunca puede inventar un resultado.

## Paso 3 — Pipeline del narrador (nuevo)

- **Contexto estructurado** (`app/context.py`): cada llamada al LLM incluye
  resumen rodante + grupo + NPCs en escena (ficha completa) + quests activas +
  consecuencias pendientes + últimos 12 mensajes. Presupuesto ~6-8k tokens.
- **Resumen rodante**: cada 40 mensajes sin resumir, un modelo (el summarizer)
  reescribe `Campaign.resumen_actual` integrando lo nuevo. Los datos duros
  (quests, NPCs, consecuencias) viven en tablas y nunca dependen del resumen.
- **Contrato JSON de salida** (`app/narrator.py` + `app/effects.py`): el LLM
  puede declarar efectos de mundo (crear NPCs/quests/consecuencias, actitudes,
  XP narrativo topeado a 50×nivel, tiempo, ubicación, iniciar combate).
  Campos fuera del schema se ignoran: no puede tocar PG ni recursos.
- **Conjuros en combate** (`POST /combat/cast`): valida preparados/conocidos,
  gasta slot antes de resolver (falla → slot igual gastado), resuelve por tipo
  (ataque mágico / salvación del objetivo / curación / auto como proyectil
  mágico), maneja concentración.
- **XP automática por CR** al ganar un combate, dividida entre PJs vivos.
- **`GET /state`**: quests, NPCs conocidos, consecuencias — el `!misiones` /
  `!lore` del concepto original, con precisión de base de datos.

## Roadmap

1. ✅ Motor de reglas + tests
2. ✅ Models + API REST deployable
3. ✅ Pipeline de contexto: resumen rodante, contrato JSON, conjuros, XP por CR
4. ⬜ WebSockets + batch de exploración (hoy: polling cada 3.5s, jugable)
5. ✅ Frontend completo ("La Mesa") servido desde /

## Frontend — La Mesa

Vanilla JS sin build step (`static/`): abrí la raíz del sitio y listo.
- **Inicio**: fundar campaña o unirse con código de invitación (visible en la
  cabecera para compartir). Sesión en localStorage: recargar no te saca.
- **Creación de personaje**: clase con info de dado/magia, atributos con
  modificador en vivo, chips de habilidades (máx 4), armadura/arma, conjuros
  para lanzadores. El servidor valida y calcula PG/CA/slots.
- **Mesa**: log de narración con polling; los resultados mecánicos aparecen
  como "sellos" de tinta (d20 14+5=19 vs CA 15 → IMPACTA) separados de la
  prosa del DM. Composer de exploración (actuar / tirada de habilidad) que
  cambia a modo combate automáticamente: barra de iniciativa con turno
  resaltado, objetivos con estado de salud narrativo (ileso/herido/malherido,
  nunca PG exactos), atacar y lanzar conjuros solo en tu turno.
- **Ficha viva**: PG con barra, atributos, CA, slots como puntos, condiciones,
  concentración. **Mundo**: misiones, NPCs conocidos con actitud, presagios
  (consecuencias pendientes) y la crónica (resumen rodante).
- Móvil: tabs Juego/Ficha/Mundo. Tolerante al cold start de Render.
