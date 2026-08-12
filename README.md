# Sylvanna — a multiplayer D&D 5e server with an AI Dungeon Master

> **The LLM only narrates.** Every die roll, resource, turn order and rule
> validation lives on the server. The model writes prose around results it
> cannot change — and neither can the client.

![screenshot](docs/screenshot.png)

### Try it in 30 seconds

**No configuration, no API key, no database setup.** Clone it, install, run — the
full rules engine is playable offline against a built-in dummy narrator. Add an
LLM key later if you want prose.

```bash
pip install -r requirements.txt && uvicorn main:app --reload
```

1. Open <http://localhost:8000> and click **Fundar campaña** — pick a campaign
   name and your player name. You get an invite code (share it to play with
   others) and a player key (keep it; it's how you rejoin).
2. **Create a character**: choose race, class and attributes. The server computes
   HP, AC, spell slots and your starting kit — the client only previews.
3. **Roll**: type an action in the composer, or hit **Tirada de habilidad**,
   pick a skill and a DC. The result lands instantly as an ink stamp
   (`d20 16+4 = 20 vs CD 12 → ÉXITO`); the DM's prose follows a moment later.

> Interface and identifiers are in Spanish — the table this was built for plays
> in Spanish. Architecture and code comments are documented in English.

Sylvanna is a full multiplayer tabletop RPG service: a **complete, dependency-free
D&D 5e rules engine**, an async **FastAPI** backend, and a zero-build **vanilla JS**
frontend ("La Mesa") served from the same process. Players share an invite code,
create characters, explore and fight; an LLM plays the Dungeon Master.

<table>
<tr><td><b>Rules engine</b></td><td>5e SRD 5.1, levels 1–20, 0 third-party deps</td></tr>
<tr><td><b>Backend</b></td><td>FastAPI · SQLAlchemy 2.0 async · Pydantic Settings</td></tr>
<tr><td><b>Storage</b></td><td>SQLite (dev) / Postgres–Neon (prod), same code path</td></tr>
<tr><td><b>Narrator</b></td><td>OpenRouter, any model, with automatic fallbacks</td></tr>
<tr><td><b>Frontend</b></td><td>Vanilla JS/CSS, no build step, mobile-friendly</td></tr>
<tr><td><b>Content</b></td><td>336 monsters · 319 spells · 237 magic items · 13 backgrounds</td></tr>
<tr><td><b>Tests</b></td><td><b>225 tests</b>, ~12s, no network required</td></tr>
</table>

---

## Why this design

Letting an LLM run a tabletop game the naive way — "you are a DM, track the HP" —
fails in every direction: the model forgets damage, invents spell slots, lets a
player act out of turn, and rewards whoever argues hardest. Sylvanna makes that
structurally impossible.

**The authority split**

| The server owns | The LLM owns |
| --- | --- |
| Dice, attack/damage resolution, saving throws | Prose, scene description, NPC voice |
| HP, spell slots, class resources, conditions | Requesting a check (`pedir_tirada`) |
| Initiative and turn validation | Declaring *world* effects via a JSON contract |
| Inventory, gold, XP, level-ups | Nothing that touches a character sheet |

The narrator returns prose **plus** an optional JSON block of world effects
(create an NPC, open a quest, grant loot, start combat, apply a condition…).
Every field is whitelisted and clamped server-side — narrative XP is capped at
`50 × level`, conditions at 3 rounds, purchases are rejected if you can't afford
them. Anything outside the schema is silently dropped. A hallucinating model
degrades the story, never the game state.

**Every roll is auditable.** Each one is persisted in the `rolls` table with its
full resolution dict — the d20, the modifiers, the DC, the outcome.

**Latency is a first-class concern.** Actions return the mechanical resolution
immediately (~25 ms) and the LLM narration runs in a `BackgroundTask`. The UI
shows "the DM is narrating…" and adaptive polling (1.3 s in combat, 5 s at rest)
picks it up when ready. If OpenRouter fails, the mechanics have already been
applied and a system message explains exactly why — daily free-tier limit,
saturated model, invalid key — instead of silently degrading.

---

## Running it

The three steps above are the whole setup. With no environment variables the app
uses local SQLite and a deterministic dummy narrator — every rule, roll and
combat works offline. `/docs` serves the interactive API.

To enable the real DM, copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q        # 225 tests
```

The combat and dice suites roll real dice rather than mocking them, so a run
occasionally skips a case the RNG made untestable (the guards say `azar`). A
handful of scenarios can also end early — see the flaky-test note in the
roadmap.

---

## Architecture

```
engine/          Pure 5e engine — zero dependencies, no I/O, fully unit-tested
  dice.py          d20 with advantage/disadvantage, damage dice, crits
  rules.py         modifiers, proficiency, DCs, progression tables 1–20
  combat.py        initiative, turn order, attack/save resolution
  entities.py      combatant value objects
  content.py       SRD content: races, classes, spells, monsters, items, feats
app/
  config.py        pydantic-settings; sane defaults for every variable
  db.py            async SQLAlchemy; SQLite dev / Neon prod + idempotent migrations
  models.py        Campaign, Player, Character, NPC, Quest, PendingConsequence,
                   Message, Roll
  hydration.py     DB rows ↔ engine entities (the only bridge between layers)
  context.py       structured prompt assembly under a ~6–8k token budget
  narrator.py      OpenRouter client: retries, backoff, model fallback, dummy mode
  effects.py       validates and applies the LLM's JSON world-effect contract
  routers/         campaigns · characters · actions · admin
main.py          FastAPI app + static frontend mounted at /
static/          "La Mesa" — vanilla JS client, no build step
data/            SRD content imported from Open5e (JSON)
scripts/         SRD importer, campaign admin CLI
```

**The engine has no idea a database exists.** It takes value objects and returns
resolution dicts. `hydration.py` is the single seam between persistence and rules,
which is why the engine can be tested exhaustively without fixtures or mocks.

**Context assembly.** Each narrator call gets a rolling summary, the party, NPCs
in scene with full stat blocks, active quests, pending consequences and the last
12 messages. Hard data (quests, NPCs, consequences) lives in tables and never
depends on the summary — the chronicle can drift without corrupting the game.
The summary is incremental: every `RESUMIR_CADA` messages a (cheaper) model folds
the new batch into the existing text, one extra call per ~40 actions.

---

## API tour

All game actions are `POST /api/campaigns/{id}/…` and authenticate with an
`X-Player-Token` header.

```http
POST /api/campaigns              { nombre, nombre_jugador }   → invite_code + player_token
POST /api/campaigns/join         { invite_code, nombre_jugador }
POST /api/characters             → server computes HP, AC, slots, starting kit
GET  /api/characters/{id}/sheet  → full live sheet
POST /api/campaigns/{id}/say     { texto }                    → narrative action
POST /api/campaigns/{id}/skill-check   { habilidad, cd }      → server-resolved roll
POST /api/campaigns/{id}/combat/start  { monstruos: [...] }   → initiative
POST /api/campaigns/{id}/combat/attack { objetivo_npc_id }    → your turn only
GET  /api/campaigns/{id}/messages?since=0                     → adaptive polling
GET  /api/campaigns/{id}/state                                → quests, NPCs, omens
```

Around 50 endpoints in total, including rests, inventory, spell management,
rituals, level-up, wild shape, metamagic, attunement and mounts.
`GET /api/health/narrator` runs a real minimal LLM call and reports the exact
failure cause — handy for diagnosing a deploy without shell access.

---

## Rules coverage

Everything below is **mechanical** — resolved by the engine, not narrated.

<details>
<summary><b>Character creation & progression</b></summary>

- **9 races, 30+ subraces** including all 10 draconic ancestries and 9 infernal
  tiefling lineages, with real elemental resistances (halved damage).
- **Point buy 27** (validated against the standard table) or free assignment.
- **13 backgrounds** granting proficiencies, gear, gold and a roleplay trait.
- **Levels 1–20**: full slot tables (full/half/pact casters), XP thresholds,
  spells known, resource uses. Extra Attack scales to 3 and 4.
- **ASI at 4/8/12/16/19**, or a **feat** instead — a dozen feats with real
  mechanical effects, not just narrative flavor.
- **Multiclassing** with ability prerequisites and combined-slot tables.
- **Subclasses** required at the correct level per class.
- Custom races/subraces can be added via `data/razas_custom.json` without touching code.
</details>

<details>
<summary><b>Class features</b></summary>

Rage · Unarmored Defense · fighting styles (all six) · Second Wind · Action Surge ·
Sneak Attack · Martial Arts · Ki & Stunning Strike · Channel Divinity (Preserve
Life, Turn Undead) · Lay on Hands · Divine Smite · Bardic Inspiration (scaling to
d8) · Arcane Recovery · Wild Shape with real beast stat blocks and CR caps ·
Sorcery Points, Font of Magic and mechanical Metamagic (Empowered, Heightened) ·
Eldritch Invocations (Agonizing Blast) · Expertise · Reckless Attack.
</details>

<details>
<summary><b>Combat</b></summary>

Initiative and strict turn validation · Attack, Dodge, Help, Shove, Flee ·
two-weapon fighting · opportunity attacks · critical hits · **full 5e conditions**
with round durations (restrained, stunned, paralyzed — including auto-crit —
grappled, prone, frightened) · damage resistances · concentration · death saves
and Medicine stabilization · **120s turn timeout** that auto-Dodges so one AFK
player can't freeze the table · automatic XP by CR split among survivors.
</details>

<details>
<summary><b>Magic & items</b></summary>

Slot-accurate casting (the slot is spent *before* resolution, so a failure still
costs it) · attack/save/healing/auto resolution derived per spell · **area and
multi-target** spells rolled once and split · **upcasting** for damage, healing
and magic missile · **ritual casting** without slots · costly material components
consumed from inventory · cantrip scaling at level 5 · prepared vs known counts
enforced per class · attunement (max 3) · consumables, equipping, trading, gold
economy with server-rejected purchases · mounts with their own HP/AC/speed.
</details>

<details>
<summary><b>Human DM panel</b></summary>

Optional admin panel gated by `ADMIN_TOKEN` (empty = disabled). Speak *as* the
DM so the AI builds on your text, edit HP/gold/XP, clear conditions, manage NPCs
and quests, rewrite the chronicle the AI uses as memory, force-end a stuck
combat. A strict server-side field whitelist means the token can steer the story
but cannot corrupt a character sheet.
</details>

---

## Frontend — "La Mesa"

Vanilla JS, no bundler, no framework, no build step: open the site root.

- **Sessions survive reloads** (localStorage) and devices — your player token is
  a key you can copy from the header and use to rejoin from anywhere.
- Mechanical results render as **ink stamps** (`d20 14+5=19 vs AC 15 → HIT`),
  visually separated from the DM's prose.
- The composer switches to combat mode automatically: initiative bar, current
  turn highlighted, targets shown with *narrative* health (unhurt / wounded /
  badly wounded — never exact HP).
- Live sheet, quests, known NPCs with attitudes, pending consequences ("omens")
  and the rolling chronicle, in collapsible panels that remember their state.
- Party chat that the DM sees but never answers for you.
- Regenerate ↺ / undo ⌫ on the last exchange — blocked when dice or combat are
  involved, because rolls don't get re-rolled.
- Mobile tabs (Game / Sheet / World) and tolerance for cold starts.

---

## Deployment

Single web service, no CORS, frontend served by the API.

| Setting | Value |
| --- | --- |
| Build | `pip install -r requirements.txt` |
| Start | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Env | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `DATABASE_URL`, `ADMIN_TOKEN` |

Tables are created on first boot and schema changes ship as an idempotent
`MIGRACIONES` list, so existing campaigns keep working across deploys. Paste the
Neon connection string as-is — the config layer normalizes the driver to asyncpg
and strips `sslmode`.

**On OpenRouter free tier:** 20 req/min and 50 req/day, and failed attempts
count. Roughly one request per game action, plus one summary per ~60 messages.

### Content import

SRD monsters and spells come from [Open5e](https://open5e.com):

```bash
python scripts/importar_srd.py                        # monsters ≤ CR 10, spells ≤ lvl 5
python scripts/importar_srd.py --cr-max 5 --solo monstruos
```

Monsters arrive with full mechanics (HP, AC, abilities and real stat-block
attacks the engine uses on NPC turns). Spell resolution is inferred heuristically
from the text; whatever can't be inferred stays narrative. Generated JSON is
committed so production needs no network at boot.

### Campaign admin

```bash
python scripts/admin.py list
python scripts/admin.py delete 3 7
DATABASE_URL="postgresql://..." python scripts/admin.py wipe --yes
```

---

## Engineering notes

A few problems worth writing down:

- **Truncated JSON leaking into the chat.** Root cause wasn't the parser — the
  model ran out of tokens mid-block, leaving an unclosed fence. Fixed in three
  places: a parser that amputates dangling blocks, a raised token budget, and a
  prompt rule that the *narration* gets shortened when space runs out, never the
  JSON contract.
- **Windows encoding.** The importer writes explicit UTF-8 and the loader
  tolerates files previously written as cp1252, so existing data keeps loading.
- **One source of truth for content.** The frontend used to mirror the race list;
  now `GET /api/content` serves the full catalog and the UI just renders it.
- **Backwards compatibility.** Old characters survive every content rename via
  alias keys, and the single added column ships through the idempotent migration list.

## Roadmap

- [x] Rules engine + test suite
- [x] Models + deployable REST API
- [x] Narrator pipeline: rolling summary, JSON contract, spells, XP by CR
- [x] Full frontend served from `/`
- [x] Levels 1–20, feats, backgrounds, multiclassing, magic items
- [ ] Per-subclass mechanics (currently narrative: the DM respects them, the engine doesn't enforce them)
- [ ] Seed the RNG in combat tests. `test_combate_ronda.py::test_descripcion_de_ataque_queda_en_el_log`
      fails on roughly 5% of runs: three goblins can drop the level-1 fighter
      before their turn, combat ends, and the test indexes a `None` state. The
      neighbouring tests guard this with `pytest.skip("azar")`; this one doesn't.
- [ ] WebSockets (adaptive polling has been sufficient for small tables)

---

## License & attribution

**Code** — MIT. See [LICENSE](LICENSE). This covers everything in `engine/`,
`app/`, `static/`, `scripts/`, `tests/` and `main.py`.

**SRD content** — This work includes material taken from the System Reference
Document 5.1 ("SRD 5.1") by Wizards of the Coast LLC and available at
<https://dnd.wizards.com/resources/systems-reference-document>. The SRD 5.1 is
licensed under the Creative Commons Attribution 4.0 International License,
available at <https://creativecommons.org/licenses/by/4.0/legalcode>.

**Imported data** — Monsters, spells and magic items under `data/` are imported
from the [Open5e](https://open5e.com) API, filtered to the `wotc-srd` document
slug, and carry the SRD 5.1 licence above. Open5e is an open database of 5e
content; thanks to its maintainers.

Sylvanna is an unofficial fan project, not affiliated with, endorsed, sponsored
or approved by Wizards of the Coast.

A small number of options outside the SRD (12 backgrounds, 12 feats and 9
tiefling lineages) ship as **mechanical data only** — ability adjustments,
proficiency lists and level tables, with original descriptions rather than
rulebook text. They are marked with `TODO(no-SRD)` comments in
`engine/content.py`. For anything further, `data/razas_custom.json` is a
git-ignored extension point: add content from books you own locally rather than
committing it.

---

Built as a study in keeping an LLM inside a hard boundary: give it the whole
story and none of the state.
