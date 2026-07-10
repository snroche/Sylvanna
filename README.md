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
4. ⬜ WebSockets (el polling adaptativo lo hace innecesario para grupos chicos)
5. ✅ Frontend completo ("La Mesa") servido desde /
6. ✅ Versión completa: latencia, descansos, inventario, niveles, timeout,
   retomar campaña, reemplazo tras muerte

## Versión completa — qué se agregó

**Latencia (el cambio grande):** las acciones devuelven la resolución mecánica
al instante (~25ms) y la narración del LLM corre en un BackgroundTask. La UI
muestra "El DM narra…" y polling adaptativo (1.3s esperando narración o en
combate, 5s en reposo) la trae cuando está. El resumen rodante también corre
en background. Si OpenRouter falla, la mecánica ya quedó aplicada y un mensaje
de sistema lo avisa.

**Descansos:** corto por personaje (gasta dados de golpe; el brujo recupera
slots) y largo grupal (PG/slots al máximo, mitad de dados; limitado a uno por
día de juego). Botones en la ficha.

**Inventario:** kit inicial automático (arma+armadura elegidas, 2 pociones,
antorchas, raciones). Usar consumibles (la poción cura 2d4+2 server-side y en
combate consume el turno), equipar armas del inventario, dar objetos a
compañeros. El LLM puede otorgar loot y monedas de oro vía contrato (con topes).

**Subida de nivel:** botón en la ficha cuando la XP alcanza; elegís tirar el
dado de golpe o valor fijo; recalcula PG, dados y slots preservando gastados.

**Timeout de turno:** 120s sin actuar en combate → Esquivar automático y pasa
el turno (contador visible en la barra de combate). Un AFK no congela la mesa.

**Retomar campaña:** tu "llave" de jugador (token) sirve para volver a entrar
desde cualquier dispositivo (tarjeta en el inicio, botón 🔑 en la cabecera
para copiarla, endpoint GET /api/campaigns/me).

**Muerte con reemplazo:** si tu personaje muere podés forjar uno nuevo y
seguir en la misma campaña; el caído queda en el historial.

**Narrador visible y diagnosticable:** la cabecera muestra qué modelo narra
("DM dummy" en rojo si falta la key). Click en esa pastilla = test unitario
real del narrador (también en GET /api/health/narrator): hace una llamada
mínima a OpenRouter y devuelve OK o la causa exacta del fallo.

**Errores del narrador visibles:** si OpenRouter falla, el chat muestra la
causa real ("límite diario del free tier alcanzado", "modelo saturado",
"key inválida") en vez de caer silenciosamente al dummy. Reintentos con
backoff en 429 por minuto / 5xx; el límite DIARIO no se reintenta (los
fallos también consumen cuota).

**Fallback de modelos:** OPENROUTER_MODEL acepta una lista separada por
comas; el primero es el principal y el resto fallbacks automáticos (routing
de OpenRouter). Ej:
`meta-llama/llama-3.3-70b-instruct:free,deepseek/deepseek-chat:free`

**Límites del free tier de OpenRouter (importante):** 20 req/min y 50
req/día sin créditos — y los intentos fallidos cuentan. Comprar USD 10 una
única vez (no expiran) sube el límite a 1000/día para siempre. Cada acción
de juego ≈ 1 request, más 1 de resumen cada 40 mensajes.

**Contenido:** 12 monstruos (goblin→ogro), armas naturales, consumibles.

## Rasgos de clase, acciones de combate y party (SRD 5.1)

**Rasgos de clase mecánicos (niveles 1-4):**
- Bárbaro: Furia (+2 daño melé todo el combate, 2-3 usos/día) y Defensa sin
  armadura (CA 10+DES+CON).
- Guerrero: estilo de combate a elección (Defensa +1 CA / Duelo +2 daño /
  Arquería +2 ataque), Nuevo Aliento (1d10+nivel, 1/corto) y Oleada de
  Acción nv2 (ataque extra en el turno, 1/corto).
- Pícaro: Ataque Furtivo (+1d6 nv1, +2d6 nv3; con arma de finura/distancia
  y un aliado consciente en combate o ventaja; dobla dados en crítico).
- Monje: Artes Marciales (1d4 DES) y Defensa sin armadura (10+DES+SAB, sin
  escudo).
- Clérigo: Canalizar Divinidad nv2 (Preservar Vida: cura 5×nivel, 1/corto).
- Paladín: Imposición de Manos (reserva de 5×nivel PG por día).
- Bardo: Inspiración Bárdica (un aliado suma 1d6 a su próxima tirada de
  ataque o habilidad; usos = mod CAR por día).
- Mago: Recuperación Arcana (recupera slots en el descanso corto, automática).
- Brujo: truco Explosión Sobrenatural (eldritch blast, 1d10).
Los recursos se muestran en la ficha con botón de uso y se resetean con el
descanso que corresponde.

**Acciones de combate:** además de atacar y lanzar: Esquivar (desventaja a
los ataques en tu contra), Ayudar (ventaja al próximo ataque de un aliado),
Empujar (Atletismo vs 10+DES para derribar) y Huir (Acrobacias CD 12; el
fallo cuesta un golpe de oportunidad).

**Panel de party:** en la pestaña Mundo, todos los personajes con nombre,
raza, clase/nivel, alineamiento, PG y condiciones.

**Mejora de atributos (ASI):** en los niveles 4 y 8 el level-up exige
repartir +2 puntos (+2 a uno o +1/+1), validado server-side con tope 20.

**Feats:** el SRD solo libera uno (Grappler, incluido). Los de PHB/Tasha's/
Xanathar's son contenido con copyright y no vienen precargados: la
estructura `FEATS` en `engine/content.py` está lista para que cargues los
de tu mesa como data (formato documentado ahí mismo).

## Razas, point buy y administración

**Razas y subrazas (9):** humano, elfo (alto/bosques/drow), enano
(colinas/montañas), mediano (piesligeros/fornido), gnomo (bosque/rocas),
semielfo (+1 a dos atributos a elección), semiorco, dracónido, tiflin.
Los bonos raciales y la velocidad los aplica EL SERVIDOR sobre los valores
base: el cliente solo muestra el preview. El enano de las colinas suma su
+1 PG por nivel. Las razas con subrazas la exigen.

**Métodos de atributos:** point buy 27 (validado server-side con la tabla
estándar: 8=0 … 15=9, máx 15 base) o libre (3–18, a criterio de la mesa).
Contador de puntos en vivo en la UI.

**Salir al menú:** botón en la cabecera (recuerda guardar la llave 🔑).

**Administración de campañas** (`scripts/admin.py`, usa el mismo
DATABASE_URL que la app):
```bash
python scripts/admin.py list
python scripts/admin.py delete 3 7
python scripts/admin.py wipe --yes
# contra Neon desde tu máquina:
DATABASE_URL="postgresql://..." python scripts/admin.py wipe --yes
```

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
