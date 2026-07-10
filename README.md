# DnD Engine — Motor de reglas 5e (Paso 1 del proyecto)

Motor de reglas D&D 5e **puro**: sin base de datos, sin LLM, sin async.
Es la fundación del servicio multijugador con narrador IA.

## Estructura

```
engine/
├── dice.py       # RNG del servidor (SystemRandom), roll("2d6+3"), d20 con ventaja
├── entities.py   # Dataclasses puras: Criatura, Arma, Armadura, SpellState
├── rules.py      # Núcleo 5e: mod, BC, CA, ataques, daño, curación, muerte,
│                 #   concentración, slots, habilidades, salvaciones, descansos
├── combat.py     # Máquina de estados de campaña + turnos/iniciativa (Combat)
└── content.py    # Contenido SRD v1: 14 armas, 8 armaduras, 12 clases,
                  #   tablas de slots, 6 monstruos, ~25 conjuros, XP por CR
tests/            # 76 tests (pytest)
demo.py           # Combate simulado de punta a punta
```

## Uso

```bash
pip install pytest
python -m pytest tests/ -q     # correr la suite
python demo.py                 # ver un combate resuelto por el motor
```

## Principio de diseño

Cada función del motor devuelve un **dict de resolución completo**
(tirada natural, bonos, totales, CD/CA, resultado, efectos derivados).
Ese dict tiene tres destinos en el sistema final:

1. Tabla `Roll` de la DB (auditoría)
2. Broadcast por WebSocket (UI de los jugadores)
3. Prompt del LLM (el narrador recibe resultados YA resueltos, nunca decide números)

El estado de las criaturas se **muta** dentro del motor (PG, slots, condiciones);
la capa API es responsable de hidratar `Criatura` desde la DB antes de llamar
al motor y persistir los cambios después.

## Qué NO hace el motor (a propósito)

- No persiste nada → eso es de la capa `models/` (SQLAlchemy + Neon)
- No llama a OpenRouter → eso es de `narrator/`
- No maneja WebSockets ni HTTP → eso es de `api/` (FastAPI)
- No resuelve efectos narrativos de conjuros (hechizar, invisibilidad):
  el motor valida y gasta el slot; el efecto lo aplica el backend
  como condición + el LLM lo narra

## Próximos pasos (según el plan acordado)

1. ✅ Motor de reglas + tests
2. ⬜ `models/` + API REST (FastAPI, un jugador, DM dummy)
3. ⬜ `narrator/` (OpenRouter, pipeline de contexto, resumen rodante)
4. ⬜ WebSockets + multijugador (batch de exploración, turnos de combate)
5. ⬜ Frontend de fichas (servido estático desde la misma app en Render)
