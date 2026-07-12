"""Motor de reglas D&D 5e. Funciones puras: reciben entidades, mutan estado,
devuelven dicts de resolución completos para auditoría/narración.

El LLM NUNCA ejecuta nada de esto: solo recibe los resultados.
"""
from __future__ import annotations

from .dice import d20, roll
from .entities import Arma, Criatura

# ---------------------------------------------------------------- básicos

HABILIDADES = {
    "atletismo": "FUE",
    "acrobacias": "DES", "juego_de_manos": "DES", "sigilo": "DES",
    "arcanos": "INT", "historia": "INT", "investigacion": "INT",
    "naturaleza": "INT", "religion": "INT",
    "perspicacia": "SAB", "medicina": "SAB", "percepcion": "SAB",
    "supervivencia": "SAB", "trato_con_animales": "SAB",
    "engano": "CAR", "intimidacion": "CAR", "actuacion": "CAR", "persuasion": "CAR",
}

XP_POR_NIVEL = {
    1: 0, 2: 300, 3: 900, 4: 2_700, 5: 6_500,
    6: 14_000, 7: 23_000, 8: 34_000, 9: 48_000, 10: 64_000,
    11: 85_000, 12: 100_000, 13: 120_000, 14: 140_000, 15: 165_000,
    16: 195_000, 17: 225_000, 18: 265_000, 19: 305_000, 20: 355_000,
}

# Condiciones que imponen desventaja al atacar
_COND_DESV_ATAQUE = {"envenenado", "asustado", "cegado", "derribado_distancia"}


def mod(puntaje: int) -> int:
    """Modificador de atributo: (puntaje - 10) // 2, redondeo hacia abajo."""
    return (puntaje - 10) // 2


def bc(nivel: int) -> int:
    """Bonus de competencia por nivel de personaje."""
    return 2 + (max(1, nivel) - 1) // 4


def calcular_ca(c: Criatura) -> int:
    if c.ca_fija is not None:
        return c.ca_fija + (2 if c.escudo else 0)
    des = mod(c.atributos["DES"])
    if c.armadura is None:
        base = 10 + des
        # Defensa sin armadura (rasgo de clase)
        if c.ca_alternativa == "barbaro":
            base = 10 + des + mod(c.atributos["CON"])
        elif c.ca_alternativa == "monje" and not c.escudo:
            base = 10 + des + mod(c.atributos["SAB"])
        elif c.ca_alternativa == "draconico":
            base = 13 + des
    elif c.armadura.des_max == 0:      # pesada: DES no aplica
        base = c.armadura.ca_base
    elif c.armadura.des_max is None:   # ligera: DES completa
        base = c.armadura.ca_base + des
    else:                              # media: DES con tope (+2)
        base = c.armadura.ca_base + min(des, c.armadura.des_max)
    total = base + (2 if c.escudo else 0)
    # Estilo de combate Defensa: +1 CA usando armadura
    if c.estilo_combate == "defensa" and c.armadura is not None:
        total += 1
    return total


def _ventaja_neta(bonos: int, penal: int) -> int:
    """5e: si hay al menos una fuente de cada, se cancelan (queda 0)."""
    if bonos > 0 and penal > 0:
        return 0
    if bonos > 0:
        return 1
    if penal > 0:
        return -1
    return 0


# ---------------------------------------------------------------- checks

