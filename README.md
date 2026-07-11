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

## Panel del DM humano, condiciones completas y economía

**Panel de admin (⚙ en la cabecera):** protegido por env `ADMIN_TOKEN`
(vacío = deshabilitado; el token se pide una vez y queda en el navegador).
Todo lo que necesitás para corregir rarezas del narrador en segundos:
- **Hablar como el DM**: tu texto entra como narración; la IA lo ve en su
  contexto y construye sobre él. Ideal para redirigir la historia.
- Editar PG/oro/XP de cada personaje, limpiar condiciones, dar/quitar items.
- NPCs: actitud, en escena, eliminar duplicados.
- Cambiar estado de misiones, borrar consecuencias pendientes.
- **Editar la crónica** (el resumen que la IA usa como memoria).
- Forzar el fin de un combate trabado.
Whitelist estricta de campos server-side: el token no permite romper fichas.

**Condiciones 5e completas y mecánicas:** restringido (desventaja atacando,
ventaja en tu contra), aturdido y paralizado (perdés el turno — PJ y NPC —,
ventaja en tu contra, auto-fallo de salvaciones FUE/DES, y golpear a un
paralizado es crítico), agarrado (bloquea Huir), atacar derribado da
desventaja, y levantarse es automático al inicio de tu turno. Las
condiciones pueden tener **duración en rondas** que expira sola. El DM (IA)
puede aplicarlas y quitarlas con `aplicar_condicion` / `quitar_condicion`
(whitelist de tipos, máximo 3 rondas).

**Economía funcional:** la IA ya narraba mercaderes pero no podía cobrar.
Nuevo efecto `quitar_monedas`: al comprar, el DM emite el item (loot) y el
precio en la misma respuesta; el sistema rechaza el gasto si no te alcanza
el oro (y el DM debe renegociar). Precios de referencia del SRD en el
prompt. Vender = quitar_item + otorgar_monedas a mitad de precio.

## Ascendencias dracónicas, resistencias y razas custom

**Dracónido completo (SRD):** las 10 ascendencias como subrazas (negro,
azul, latón, bronce, cobre, oro, verde, rojo, plata, blanco), cada una con
su elemento y salvación. El **Aliento de Dragón es mecánico**: botón 🐉 en
la ficha, 2d6 de daño (3d6 a nivel 5+), CD 8+BC+CON, salvación del enemigo
para mitad, 1 uso por descanso corto, y puede cerrar el combate.

**Resistencias elementales reales:** el motor ahora reduce a la mitad el
daño de tipos resistidos (dracónido → su elemento, tiefling → fuego,
enano → veneno; data-driven). Aplica en ataques, stat blocks y el aliento;
la resolución marca `"resistido": true`.

