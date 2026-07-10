"""Demo: combate completo PJ vs goblins usando solo el motor.

Ejecutar: python demo.py

Esto simula exactamente lo que hará la capa API: hidratar criaturas,
resolver acciones con el motor, y quedarse con los dicts de resolución
(que en el sistema real van a la DB, al WebSocket y al prompt del LLM).
"""
import json

from engine import Combat, Criatura, SpellState, curar, gastar_slot, resolver_ataque
from engine.content import ARMAS, MONSTRUOS, slots_iniciales
from engine.dice import roll


def crear_pj():
    return Criatura(
        id="thorin", nombre="Thorin", nivel=1,
        atributos={"FUE": 16, "DES": 12, "CON": 14, "INT": 8, "SAB": 10, "CAR": 13},
        pg_actual=12, pg_max=12, dado_golpe="d10", dados_golpe_disp=1,
        competencias={"habilidades": ["atletismo", "intimidacion"],
                      "salvaciones": ["FUE", "CON"],
                      "armas": ["marcial", "simple"],
                      "armaduras": ["ligera", "media", "escudo"]},
    )


def crear_goblin(n):
    m = MONSTRUOS["goblin"]
    return Criatura(
        id=f"goblin_{n}", nombre=f"Goblin {n}", nivel=1,
        atributos=m["atributos"], pg_actual=m["pg"], pg_max=m["pg"],
        ca_fija=m["ca_fija"],
    )


def main():
    pj = crear_pj()
    goblins = [crear_goblin(1), crear_goblin(2)]
    todos = {c.id: c for c in [pj] + goblins}

    print("=== INICIA COMBATE ===")
    combate = Combat.iniciar([pj], goblins)
    for t in combate.tiradas_iniciativa:
        print(f"  Iniciativa {t['criatura_id']}: d20={t['natural']} "
              f"+{t['bono']} = {t['total']}")
    print(f"  Orden: {[e['id'] for e in combate.orden]}\n")

    espada = ARMAS["espada_larga"]
    cimitarra = ARMAS["cimitarra"]

    ronda_max = 20
    while combate.activo and combate.ronda <= ronda_max:
        actor_id = combate.turno_actual["id"]
        actor = todos[actor_id]

        if actor_id == "thorin":
            # el PJ ataca al primer goblin vivo
            vivos = [g for g in goblins if g.pg_actual > 0]
            if not vivos:
                break
            objetivo = vivos[0]
            r = resolver_ataque(actor, objetivo, espada)
        else:
            objetivo = pj
            r = resolver_ataque(actor, objetivo, cimitarra)

        estado = "IMPACTA" if r["impacta"] else "falla"
        crit = " ¡CRÍTICO!" if r["critico"] else (" (pifia)" if r["pifia"] else "")
        danio = f" → {r['danio']['total_final']} de daño, {objetivo.nombre} " \
                f"queda a {objetivo.pg_actual} PG" if r["danio"] else ""
        print(f"R{combate.ronda} | {actor.nombre} ataca a {objetivo.nombre}: "
              f"d20={r['natural']}+{r['bono_ataque']}={r['total']} vs CA "
              f"{r['ca_objetivo']} → {estado}{crit}{danio}")

        if objetivo.pg_actual == 0:
            print(f"      *** {objetivo.nombre} cae ***")
            combate.remover(objetivo.id)
            if not combate.npcs_restantes():
                print("\n=== VICTORIA: no quedan enemigos ===")
                combate.activo = False
                break
            if not combate.pjs_restantes():
                print("\n=== DERROTA: el grupo cayó ===")
                combate.activo = False
                break

        if combate.activo:
            combate.avanzar_turno()

    print(f"\nEstado final de Thorin: {pj.pg_actual}/{pj.pg_max} PG")
    print("\nEjemplo de dict de resolución (lo que ve el LLM y la UI):")
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
