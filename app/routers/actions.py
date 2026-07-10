"""Acciones de juego — versión completa.

Cambios clave respecto al paso 3:
- LATENCIA: los endpoints devuelven la resolución mecánica AL INSTANTE y la
  narración del LLM corre en BackgroundTask (Campaign.narrando=True mientras
  tanto; el polling del cliente la levanta cuando está lista).
- TIMEOUT DE TURNO: si un PJ no actúa en 120s, el servidor le aplica Esquivar
  y pasa el turno (se chequea en cada GET de campaña — los clientes pollean).
- DESCANSOS corto (por personaje) y largo (grupal).
- INVENTARIO: usar consumibles, equipar, dar objetos.
- SUBIDA DE NIVEL cuando la XP alcanza.
- MUERTE: _mi_personaje elige el personaje VIVO del jugador (permite reemplazo).
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.combat import Combat
from engine.content import (ARMADURAS, ARMAS, CLASES, CONJUROS, CONSUMIBLES,
                            MONSTRUOS, XP_POR_CR, slots_iniciales)
from engine.dice import roll
from engine.rules import (ataque_magico, cd_salvacion_magica,
                          check_concentracion, curar, descanso_corto,
                          descanso_largo, gastar_slot, mod, nivel_por_xp,
                          puede_lanzar, resolver_ataque, salvacion_muerte,
                          tirada_habilidad, tirada_salvacion)

from ..context import actualizar_resumen_si_corresponde, construir_contexto
from ..db import SessionLocal, get_db
from ..deps import jugador_actual
from ..effects import aplicar_efectos
from ..hydration import (hidratar_npc, hidratar_personaje, persistir_npc,
                         persistir_personaje)
from ..models import (NPC, Campaign, Character, Message, PendingConsequence,
                      Player, Quest, Roll)
from ..narrator import narrar

router = APIRouter(prefix="/api/campaigns/{campaign_id}", tags=["actions"])

TIMEOUT_TURNO_SEG = 120


# ================================================================ helpers

async def _mi_personaje(campaign_id: int, player: Player,
                        db: AsyncSession) -> Character:
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    res = await db.execute(select(Character)
                           .where(Character.player_id == player.id)
                           .order_by(Character.id.desc()))
    chars = res.scalars().all()
    if not chars:
        raise HTTPException(400, "Todavía no creaste un personaje")
    vivo = next((c for c in chars if c.vivo), None)
    if vivo is None:
        raise HTTPException(400, "Tu personaje está muerto. Creá uno nuevo.")
    return vivo


def _msg(db, campaign_id, autor, autor_nombre, contenido):
    db.add(Message(campaign_id=campaign_id, autor=autor,
                   autor_nombre=autor_nombre, contenido=contenido))


def _roll(db, campaign_id, resolucion, character_id=None):
    db.add(Roll(campaign_id=campaign_id, character_id=character_id,
                resolucion=resolucion))


def _quitar_esquivando(char: Character):
    char.condiciones = [c for c in char.condiciones
                        if c.get("tipo") != "esquivando"]


# ---------------- narración en background (fix de latencia) ----------------

def encolar_narracion(bg: BackgroundTasks, camp: Campaign,
                      accion: str, actor_id: int | None):
    """Marca narrando=True (el caller comitea) y agenda la narración."""
    camp.narrando = True
    bg.add_task(_narrar_bg, camp.id, accion, actor_id)


async def _narrar_bg(campaign_id: int, accion: str, actor_id: int | None):
    """Corre DESPUÉS de responder el HTTP, con su propia sesión de DB."""
    async with SessionLocal() as db:
        camp = await db.get(Campaign, campaign_id)
        try:
            contexto = await construir_contexto(db, camp)
            narracion, efectos = await narrar(contexto, accion)
            actor = await db.get(Character, actor_id) if actor_id else None
            log = await aplicar_efectos(db, camp, efectos, actor=actor)
            _msg(db, campaign_id, "dm", "DM", narracion)
            if log.get("aplicados"):
                resumen_fx = ", ".join(f"{k}: {v}" for k, v in log["aplicados"])
                _msg(db, campaign_id, "sistema", "Sistema", f"✱ {resumen_fx}")
            if log.get("inicia_combate") and camp.estado != "combate":
                await _iniciar_combate(db, camp, log["inicia_combate"])
            await actualizar_resumen_si_corresponde(db, camp)
        except Exception as e:  # nunca dejar narrando=True colgado
            print(f"[narrador-bg] error: {e}")
            _msg(db, campaign_id, "sistema", "Sistema",
                 "⚠ El DM se quedó sin palabras (error del narrador). "
                 "La mecánica ya está aplicada; continúen.")
        finally:
            camp.narrando = False
            await db.commit()


# ---------------- timeout de turno --------------------------------------

async def chequear_timeout_turno(db: AsyncSession, camp: Campaign) -> list[dict]:
    """Si el PJ del turno actual lleva >120s sin actuar: Esquivar automático
    y pasa el turno. Lo llaman los GET (los clientes pollean constantemente)."""
    if camp.estado != "combate" or not camp.combate:
        return []
    combate = Combat.from_dict(camp.combate)
    if not combate.activo or combate.turno_actual["tipo"] != "pj":
        return []
    ts = combate.turno_ts
    if ts is None or time.time() - ts < TIMEOUT_TURNO_SEG:
        return []

    char = await db.get(Character, int(combate.turno_actual["id"].split("_")[1]))
    if char.pg_actual > 0:
        _quitar_esquivando(char)
        char.condiciones = list(char.condiciones) + [
            {"tipo": "esquivando", "origen": "timeout"}]
        _msg(db, camp.id, "sistema", "Sistema",
             f"⏱ {char.nombre} duda demasiado: se cubre (Esquivar) y pierde el turno.")
    combate.avanzar_turno()
    combate.turno_ts = time.time()
    camp.combate = combate.to_dict()
    eventos = await _resolver_turnos_npc(db, camp)
    await db.commit()
    return eventos


# ================================================================ narrativa

class AccionNarrativa(BaseModel):
    texto: str


@router.post("/say")
async def accion_narrativa(campaign_id: int, body: AccionNarrativa,
                           bg: BackgroundTasks,
                           player: Player = Depends(jugador_actual),
                           db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "Estás en combate: usá attack o cast")
    _msg(db, campaign_id, "jugador", char.nombre, body.texto)
    encolar_narracion(bg, camp, f"{char.nombre} dice/hace: {body.texto}", char.id)
    await db.commit()
    return {"ok": True, "narrando": True}


class AccionHabilidad(BaseModel):
    habilidad: str
    cd: int = 12
    descripcion: str = ""


@router.post("/skill-check")
async def accion_habilidad(campaign_id: int, body: AccionHabilidad,
                           bg: BackgroundTasks,
                           player: Player = Depends(jugador_actual),
                           db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    cr = hidratar_personaje(char)
    r = tirada_habilidad(cr, body.habilidad, body.cd)
    persistir_personaje(cr, char)
    _msg(db, campaign_id, "jugador", char.nombre,
         f"[{body.habilidad}] {body.descripcion}")
    _roll(db, campaign_id, r, char.id)
    encolar_narracion(
        bg, camp,
        f"{char.nombre} intenta {body.habilidad} "
        f"({body.descripcion or 'sin detalle'}). "
        f"Resultado del sistema: {json.dumps(r, ensure_ascii=False)}",
        char.id)
    await db.commit()
    return {"resolucion": r, "narrando": True}


# ================================================================ combate

async def _iniciar_combate(db: AsyncSession, camp: Campaign,
                           monstruos: list[str]) -> dict:
    npcs = []
    contador: dict[str, int] = {}
    for plantilla in monstruos:
        contador[plantilla] = contador.get(plantilla, 0) + 1
        info = MONSTRUOS[plantilla]
        n = NPC(campaign_id=camp.id, tipo="monstruo", plantilla=plantilla,
                nombre=f"{info['nombre']} {contador[plantilla]}",
                stats=info, pg_actual=info["pg"], en_escena=True,
                actitud="hostil")
        db.add(n)
        npcs.append(n)
    await db.flush()

    res = await db.execute(select(Character).where(
        Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
    chars = res.scalars().all()
    combate = Combat.iniciar([hidratar_personaje(c) for c in chars],
                             [hidratar_npc(n) for n in npcs])
    combate.turno_ts = time.time()
    camp.combate = combate.to_dict()
    camp.estado = "combate"
    _msg(db, camp.id, "sistema", "Sistema",
         f"⚔️ Combate iniciado. Orden: {[e['id'] for e in combate.orden]}")
    _roll(db, camp.id, {"tipo": "inicio_combate",
                        "iniciativas": combate.tiradas_iniciativa})
    eventos = await _resolver_turnos_npc(db, camp)
    return {"orden": combate.orden, "iniciativas": combate.tiradas_iniciativa,
            "turnos_npc": eventos}


class IniciarCombate(BaseModel):
    monstruos: list[str]


@router.post("/combat/start")
async def iniciar_combate_manual(campaign_id: int, body: IniciarCombate,
                                 bg: BackgroundTasks,
                                 player: Player = Depends(jugador_actual),
                                 db: AsyncSession = Depends(get_db)):
    await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "Ya hay un combate activo")
    for m in body.monstruos:
        if m not in MONSTRUOS:
            raise HTTPException(400, f"Monstruo desconocido: {m}. "
                                     f"Opciones: {list(MONSTRUOS)}")
    resultado = await _iniciar_combate(db, camp, body.monstruos)
    encolar_narracion(
        bg, camp,
        f"Comienza un combate contra {body.monstruos}. "
        f"Iniciativas: {json.dumps(resultado['iniciativas'], ensure_ascii=False)}. "
        f"Primeros turnos enemigos: "
        f"{json.dumps(resultado['turnos_npc'], ensure_ascii=False)}",
        None)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {**resultado, "combate": camp.combate}


async def _post_accion_combate(db: AsyncSession, camp: Campaign,
                               combate: Combat, char: Character,
                               objetivo: NPC | None) -> tuple[list, str | None]:
    if objetivo is not None and (objetivo.pg_actual or 0) == 0:
        combate.remover(f"npc_{objetivo.id}")

    fin = None
    if not combate.npcs_restantes():
        fin = "victoria"
        combate.activo = False
        camp.estado = "exploracion"
        camp.combate = None
        res = await db.execute(select(NPC).where(
            NPC.campaign_id == camp.id, NPC.tipo == "monstruo",
            NPC.vivo == False, NPC.en_escena == True))  # noqa: E712
        caidos = res.scalars().all()
        xp_total = sum(XP_POR_CR.get((n.stats or {}).get("cr", "0"), 10)
                       for n in caidos)
        for n in caidos:
            n.en_escena = False
        res = await db.execute(select(Character).where(
            Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
        vivos = res.scalars().all()
        if vivos and xp_total:
            porcada = max(1, xp_total // len(vivos))
            for c in vivos:
                c.xp += porcada
                if nivel_por_xp(c.xp) > c.nivel:
                    _msg(db, camp.id, "sistema", "Sistema",
                         f"⭐ {c.nombre} puede subir a nivel {nivel_por_xp(c.xp)} "
                         f"(botón en la ficha).")
            _msg(db, camp.id, "sistema", "Sistema",
                 f"⚔️ Victoria. +{porcada} XP para cada personaje vivo.")
    else:
        combate.avanzar_turno()
        combate.turno_ts = time.time()

    camp.combate = combate.to_dict() if combate.activo else None
    eventos = []
    if combate.activo:
        eventos = await _resolver_turnos_npc(db, camp)
        if camp.estado != "combate":
            fin = "derrota"
    return eventos, fin


class Atacar(BaseModel):
    objetivo_npc_id: int
    dos_manos: bool = False


@router.post("/combat/attack")
async def atacar(campaign_id: int, body: Atacar, bg: BackgroundTasks,
                 player: Player = Depends(jugador_actual),
                 db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, "No es tu turno")
    if not char.arma_equipada:
        raise HTTPException(400, "No tenés arma equipada")
    npc = await db.get(NPC, body.objetivo_npc_id)
    if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
        raise HTTPException(404, "Objetivo inválido o ya está fuera de combate")

    _quitar_esquivando(char)
    cr_pj = hidratar_personaje(char)
    cr_npc = hidratar_npc(npc)
    r = resolver_ataque(cr_pj, cr_npc, ARMAS[char.arma_equipada],
                        dos_manos=body.dos_manos)
    persistir_personaje(cr_pj, char)
    persistir_npc(cr_npc, npc)
    _msg(db, campaign_id, "jugador", char.nombre, f"[ataque] contra {npc.nombre}")
    _roll(db, campaign_id, r, char.id)

    eventos, fin = await _post_accion_combate(db, camp, combate, char, npc)
    encolar_narracion(
        bg, camp,
        f"Ataque de {char.nombre} contra {npc.nombre}: "
        f"{json.dumps(r, ensure_ascii=False)}. "
        f"Turnos de enemigos: {json.dumps(eventos, ensure_ascii=False)}. "
        f"{('Fin del combate: ' + fin) if fin else 'El combate continúa.'}",
        char.id)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {"resolucion": r, "turnos_npc": eventos, "fin_combate": fin,
            "narrando": True, "combate": camp.combate}


class Lanzar(BaseModel):
    conjuro: str
    objetivo_npc_id: int | None = None
    objetivo_character_id: int | None = None
    nivel_slot: int | None = None


@router.post("/combat/cast")
async def lanzar_conjuro(campaign_id: int, body: Lanzar, bg: BackgroundTasks,
                         player: Player = Depends(jugador_actual),
                         db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, "No es tu turno")

    conjuro = CONJUROS.get(body.conjuro)
    if conjuro is None:
        raise HTTPException(400, f"Conjuro desconocido: {body.conjuro}")

    _quitar_esquivando(char)
    cr_pj = hidratar_personaje(char)
    val = puede_lanzar(cr_pj, body.conjuro)
    if not val["ok"]:
        raise HTTPException(400, f"No podés lanzarlo: {val['motivo']}")

    nivel = conjuro["nivel"]
    gasto = None
    if nivel > 0:
        nivel_usado = body.nivel_slot or nivel
        if nivel_usado < nivel:
            raise HTTPException(400, f"Este conjuro requiere slot nivel {nivel}+")
        gasto = gastar_slot(cr_pj, nivel_usado)
        if not gasto["ok"]:
            raise HTTPException(400, f"Sin espacios: {gasto['motivo']}")

    atributo = CLASES[char.clase]["atributo_magico"] or "INT"
    resoluciones: list[dict] = []
    objetivo_nombre = None
    npc = None

    tipo = conjuro["resolucion"]
    if tipo in ("ataque", "salvacion") or (tipo == "auto" and conjuro.get("proyectiles")):
        npc = await db.get(NPC, body.objetivo_npc_id or -1)
        if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = npc.nombre
        cr_npc = hidratar_npc(npc)

        if tipo == "ataque":
            r = ataque_magico(cr_pj, cr_npc, atributo,
                              conjuro["danio"], conjuro["tipo_danio"])
            resoluciones.append(r)
        elif tipo == "salvacion":
            cd = cd_salvacion_magica(cr_pj, atributo)
            salv = tirada_salvacion(cr_npc, conjuro["salvacion"], cd)
            resoluciones.append(salv)
            if conjuro.get("danio"):
                d = roll(conjuro["danio"])
                final = d["total"]
                if salv["exito"]:
                    final = final // 2 if conjuro.get(
                        "en_salvacion_exitosa") == "mitad" else 0
                if final:
                    from engine.rules import aplicar_danio
                    ev = aplicar_danio(cr_npc, final)
                    resoluciones.append({"tipo": "danio_conjuro", **d,
                                         "final": final,
                                         "efectos": ev["eventos"]})
            elif not salv["exito"]:
                cond = ("paralizado" if "inmovilizar" in body.conjuro
                        else "hechizado")
                cr_npc.condiciones.append({"tipo": cond, "origen": body.conjuro})
                resoluciones.append({"tipo": "condicion_aplicada",
                                     "conjuro": body.conjuro})
        else:  # auto con proyectiles (proyectil mágico)
            from engine.rules import aplicar_danio
            total, dados = 0, []
            for _ in range(conjuro["proyectiles"]):
                d = roll(conjuro["danio"])
                dados.append(d["dados"])
                total += d["total"]
            ev = aplicar_danio(cr_npc, total)
            resoluciones.append({"tipo": "danio_auto", "dados": dados,
                                 "total_final": total,
                                 "efectos": ev["eventos"]})
        persistir_npc(cr_npc, npc)

    elif tipo == "curacion":
        obj = await db.get(Character, body.objetivo_character_id or char.id)
        if obj is None or obj.campaign_id != campaign_id:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = obj.nombre
        cr_obj = hidratar_personaje(obj) if obj.id != char.id else cr_pj
        d = roll(conjuro["curacion"])
        total = d["total"] + (mod(cr_pj.atributos[atributo])
                              if conjuro.get("suma_mod_magico") else 0)
        cur = curar(cr_obj, total)
        resoluciones.append({"tipo": "curacion", **d, "total_final": total, **cur})
        if obj.id != char.id:
            persistir_personaje(cr_obj, obj)

    else:  # auto sin proyectiles (escudo, bendecir...)
        resoluciones.append({"tipo": "efecto_auto",
                             "efecto": conjuro.get("efecto", body.conjuro)})

    if conjuro.get("concentracion"):
        cr_pj.spell_state.concentracion_activa = {
            "hechizo": body.conjuro, "desde_ronda": combate.ronda}

    persistir_personaje(cr_pj, char)
    _msg(db, campaign_id, "jugador", char.nombre,
         f"[conjuro] {body.conjuro}" +
         (f" contra {objetivo_nombre}" if objetivo_nombre else ""))
    for r in resoluciones:
        _roll(db, campaign_id, r, char.id)

    eventos, fin = await _post_accion_combate(db, camp, combate, char, npc)
    encolar_narracion(
        bg, camp,
        f"{char.nombre} lanza {body.conjuro}"
        f"{' contra ' + objetivo_nombre if objetivo_nombre else ''}. "
        f"Resultados: {json.dumps(resoluciones, ensure_ascii=False)}. "
        f"Turnos de enemigos: {json.dumps(eventos, ensure_ascii=False)}. "
        f"{('Fin del combate: ' + fin) if fin else ''}",
        char.id)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {"resoluciones": resoluciones, "gasto_slot": gasto,
            "turnos_npc": eventos, "fin_combate": fin,
            "narrando": True, "combate": camp.combate}


async def _resolver_turnos_npc(db: AsyncSession, camp: Campaign) -> list[dict]:
    if not camp.combate:
        return []
    combate = Combat.from_dict(camp.combate)
    eventos: list[dict] = []

    for _ in range(30):
        if not combate.activo:
            break
        actual = combate.turno_actual

        if actual["tipo"] == "pj":
            char = await db.get(Character, int(actual["id"].split("_")[1]))
            if char.pg_actual > 0:
                _quitar_esquivando(char)  # empieza su turno: deja de cubrirse
                break
            cr = hidratar_personaje(char)
            r = salvacion_muerte(cr)
            persistir_personaje(cr, char)
            eventos.append({"actor": char.nombre, "salvacion_muerte": r})
            _roll(db, camp.id, r, char.id)
            if r["evento"] == "muerte":
                _msg(db, camp.id, "sistema", "Sistema",
                     f"💀 {char.nombre} ha muerto.")
                combate.remover(actual["id"])
                if not combate.pjs_restantes():
                    camp.estado = "exploracion"
                    camp.combate = None
                    eventos.append({"fin_combate": "derrota_total"})
                    return eventos
            else:
                combate.avanzar_turno()
            continue

        npc = await db.get(NPC, int(actual["id"].split("_")[1]))
        res = await db.execute(select(Character).where(
            Character.campaign_id == camp.id,
            Character.vivo == True, Character.pg_actual > 0))  # noqa: E712
        objetivos = res.scalars().all()
        if not objetivos:
            camp.estado = "exploracion"
            camp.combate = None
            eventos.append({"fin_combate": "derrota_total"})
            return eventos

        objetivo = min(objetivos, key=lambda c: c.pg_actual)
        arma_nombre = (npc.stats or {}).get("armas", ["garrote"])[0]
        arma = ARMAS.get(arma_nombre, ARMAS["garrote"])
        cr_npc = hidratar_npc(npc)
        cr_pj = hidratar_personaje(objetivo)
        r = resolver_ataque(cr_npc, cr_pj, arma)
        if "requiere_check_concentracion" in r.get("efectos", []):
            conc = check_concentracion(cr_pj, r["danio"]["total_final"])
            eventos.append({"actor": objetivo.nombre, "concentracion": conc})
            _roll(db, camp.id, conc, objetivo.id)
        persistir_personaje(cr_pj, objetivo)
        persistir_npc(cr_npc, npc)
        eventos.append({"actor": npc.nombre, "ataque": r,
                        "objetivo": objetivo.nombre})
        _roll(db, camp.id, r)
        combate.avanzar_turno()

    combate.turno_ts = time.time()
    camp.combate = combate.to_dict() if combate.activo else None
    return eventos


# ================================================================ descansos

class DescansoCorto(BaseModel):
    dados: int = 1


@router.post("/rest/short")
async def rest_short(campaign_id: int, body: DescansoCorto,
                     player: Player = Depends(jugador_actual),
                     db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "No se descansa en combate")
    cr = hidratar_personaje(char)
    r = descanso_corto(cr, body.dados)
    if not r["ok"]:
        raise HTTPException(400, f"No podés: {r['motivo']} "
                                 f"(disponibles: {r.get('disponibles', 0)})")
    # Brujo: recupera todos sus slots con descanso corto
    if char.clase == "brujo" and cr.spell_state:
        for s in cr.spell_state.slots.values():
            s["usados"] = 0
        r["slots_brujo_recuperados"] = True
    persistir_personaje(cr, char)
    camp.tiempo_juego_min += 60
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🔥 {char.nombre} descansa una hora: gasta {body.dados} dado(s) de "
         f"golpe y recupera {r['curado']} PG "
         f"({char.pg_actual}/{char.pg_max}).")
    _roll(db, campaign_id, r, char.id)
    await db.commit()
    return r


@router.post("/rest/long")
async def rest_long(campaign_id: int, bg: BackgroundTasks,
                    player: Player = Depends(jugador_actual),
                    db: AsyncSession = Depends(get_db)):
    await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "No se descansa en combate")
    if camp.tiempo_juego_min - camp.ultimo_descanso_largo_min < 480:
        raise HTTPException(409, "Descansaron hace muy poco (regla de una vez "
                                 "por día de juego)")
    res = await db.execute(select(Character).where(
        Character.campaign_id == campaign_id, Character.vivo == True))  # noqa: E712
    resultados = {}
    for c in res.scalars().all():
        cr = hidratar_personaje(c)
        r = descanso_largo(cr)
        persistir_personaje(cr, c)
        c.pg_actual = c.pg_max  # persistir_personaje ya lo hace; explícito
        resultados[c.nombre] = {"pg": c.pg_max, "dados": c.dados_golpe_disp}
    camp.tiempo_juego_min += 480
    camp.ultimo_descanso_largo_min = camp.tiempo_juego_min
    _msg(db, campaign_id, "sistema", "Sistema",
         "🌙 El grupo hace un descanso largo: PG al máximo, espacios de "
         "conjuro recuperados, mitad de los dados de golpe de vuelta.")
    encolar_narracion(bg, camp,
                      "El grupo acampa y hace un descanso largo de 8 horas. "
                      "Narrá el paso de la noche (puede pasar algo o no).",
                      None)
    await db.commit()
    return {"ok": True, "resultados": resultados}


# ================================================================ inventario

class UsarObjeto(BaseModel):
    nombre: str


@router.post("/inventory/use")
async def usar_objeto(campaign_id: int, body: UsarObjeto,
                      player: Player = Depends(jugador_actual),
                      db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    inv = list(char.inventario)
    item = next((x for x in inv if x.get("nombre") == body.nombre
                 and x.get("cantidad", 0) > 0), None)
    if item is None:
        raise HTTPException(404, f"No tenés {body.nombre}")

    info = CONSUMIBLES.get(body.nombre, {"efecto": "narrativo"})
    resultado = {"objeto": body.nombre}
    if info["efecto"] == "curacion":
        if camp.estado == "combate":
            combate = Combat.from_dict(camp.combate)
            if not combate.es_turno_de(f"pj_{char.id}"):
                raise HTTPException(409, "En combate solo podés usar objetos "
                                         "en tu turno")
        cr = hidratar_personaje(char)
        d = roll(info["formula"])
        cur = curar(cr, d["total"])
        persistir_personaje(cr, char)
        resultado.update({"tipo": "curacion", **d, "curado": cur["curado"],
                          "pg_actual": char.pg_actual})
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🧪 {char.nombre} usa {body.nombre}: +{cur['curado']} PG "
             f"({char.pg_actual}/{char.pg_max}).")
        _roll(db, campaign_id, resultado, char.id)
        # usar objeto en combate consume el turno
        if camp.estado == "combate":
            combate = Combat.from_dict(camp.combate)
            combate.avanzar_turno()
            combate.turno_ts = time.time()
            camp.combate = combate.to_dict()
            await _resolver_turnos_npc(db, camp)
    else:
        _msg(db, campaign_id, "sistema", "Sistema",
             f"{char.nombre} usa {body.nombre}.")

    item["cantidad"] -= 1
    char.inventario = [x for x in inv if x.get("cantidad", 0) > 0]
    await db.commit()
    return resultado


class Equipar(BaseModel):
    arma: str | None = None
    armadura: str | None = None
    escudo: bool | None = None


@router.post("/inventory/equip")
async def equipar(campaign_id: int, body: Equipar,
                  player: Player = Depends(jugador_actual),
                  db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "No podés reequiparte en pleno combate")
    nombres_inv = {x.get("nombre") for x in char.inventario}
    if body.arma is not None:
        if body.arma not in ARMAS:
            raise HTTPException(400, "Arma desconocida")
        if body.arma not in nombres_inv and body.arma != char.arma_equipada:
            raise HTTPException(400, f"No tenés {body.arma} en el inventario")
        char.arma_equipada = body.arma
    if body.armadura is not None:
        if body.armadura and body.armadura not in ARMADURAS:
            raise HTTPException(400, "Armadura desconocida")
        if body.armadura and body.armadura not in nombres_inv \
                and body.armadura != char.armadura:
            raise HTTPException(400, f"No tenés {body.armadura}")
        char.armadura = body.armadura or None
    if body.escudo is not None:
        char.escudo = body.escudo
    await db.commit()
    from engine.rules import calcular_ca
    return {"ok": True, "arma": char.arma_equipada,
            "armadura": char.armadura, "escudo": char.escudo,
            "ca": calcular_ca(hidratar_personaje(char))}


class DarObjeto(BaseModel):
    a_character_id: int
    nombre: str
    cantidad: int = 1


@router.post("/inventory/give")
async def dar_objeto(campaign_id: int, body: DarObjeto,
                     player: Player = Depends(jugador_actual),
                     db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    destino = await db.get(Character, body.a_character_id)
    if destino is None or destino.campaign_id != campaign_id or not destino.vivo:
        raise HTTPException(404, "Destinatario inválido")
    inv = list(char.inventario)
    item = next((x for x in inv if x.get("nombre") == body.nombre), None)
    if item is None or item.get("cantidad", 0) < body.cantidad:
        raise HTTPException(400, f"No tenés {body.cantidad}x {body.nombre}")
    item["cantidad"] -= body.cantidad
    char.inventario = [x for x in inv if x.get("cantidad", 0) > 0]
    inv2 = list(destino.inventario)
    ex = next((x for x in inv2 if x.get("nombre") == body.nombre), None)
    if ex:
        ex["cantidad"] = ex.get("cantidad", 1) + body.cantidad
    else:
        inv2.append({"nombre": body.nombre, "cantidad": body.cantidad})
    destino.inventario = inv2
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🎒 {char.nombre} le da {body.cantidad}x {body.nombre} a "
         f"{destino.nombre}.")
    await db.commit()
    return {"ok": True}


# ================================================================ nivel

class SubirNivel(BaseModel):
    metodo: str = "fijo"   # "fijo" (mitad+1) | "tirar"


@router.post("/level-up")
async def subir_nivel(campaign_id: int, body: SubirNivel,
                      player: Player = Depends(jugador_actual),
                      db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    objetivo = nivel_por_xp(char.xp)
    if objetivo <= char.nivel:
        raise HTTPException(400, f"Todavía no tenés XP para subir "
                                 f"(nivel {char.nivel}, {char.xp} XP)")
    char.nivel += 1  # de a un nivel por vez, como el prompt original
    caras = int(char.dado_golpe[1:])
    con = mod(char.atributos["CON"])
    if body.metodo == "tirar":
        d = roll(f"1{char.dado_golpe}")
        ganancia = max(1, d["dados"][0] + con)
        detalle = {"metodo": "tirar", "dado": d["dados"][0]}
    else:
        ganancia = max(1, (caras // 2 + 1) + con)
        detalle = {"metodo": "fijo", "valor": caras // 2 + 1}
    char.pg_max += ganancia
    char.pg_actual += ganancia
    char.dados_golpe_disp = min(char.nivel, char.dados_golpe_disp + 1)

    # recalcular slots preservando los gastados
    nuevos = slots_iniciales(char.clase, char.nivel)
    for nv, s in nuevos.items():
        usados_previos = char.slots.get(nv, {}).get("usados", 0)
        s["usados"] = min(usados_previos, s["max"])
    char.slots = nuevos

    _msg(db, campaign_id, "sistema", "Sistema",
         f"⭐ {char.nombre} sube a nivel {char.nivel} (+{ganancia} PG máx).")
    _roll(db, campaign_id, {"tipo": "subida_nivel", "nivel": char.nivel,
                            "pg_ganados": ganancia, **detalle}, char.id)
    await db.commit()
    return {"nivel": char.nivel, "pg_ganados": ganancia,
            "pg_max": char.pg_max, "slots": char.slots, **detalle}


# ================================================================ estado

@router.get("/state")
async def estado_mundo(campaign_id: int,
                       player: Player = Depends(jugador_actual),
                       db: AsyncSession = Depends(get_db)):
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    camp = await db.get(Campaign, campaign_id)
    quests = (await db.execute(select(Quest).where(
        Quest.campaign_id == campaign_id))).scalars().all()
    npcs = (await db.execute(select(NPC).where(
        NPC.campaign_id == campaign_id, NPC.tipo == "personaje"))).scalars().all()
    cons = (await db.execute(select(PendingConsequence).where(
        PendingConsequence.campaign_id == campaign_id,
        PendingConsequence.resuelta == False))).scalars().all()  # noqa: E712
    return {
        "estado": camp.estado, "ubicacion": camp.ubicacion_actual,
        "tiempo_juego_min": camp.tiempo_juego_min,
        "resumen": camp.resumen_actual,
        "quests": [{"id": q.id, "titulo": q.titulo, "descripcion": q.descripcion,
                    "estado": q.estado, "principal": q.principal,
                    "npc_origen_id": q.npc_origen_id} for q in quests],
        "npcs_conocidos": [{"id": n.id, "nombre": n.nombre, "rol": n.rol,
                            "actitud": n.actitud, "en_escena": n.en_escena}
                           for n in npcs],
        "consecuencias_pendientes": len(cons),
    }
