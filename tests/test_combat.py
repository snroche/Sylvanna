from engine.combat import CampaignState, Combat, validar_transicion
from engine.entities import Criatura


def cr(id, des=10, tipo="pj") -> Criatura:
    return Criatura(id=id, nombre=id, nivel=1,
                    atributos={"FUE": 10, "DES": des, "CON": 10,
                               "INT": 10, "SAB": 10, "CAR": 10},
                    pg_actual=10, pg_max=10)


def test_transiciones():
    assert validar_transicion(CampaignState.EXPLORACION, CampaignState.COMBATE)
    assert validar_transicion(CampaignState.COMBATE, CampaignState.EXPLORACION)
    assert not validar_transicion(CampaignState.COMBATE, CampaignState.DESCANSO)
    assert not validar_transicion(CampaignState.PAUSADA, CampaignState.COMBATE)


def test_iniciar_combate_ordena_por_iniciativa():
    c = Combat.iniciar([cr("a"), cr("b")], [cr("g1", tipo="npc")])
    inits = [e["init"] for e in c.orden]
    assert inits == sorted(inits, reverse=True)
    assert len(c.tiradas_iniciativa) == 3
    assert c.ronda == 1 and c.turno_idx == 0


def test_empate_pj_antes_que_npc():
    # forzamos el orden manualmente para testear la clave de sort
    entradas = [
        {"tipo": "npc", "id": "g", "init": 15, "des": 2},
        {"tipo": "pj", "id": "a", "init": 15, "des": 0},
    ]
    entradas.sort(key=lambda e: (-e["init"], 0 if e["tipo"] == "pj" else 1, -e["des"]))
    assert entradas[0]["id"] == "a"


def test_avanzar_turno_y_ronda():
    c = Combat(orden=[{"tipo": "pj", "id": "a", "init": 15, "des": 0},
                      {"tipo": "npc", "id": "g", "init": 10, "des": 0}])
    assert c.turno_actual["id"] == "a"
    r = c.avanzar_turno()
    assert r["turno"]["id"] == "g" and not r["nueva_ronda"]
    r = c.avanzar_turno()
    assert r["turno"]["id"] == "a" and r["nueva_ronda"] and c.ronda == 2


def test_es_turno_de():
    c = Combat(orden=[{"tipo": "pj", "id": "a", "init": 15, "des": 0},
                      {"tipo": "pj", "id": "b", "init": 10, "des": 0}])
    assert c.es_turno_de("a")
    assert not c.es_turno_de("b")


def test_remover_ajusta_indice():
    c = Combat(orden=[{"tipo": "pj", "id": "a", "init": 15, "des": 0},
                      {"tipo": "npc", "id": "g", "init": 12, "des": 0},
                      {"tipo": "pj", "id": "b", "init": 10, "des": 0}])
    c.avanzar_turno()          # turno de g (idx 1)
    c.remover("a")             # muere alguien antes del turno actual
    assert c.turno_actual["id"] == "g"
    c.remover("g")
    assert c.turno_actual["id"] == "b"


def test_remover_ultimo_desactiva():
    c = Combat(orden=[{"tipo": "pj", "id": "a", "init": 15, "des": 0}])
    c.remover("a")
    assert not c.activo


def test_npcs_pjs_restantes():
    c = Combat(orden=[{"tipo": "pj", "id": "a", "init": 15, "des": 0},
                      {"tipo": "npc", "id": "g", "init": 10, "des": 0}])
    assert c.npcs_restantes() == ["g"]
    assert c.pjs_restantes() == ["a"]


def test_serializacion_roundtrip():
    c = Combat.iniciar([cr("a")], [cr("g")])
    c.avanzar_turno()
    d = c.to_dict()
    c2 = Combat.from_dict(d)
    assert c2.ronda == c.ronda
    assert c2.turno_idx == c.turno_idx
    assert c2.orden == c.orden