def tirada_habilidad(c: Criatura, habilidad: str, cd: int, ventaja: int = 0) -> dict:
    if habilidad not in HABILIDADES:
        raise ValueError(f"Habilidad desconocida: {habilidad}")
    atributo = HABILIDADES[habilidad]
    bono = mod(c.atributos[atributo])
    if habilidad in c.competencias.get("habilidades", []):
        bono += bc(c.nivel)
        # Expertise (pícaro/bardo): duplica el bonus de competencia
        if habilidad in c.competencias.get("expertise", []):
            bono += bc(c.nivel)

    penal = 1 if c.tiene_condicion("envenenado") or c.tiene_condicion("asustado") else 0
    # Inspiración Heroica: ventaja en la tirada, se consume
    bonos_v = 1 if ventaja > 0 else 0
    if c.tiene_condicion("inspiracion_heroica"):
        bonos_v += 1
        c.quitar_condicion("inspiracion_heroica")
    t = d20(_ventaja_neta(bonos_v, penal + (1 if ventaja < 0 else 0)))
    total = t["natural"] + bono
    inspiracion = None
    cond_insp = next((x for x in c.condiciones
                      if x.get("tipo") == "inspirado"), None)
    if cond_insp:
        insp = roll(cond_insp.get("dado", "1d6"))
        inspiracion = insp["dados"][0]
        total += inspiracion
        c.quitar_condicion("inspirado")
    exito = (total >= cd and not t["pifia"]) or t["critico"]
    margen = cd - total
    if exito:
        grado = "exito_critico" if t["critico"] else "exito"
    elif margen <= 2:
        grado = "fallo_simple"
    elif margen <= 5:
        grado = "fallo_con_complicacion"
    elif margen <= 9:
        grado = "fallo_grave"
    else:
        grado = "fallo_critico"
    if t["pifia"]:
        grado = "fallo_critico"
    return {
        "tipo": "habilidad", "habilidad": habilidad, "atributo": atributo,
        **t, "bono": bono, "total": total, "cd": cd,
        "exito": exito, "grado": grado, "inspiracion": inspiracion,
    }


def tirada_salvacion(c: Criatura, atributo: str, cd: int, ventaja: int = 0) -> dict:
    if atributo in ("FUE", "DES") and (c.tiene_condicion("aturdido")
                                       or c.tiene_condicion("paralizado")):
        return {"tipo": "salvacion", "atributo": atributo, "cd": cd,
                "natural": 0, "tiradas": [], "bono": 0, "total": 0,
                "exito": False, "critico": False, "pifia": False,
                "auto_fallo": "incapacitado"}
    if atributo not in ("FUE", "DES", "CON", "INT", "SAB", "CAR"):
        raise ValueError(f"Atributo inválido: {atributo}")
    # Paralizado/aturdido/inconsciente: falla automática en FUE y DES
    if atributo in ("FUE", "DES") and any(
        c.tiene_condicion(x) for x in ("paralizado", "aturdido", "inconsciente")
    ):
        return {"tipo": "salvacion", "atributo": atributo, "cd": cd,
                "auto_fallo": True, "exito": False, "natural": None, "total": None}
    bono = mod(c.atributos[atributo])
    if atributo in c.competencias.get("salvaciones", []):
        bono += bc(c.nivel)
    t = d20(ventaja)
    total = t["natural"] + bono
    exito = (total >= cd and not t["pifia"]) or t["critico"]
    return {"tipo": "salvacion", "atributo": atributo, **t,
            "bono": bono, "total": total, "cd": cd, "exito": exito}


# ---------------------------------------------------------------- combate

def iniciativa(c: Criatura) -> dict:
    t = d20()
    bono = mod(c.atributos["DES"]) + c.bono_iniciativa
    total = t["natural"] + bono
    return {"tipo": "iniciativa", "criatura_id": c.id, **t,
            "bono": bono, "total": total}


_TIPOS_CASTIGO_DIVINO = {"no_muerto", "infernal", "undead", "fiend"}


def dados_castigo_divino(nivel_slot: int, objetivo: Criatura) -> str:
    """Dados de Castigo Divino (Paladín): 2d8 con slot nivel 1, +1d8 por nivel
    de slot por encima (máx 5d8) y +1d8 extra si el objetivo es no-muerto o
    infernal (máx 6d8). SRD."""
    n = min(2 + max(0, nivel_slot - 1), 5)
    tipo = (objetivo.tipo_criatura or "").lower()
    if any(t in tipo for t in _TIPOS_CASTIGO_DIVINO):
        n = min(n + 1, 6)
    return f"{n}d8"


def _reroll_gwf(dados_expr: str) -> dict:
    """Tira daño de arma re-tirando 1 y 2 una vez (estilo Gran Arma).
    Devuelve el mismo formato que roll()."""
    base = roll(dados_expr)
    caras = int(dados_expr.split("d")[1].split("+")[0].split("-")[0])
    nuevos = []
    for d in base["dados"]:
        if d <= 2:
            d = _RNG_ROLL(caras)
        nuevos.append(d)
    return {"expr": dados_expr + " (gran arma)", "dados": nuevos,
            "mod": base["mod"], "total": sum(nuevos) + base["mod"]}


def _RNG_ROLL(caras: int) -> int:
    from .dice import _RNG
    return _RNG.randint(1, caras)