**Razas y subrazas custom (`data/razas_custom.json`):** para contenido de
tus libros (bloodlines de tiefling de Mordenkainen's, etc.) que no puedo
precargar por copyright. El formato está documentado en
`engine/content.py`: las razas nuevas se agregan enteras, y las existentes
se mergean a nivel subraza — agregás `"tiefling": {"subrazas": {"zariel":
{...}}}` y aparece en la UI con sus bonos y rasgo, validación server-side
incluida. Ojo: si le agregás subrazas a una raza que no tenía, la subraza
pasa a ser obligatoria (agregá una `"estandar"` con `"bonos": {}` para
conservar la base). Soporta `bonos`, `rasgo`, `velocidad_m`,
`resistencias` y `bonos_a_eleccion`.

## Fixes de la sesión de testeo en profundidad

- **Encoding (Windows):** el importador ahora escribe UTF-8 explícito, y el
  loader tolera archivos ya escritos en cp1252 — tu `conjuros_srd.json`
  actual carga sin regenerarlo (aunque re-correr el script lo deja limpio).
- **JSON escapado en la narración:** causa raíz: el modelo se quedaba sin
  tokens a mitad del bloque JSON → fence sin cerrar → el parser no lo
  reconocía y se filtraba a la mesa. Triple fix: parser que amputa bloques
  colgados, presupuesto de tokens 700→1100, y prompt que exige JSON breve
  al final ("si falta espacio se acorta la narración, jamás el JSON").
- **El DM ahora pide tiradas y saca items:** dos efectos nuevos en el
  contrato: `pedir_tirada` (acciones inciertas sin tirada → el DM la pide
  en vez de resolver) y `quitar_item` (objetos dejados/entregados/rotos
  salen del inventario, con match tolerante de nombre).
- **Tiradas visibles para todos:** cada skill-check emite un mensaje de
  sistema con el desglose (d20+bono=total → éxito/fallo).
- **"X está escribiendo…":** heartbeat liviano (3s de throttle) visible
  para el resto de la mesa.
- **↺ Regenerar / ⌫ Deshacer:** botones junto al composer. Solo sobre pares
  acción→narración simples (con tiradas o combate en el medio se bloquea:
  los dados no se re-tiran). Los demás clientes detectan el borrado por
  retroceso de ids y re-renderizan solos.
- **Doble envío:** guard de in-flight en el cliente.
- **UI:** chat hasta 90ch de ancho, panel lateral con secciones colapsables
  (La party, Misiones, Personajes, Presagios, Crónica) que recuerdan su
  estado — la ficha ya no queda enterrada.
- **Crónica:** el resumen NO se regenera entero: cada `RESUMIR_CADA`
  mensajes (env, default 40) integra el lote nuevo al resumen existente.
  Una llamada extra al modelo cada ~40 acciones.

## Experiencia completa hasta nivel 5

**Nivel 5 mecánico:**
- **Ataque Extra** (guerrero/bárbaro/paladín/ranger/monje nv5+): el primer
  ataque del turno no lo consume; el segundo sí. Compatible con Oleada de
  Acción (que sigue dando un ataque adicional aparte).
- **Trucos escalados**: a nivel 5 los trucos de daño duplican sus dados
  (rayo de escarcha 2d8, explosión sobrenatural 2d10, etc.), automático.
- **Inspiración Bárdica d8** a partir de nivel 5 del bardo.
- Ataque Furtivo ya escalaba solo ((nivel+1)/2 d6 → 3d6 a nv5), igual que
  el bonus de competencia (+3 a nv5) y los slots (nivel 3 a nv5).

**Gestión de conjuros** (`POST /spells/manage`, botón 📜 en la ficha):
panel con todo el catálogo (filtro + contador), validación server-side de
existencia, nivel máximo lanzable según slots de clase, y cantidad:
conocidos por tabla SRD (bardo/hechicero/brujo/ranger) o preparados =
mod mágico + nivel (mago/clérigo/druida; paladín mod+nivel/2). Los
preparados se pueden reorganizar en cualquier momento fuera de combate,
como manda 5e.

**Subclases**: al llegar al nivel de subclase de tu clase (1 para clérigo/
hechicero/brujo, 2 para mago/druida, 3 para el resto) el level-up la exige.
Opciones del SRD precargadas (Campeón, Dominio de la Vida, Ladrón, etc.) o
texto libre. En v1 es una elección narrativa: figura en la ficha y en el
contexto del DM, que la respeta; la mecánica fina de cada subclase queda
para la próxima iteración.

**Razas/subrazas desde el servidor**: `/api/content` ahora expone el
catálogo completo (bonos, rasgo, velocidad por subraza) y la UI lo muestra
al elegir — se acabaron los selects sin información. El frontend ya no
tiene espejo propio de razas: una sola fuente de verdad.

## Ambientación, party chat, nomenclatura e importador SRD

**Ambientación de campaña:** al crearla podés describir el setting
("transcurre en Baldur's Gate…"). Queda fija en el contexto de TODAS las
llamadas al narrador, y al crearse el primer personaje el DM genera la
escena de apertura basada en ella.

**Charla entre jugadores:** botón "💬 Party" — el mensaje llega a la mesa
(con estilo propio) pero el DM no interviene ni responde por nadie. Además
el prompt del narrador ahora prohíbe explícitamente hablar o decidir por
los personajes de los jugadores.

**Nomenclatura:** tiefling (no "tiflin"), camisa_de_mallas, ring_mail,
cota_de_mallas, armadura_de_placas. Los nombres viejos siguen funcionando
como aliases (personajes existentes no se rompen). El narrador tiene
instrucción de usar los nombres de juego tal cual, sin traducciones
rebuscadas.

**Importador del SRD (Open5e):**
```bash
python scripts/importar_srd.py                 # monstruos hasta CR 10 + conjuros hasta nv 5
python scripts/importar_srd.py --cr-max 5 --solo monstruos
```
Genera `data/monstruos_srd.json` y `data/conjuros_srd.json`, que
`engine/content.py` mergea automáticamente al arrancar (sin pisar lo
curado). Los monstruos vienen con mecánica completa: PG, CA, atributos y
**ataques de stat block** (bono y dados reales) que el motor usa en los
turnos de NPC. Los conjuros traen nivel/concentración seguros y resolución
mecánica deducida por heurística del texto (ataque/salvación/daño); los no
deducibles quedan como narrativos con su descripción. La UI carga el
catálogo desde `GET /api/content` (creación muestra trucos y nivel 1, con
filtro de texto). Corré el script en tu máquina (necesita internet) y
comiteá los JSON al repo para que Render los sirva.

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