def resolver_ataque(atacante: Criatura, objetivo: Criatura, arma: Arma,
                    ventaja: int = 0, dos_manos: bool = False,
                    furtivo: bool = False, smite_dados: str | None = None,
                    mano_secundaria: bool = False,
                    imprudente: bool = False) -> dict:
    """Ataque completo: impacto + daño. Muta pg del objetivo si impacta.

    Rasgos que se aplican solos (condiciones/campos del atacante):
    - "ayudado": ventaja en este ataque (se consume)
    - "inspirado": +1d6 al total de ataque (se consume)
    - "furia": +2 daño melé
    - estilo "duelo": +2 daño melé a una mano; "arqueria": +2 ataque a distancia
    - estilo "gran_arma": re-tira 1 y 2 en los dados de daño melé a dos manos
    - furtivo=True (lo decide la capa de juego): +Nd6 de daño del pícaro
    - smite_dados ("3d8"): Castigo Divino del paladín (radiante, solo melé)
    - mano_secundaria=True: ataque con arma secundaria (no suma mod de daño
      salvo estilo de dos armas)
    - imprudente=True: Ataque Temerario del bárbaro (ventaja al atacar; la capa
      de juego marca la condición 'imprudente' para dar ventaja a los enemigos)
    """
    # atributo de ataque
    if arma.distancia:
        atr = "DES"
    elif arma.finura:
        atr = "DES" if mod(atacante.atributos["DES"]) > mod(atacante.atributos["FUE"]) else "FUE"
    else:
        atr = "FUE"
    m = mod(atacante.atributos[atr])
    competente = arma.categoria in atacante.competencias.get("armas", []) \
        or arma.nombre in atacante.competencias.get("armas", [])
    bono_ataque = m + (bc(atacante.nivel) if competente else 0)
    if atacante.estilo_combate == "arqueria" and arma.distancia:
        bono_ataque += 2
    arma_sagrada = next((c for c in atacante.condiciones
                         if c.get("tipo") == "arma_sagrada"), None)
    if arma_sagrada:
        bono_ataque += arma_sagrada.get("valor", 0)

    # ventaja/desventaja situacional + condiciones
    bonos = 1 if ventaja > 0 else 0
    if imprudente and not arma.distancia:
        bonos += 1   # Ataque Temerario: ventaja al atacar cuerpo a cuerpo
    if atacante.tiene_condicion("ayudado"):
        bonos += 1
        atacante.quitar_condicion("ayudado")
    if atacante.tiene_condicion("inspiracion_heroica"):
        bonos += 1   # Inspiración Heroica: ventaja, se consume
        atacante.quitar_condicion("inspiracion_heroica")
    penal = 1 if ventaja < 0 else 0
    if atacante.tiene_condicion("envenenado") or atacante.tiene_condicion("cegado") \
            or atacante.tiene_condicion("asustado") \
            or atacante.tiene_condicion("restringido") \
            or atacante.tiene_condicion("derribado"):
        penal += 1
    if objetivo.tiene_condicion("restringido") \
            or objetivo.tiene_condicion("aturdido") \
            or objetivo.tiene_condicion("paralizado"):
        bonos += 1
    if objetivo.tiene_condicion("cegado"):
        bonos += 1
    if objetivo.tiene_condicion("imprudente"):
        bonos += 1   # bárbaro expuesto por su Ataque Temerario
    if objetivo.tiene_condicion("derribado"):
        if arma.distancia:
            penal += 1
        else:
            bonos += 1
    if objetivo.tiene_condicion("esquivando"):
        penal += 1
    critico_auto = objetivo.tiene_condicion("paralizado") and not arma.distancia

    t = d20(_ventaja_neta(bonos, penal))
    ca = calcular_ca(objetivo)
    total = t["natural"] + bono_ataque
    inspiracion = None
    cond_insp = next((c for c in atacante.condiciones
                      if c.get("tipo") == "inspirado"), None)
    if cond_insp:
        insp = roll(cond_insp.get("dado", "1d6"))
        inspiracion = insp["dados"][0]
        total += inspiracion
        atacante.quitar_condicion("inspirado")
    crit_natural = t["natural"] >= atacante.crit_min
    impacta = crit_natural or (not t["pifia"] and total >= ca)
    critico = crit_natural or (impacta and critico_auto)

    resultado = {
        "tipo": "ataque", "atacante_id": atacante.id, "objetivo_id": objetivo.id,
        "arma": arma.nombre, "atributo": atr, **t,
        "bono_ataque": bono_ataque, "total": total, "ca_objetivo": ca,
        "impacta": impacta, "critico": critico, "danio": None, "efectos": [],
        "inspiracion": inspiracion,
    }
    if impacta:
        dado = arma.dos_manos if (dos_manos and arma.dos_manos) else arma.dado_danio
        # Estilo Gran Arma: re-tira 1 y 2 en los dados de daño (melé a dos manos)
        gwf = (atacante.estilo_combate == "gran_arma" and not arma.distancia
               and (dos_manos or arma.dos_manos_fijo))
        _tira = _reroll_gwf if gwf else roll
        d = _tira(dado)
        if critico:
            extra = _tira(dado)
            d = {"expr": f"{dado} x2 (crítico)",
                 "dados": d["dados"] + extra["dados"], "mod": 0,
                 "total": d["total"] + extra["total"]}
        extras: list[dict] = []
        # Furia del bárbaro: +2 daño melé
        if atacante.tiene_condicion("furia") and not arma.distancia:
            extras.append({"motivo": "furia", "valor": 2})
        # Estilo Duelo: +2 daño melé a una mano (no con ataque de mano secundaria)
        if atacante.estilo_combate == "duelo" and not arma.distancia \
                and not dos_manos and not mano_secundaria:
            extras.append({"motivo": "duelo", "valor": 2})
        # Presa del cazador (ranger Cazador nv3): +1d8 vs heridos
        if atacante.subclase == "cazador" and atacante.nivel >= 3 \
                and objetivo.pg_actual < objetivo.pg_max:
            pc = roll("2d8" if critico else "1d8")
            extras.append({"motivo": "presa_del_cazador", "valor": pc["total"],
                           "dados": pc["dados"]})
        # Ataque furtivo del pícaro (dobla dados en crítico)
        if furtivo and atacante.nivel_furtivo > 0 \
                and (arma.finura or arma.distancia):
            n = atacante.nivel_furtivo * (2 if critico else 1)
            f = roll(f"{n}d6")
            extras.append({"motivo": "furtivo", "valor": f["total"],
                           "dados": f["dados"]})
        # Mano secundaria (dos armas): no suma el mod de atributo al daño salvo
        # que el mod sea negativo o que tengas el estilo de Combate con Dos Armas
        mod_danio = m
        if mano_secundaria and atacante.estilo_combate != "dos_armas":
            mod_danio = min(m, 0)
        danio_total = max(1, d["total"] + mod_danio + sum(e["valor"] for e in extras))
        danio_total, resistido = danio_con_resistencia(
            objetivo, danio_total, arma.tipo_danio)
        # Castigo Divino: paquete de daño radiante aparte (resistencia propia)
        smite = None
        if smite_dados and not arma.distancia:
            sd = roll(smite_dados)
            if critico:
                sx = roll(smite_dados)
                sd = {"dados": sd["dados"] + sx["dados"],
                      "total": sd["total"] + sx["total"]}
            smite_val, smite_resist = danio_con_resistencia(
                objetivo, sd["total"], "radiante")
            danio_total += smite_val
            smite = {"motivo": "castigo_divino", "valor": smite_val,
                     "dados": sd["dados"], "tipo_danio": "radiante",
                     "resistido": smite_resist}
            extras.append(smite)
        resultado["danio"] = {**d, "mod_atributo": mod_danio,
                              "total_final": danio_total,
                              "tipo_danio": arma.tipo_danio,
                              "resistido": resistido,
                              "castigo_divino": smite,
                              "extras": extras}
        resultado["efectos"] = aplicar_danio(objetivo, danio_total)["eventos"]
    return resultado


def aplicar_danio(c: Criatura, danio: int) -> dict:
    """Descuenta PG y devuelve eventos derivados (inconsciencia, check de conc.)."""
    if danio < 0:
        raise ValueError("El daño no puede ser negativo")
    c.pg_actual = max(0, c.pg_actual - danio)
    eventos: list[str] = []
    if c.pg_actual == 0 and not c.tiene_condicion("inconsciente"):
        c.condiciones.append({"tipo": "inconsciente", "origen": "0_pg"})
        c.condiciones.append({"tipo": "derribado", "origen": "0_pg"})
        if c.spell_state and c.spell_state.concentracion_activa:
            c.spell_state.concentracion_activa = None
            eventos.append("concentracion_rota")
        eventos.append("cae_inconsciente")
    elif c.spell_state and c.spell_state.concentracion_activa:
        eventos.append("requiere_check_concentracion")
    return {"pg_actual": c.pg_actual, "eventos": eventos}


def curar(c: Criatura, cantidad: int) -> dict:
    """Cura PG. Si estaba a 0, despierta y resetea salvaciones de muerte."""
    if not c.vivo:
        return {"pg_actual": c.pg_actual, "eventos": ["objetivo_muerto"], "curado": 0}
    antes = c.pg_actual
    c.pg_actual = min(c.pg_max, c.pg_actual + cantidad)
    eventos = []
    if antes == 0 and c.pg_actual > 0:
        c.quitar_condicion("inconsciente")
        c.muerte_exitos = 0
        c.muerte_fallos = 0
        eventos.append("recupera_consciencia")
    return {"pg_actual": c.pg_actual, "eventos": eventos, "curado": c.pg_actual - antes}


def check_concentracion(c: Criatura, danio: int) -> dict:
    """Salvación de CON por daño recibido concentrando. Muta spell_state si falla."""
    cd = max(10, danio // 2)
    res = tirada_salvacion(c, "CON", cd)
    res["tipo"] = "concentracion"
    res["hechizo"] = (c.spell_state.concentracion_activa or {}).get("hechizo")
    if not res["exito"] and c.spell_state:
        c.spell_state.concentracion_activa = None
        res["concentracion_rota"] = True
    else:
        res["concentracion_rota"] = False
    return res


def salvacion_muerte(c: Criatura) -> dict:
    """Tirada automática del servidor al inicio del turno de un PJ a 0 PG."""
    t = d20()
    n = t["natural"]
    evento = None
    if n == 20:
        c.pg_actual = 1
        c.quitar_condicion("inconsciente")
        c.muerte_exitos = 0
        c.muerte_fallos = 0
        evento = "despierta_con_1pg"
    elif n == 1:
        c.muerte_fallos += 2
    elif n >= 10:
        c.muerte_exitos += 1
    else:
        c.muerte_fallos += 1

    if c.muerte_fallos >= 3:
        c.vivo = False
        evento = "muerte"
    elif c.muerte_exitos >= 3:
        # Estabilizado: no muere, pero sigue inconsciente hasta recibir curación
        c.condiciones.append({"tipo": "estable", "origen": "salvaciones"})
        c.muerte_exitos = 0
        c.muerte_fallos = 0
        evento = "estabilizado"
    return {"tipo": "salvacion_muerte", **t,
            "exitos": c.muerte_exitos, "fallos": c.muerte_fallos, "evento": evento}


# ---------------------------------------------------------------- magia

def gastar_slot(c: Criatura, nivel: int) -> dict:
    """Valida y descuenta un espacio de conjuro. Devuelve ok=False si no hay."""
    ss = c.spell_state
    if ss is None:
        return {"ok": False, "motivo": "no_es_lanzador"}
    s = ss.slots.get(str(nivel))
    if not s:
        return {"ok": False, "motivo": f"sin_slots_nivel_{nivel}"}
    if s["usados"] >= s["max"]:
        return {"ok": False, "motivo": "slots_agotados",
                "slots": {nivel: f"{s['usados']}/{s['max']}"}}
    s["usados"] += 1
    return {"ok": True, "nivel": nivel,
            "restantes": s["max"] - s["usados"], "max": s["max"]}


def puede_lanzar(c: Criatura, hechizo: str, requiere_verbal=True, requiere_somatico=True) -> dict:
    """Validaciones previas al gasto de slot."""
    ss = c.spell_state
    if ss is None:
        return {"ok": False, "motivo": "no_es_lanzador"}
    lista = ss.preparados if ss.preparados else ss.conocidos
    if hechizo not in lista:
        return {"ok": False, "motivo": "hechizo_no_disponible"}
    if requiere_verbal and c.tiene_condicion("silenciado"):
        return {"ok": False, "motivo": "silenciado"}
    for cond in ("paralizado", "aturdido", "inconsciente"):
        if c.tiene_condicion(cond):
            return {"ok": False, "motivo": cond}
    return {"ok": True}


def cd_salvacion_magica(c: Criatura, atributo_clave: str) -> int:
    return 8 + bc(c.nivel) + mod(c.atributos[atributo_clave])


def tirar_danio_conjuro(base_expr: str, escalado_expr: str | None = None,
                        niveles_extra: int = 0, empoderar: int = 0) -> dict:
    """Tira el daño (o curación) de un conjuro con:
    - escalado por upcasting: +escalado_expr por cada nivel de slot extra.
    - Conjuro Empoderado: re-tira los 'empoderar' dados más bajos y usa el nuevo
      valor (asume dados del mismo tamaño que el daño base).
    Devuelve el mismo formato que roll() más metadatos.
    """
    d = roll(base_expr)
    dados = list(d["dados"])
    mod_base = d["mod"]
    caras = int(base_expr.lower().split("d")[1].split("+")[0].split("-")[0])
    if escalado_expr and niveles_extra > 0:
        n, c = escalado_expr.lower().split("d")
        e = roll(f"{int(n) * niveles_extra}d{c}")
        dados += e["dados"]
    if empoderar > 0:
        orden = sorted(range(len(dados)), key=lambda i: dados[i])[:empoderar]
        for i in orden:
            dados[i] = _RNG_ROLL(caras)
    return {"expr": base_expr, "escalado": escalado_expr,
            "niveles_extra": niveles_extra, "empoderado": empoderar,
            "dados": dados, "mod": mod_base, "total": sum(dados) + mod_base}


def ataque_magico(lanzador: Criatura, objetivo: Criatura, atributo_clave: str,
                  dado_danio: str, tipo_danio: str, ventaja: int = 0,
                  bono_danio: int = 0) -> dict:
    """Ataque de conjuro. bono_danio suma un plano al daño (p. ej. Explosión
    Agonizante del brujo: +mod de CAR)."""
    bono = mod(lanzador.atributos[atributo_clave]) + bc(lanzador.nivel)
    t = d20(ventaja)
    ca = calcular_ca(objetivo)
    total = t["natural"] + bono
    impacta = t["critico"] or (not t["pifia"] and total >= ca)
    resultado = {"tipo": "ataque_magico", "atacante_id": lanzador.id,
                 "objetivo_id": objetivo.id, **t, "bono": bono, "total": total,
                 "ca_objetivo": ca, "impacta": impacta, "danio": None, "efectos": []}
    if impacta:
        d = roll(dado_danio)
        if t["critico"]:
            extra = roll(dado_danio)
            d = {"expr": f"{dado_danio} x2 (crítico)",
                 "dados": d["dados"] + extra["dados"], "mod": 0,
                 "total": d["total"] + extra["total"]}
        danio_final = max(0, d["total"] + bono_danio)
        resultado["danio"] = {**d, "total_final": danio_final,
                              "bono_danio": bono_danio, "tipo_danio": tipo_danio}
        resultado["efectos"] = aplicar_danio(objetivo, danio_final)["eventos"]
    return resultado


# ---------------------------------------------------------------- descansos

def descanso_corto(c: Criatura, dados_a_gastar: int) -> dict:
    """Gasta Dados de Golpe para curar. Brujo recupera slots (flag aparte en API)."""
    if dados_a_gastar < 0 or dados_a_gastar > c.dados_golpe_disp:
        return {"ok": False, "motivo": "dados_insuficientes",
                "disponibles": c.dados_golpe_disp}
    tiradas = []
    total = 0
    con = mod(c.atributos["CON"])
    for _ in range(dados_a_gastar):
        r = roll(f"1{c.dado_golpe}")
        tiradas.append(r["dados"][0])
        total += max(0, r["dados"][0] + con)
    c.dados_golpe_disp -= dados_a_gastar
    cur = curar(c, total)
    return {"ok": True, "tipo": "descanso_corto", "dados_gastados": dados_a_gastar,
            "tiradas": tiradas, "mod_con": con, "curado": cur["curado"],
            "pg_actual": c.pg_actual, "dados_restantes": c.dados_golpe_disp}


def descanso_largo(c: Criatura) -> dict:
    """Recupera PG, mitad de Dados de Golpe y todos los slots."""
    c.pg_actual = c.pg_max
    recupera_dados = max(1, c.nivel // 2)
    c.dados_golpe_disp = min(c.nivel, c.dados_golpe_disp + recupera_dados)
    if c.spell_state:
        for s in c.spell_state.slots.values():
            s["usados"] = 0
        c.spell_state.concentracion_activa = None
    c.quitar_condicion("estable")
    return {"ok": True, "tipo": "descanso_largo", "pg_actual": c.pg_actual,
            "dados_golpe_disp": c.dados_golpe_disp}


# ---------------------------------------------------------------- progresión

def nivel_por_xp(xp: int) -> int:
    nivel = 1
    for nv, req in XP_POR_NIVEL.items():
        if xp >= req:
            nivel = nv
    return nivel


def danio_con_resistencia(objetivo: Criatura, total: int,
                          tipo_danio: str) -> tuple[int, bool]:
    """Aplica resistencias: mitad (redondeo abajo, mín 1) si el objetivo
    resiste ese tipo de daño."""
    if tipo_danio and tipo_danio in objetivo.resistencias:
        return max(1, total // 2), True
    return total, False


def ataque_statblock(atacante: Criatura, objetivo: Criatura, nombre: str,
                     bono: int, danio_expr: str,
                     tipo_danio: str = "?", ventaja: int = 0) -> dict:
    """Ataque de monstruo con números de stat block (importados del SRD):
    bono de ataque fijo y expresión de daño con modificador incluido."""
    bonos = 1 if ventaja > 0 else 0
    penal = 1 if ventaja < 0 else 0
    if objetivo.tiene_condicion("esquivando"):
        penal += 1
    if objetivo.tiene_condicion("derribado"):
        bonos += 1  # asumimos melé para monstruos v1
    if objetivo.tiene_condicion("restringido") \
            or objetivo.tiene_condicion("aturdido") \
            or objetivo.tiene_condicion("paralizado"):
        bonos += 1
    if objetivo.tiene_condicion("cegado"):
        bonos += 1
    if objetivo.tiene_condicion("imprudente"):
        bonos += 1
    t = d20(_ventaja_neta(bonos, penal))
    ca = calcular_ca(objetivo)
    total = t["natural"] + bono
    impacta = t["critico"] or (not t["pifia"] and total >= ca)
    if impacta and objetivo.tiene_condicion("paralizado"):
        t = {**t, "critico": True}  # golpe a paralizado: crítico (melé asumido)
    resultado = {"tipo": "ataque", "atacante_id": atacante.id,
                 "objetivo_id": objetivo.id, "arma": nombre, **t,
                 "bono_ataque": bono, "total": total, "ca_objetivo": ca,
                 "impacta": impacta, "critico": t["critico"],
                 "danio": None, "efectos": [], "inspiracion": None}
    if impacta:
        d = roll(danio_expr)
        if t["critico"]:
            extra = roll(danio_expr)
            d = {"expr": f"{danio_expr} x2 (crítico)",
                 "dados": d["dados"] + extra["dados"], "mod": d["mod"],
                 "total": d["total"] + extra["total"] - extra["mod"]}
        danio_total = max(1, d["total"])
        danio_total, resistido = danio_con_resistencia(
            objetivo, danio_total, tipo_danio)
        resultado["danio"] = {**d, "total_final": danio_total,
                              "tipo_danio": tipo_danio,
                              "resistido": resistido, "extras": []}
        resultado["efectos"] = aplicar_danio(objetivo, danio_total)["eventos"]
    return resultado


INCAPACITANTES = {"aturdido", "paralizado"}
CONDICIONES_APLICABLES = {"envenenado", "asustado", "cegado", "derribado",
                          "restringido", "aturdido", "paralizado", "agarrado"}


def tick_condiciones(c: Criatura) -> list[str]:
    """Al inicio del turno de la criatura: expira condiciones con 'rondas'.
    Devuelve los tipos que expiraron."""
    expiradas = []
    nuevas = []
    for cond in c.condiciones:
        rondas = cond.get("rondas")
        if rondas is None:
            nuevas.append(cond)
            continue
        if rondas <= 1:
            expiradas.append(cond.get("tipo", "?"))
        else:
            nuevas.append({**cond, "rondas": rondas - 1})
    c.condiciones = nuevas
    return expiradas


def esta_incapacitado(c: Criatura) -> bool:
    return any(c.tiene_condicion(t) for t in INCAPACITANTES)
