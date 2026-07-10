"""Acciones de juego — paso 3.

Flujo de toda acción:
  validar → hidratar → motor → persistir → contexto → narrar →
  aplicar efectos del LLM → resumen rodante si corresponde → responder.

Los turnos de monstruos usan IA simple del servidor (0 tokens). El LLM
controla el mundo narrativo vía contrato JSON (effects.py).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.combat import Combat
from engine.content import ARMAS, CONJUROS, MONSTRUOS, XP_POR_CR, CLASES
from engine.dice import roll
from engine.rules import (ataque_magico, cd_salvacion_magica,
                          check_concentracion, curar, gastar_slot, mod,
                          nivel_por_xp, puede_lanzar, resolver_ataque,
                          salvacion_muerte, tirada_habilidad,
                          tirada_salvacion)

from ..context import actualizar_resumen_si_corresponde, construir_contexto
from ..db import get_db
from ..deps import jugador_actual
from ..effects import aplicar_efectos
from ..hydration import (hidratar_npc, hidratar_personaje, persistir_npc,
                         persistir_personaje)
from ..models import (NPC, Campaign, Character, Message, PendingConsequence,
                      Player, Quest, Roll)
from ..narrator import narrar

router = APIRouter(prefix="/api/campaigns/{campaign_id}", tags=["actions"])


# ================================================================ helpers

async def _mi_personaje(campaign_id: int, player: Player,
                        db: AsyncSession) -> Character:
    if player.campaign_id != campaign_id:
        raise HTTPException(403, "No pertenecés a esta campaña")
    res = await db.execute(select(Character).where(Character.player_id == player.id))
    c = res.scalar_one_or_none()
    if c is None:
        raise HTTPException(400, "Todavía no creaste un personaje")
    if not c.vivo:
        raise HTTPException(400, "Tu personaje está muerto")
    return c


def _msg(db, campaign_id, autor, autor_nombre, contenido):
    db.add(Message(campaign_id=campaign_id, autor=autor,
                   autor_nombre=autor_nombre, contenido=contenido))


def _roll(db, campaign_id, resolucion, character_id=None):
    db.add(Roll(campaign_id=campaign_id, character_id=character_id,
                resolucion=resolucion))


async def _pipeline_narrativo(db: AsyncSession, camp: Campaign,
                              accion: str) -> tuple[str, dict]:
    """Contexto → narrar → aplicar efectos → resumen. Devuelve (narración, log)."""
    contexto = await construir_contexto(db, camp)
    narracion, efectos = await narrar(contexto, accion)
    log = await aplicar_efectos(db, camp, efectos)
    _msg(db, camp.id, "dm", "DM", narracion)

    # si el LLM inició combate, lo ejecutamos
    if log.get("inicia_combate"):
        resultado = await _iniciar_combate(db, camp, log["inicia_combate"])
        log["combate"] = resultado

    await actualizar_resumen_si_corresponde(db, camp)
    return narracion, log


# ================================================================ narrativa

class AccionNarrativa(BaseModel):
    texto: str


@router.post("/say")
async def accion_narrativa(campaign_id: int, body: AccionNarrativa,
                           player: Player = Depends(jugador_actual),
                           db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "Estás en combate: usá attack o cast")
    _msg(db, campaign_id, "jugador", char.nombre, body.texto)
    narracion, log = await _pipeline_narrativo(
        db, camp, f"{char.nombre} dice/hace: {body.texto}")
    await db.commit()
    return {"narracion": narracion, "efectos": log}


class AccionHabilidad(BaseModel):
    habilidad: str
    cd: int = 12
    descripcion: str = ""


@router.post("/skill-check")
async def accion_habilidad(campaign_id: int, body: AccionHabilidad,
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
    narracion, log = await _pipeline_narrativo(
        db, camp,
        f"{char.nombre} intenta {body.habilidad} "
        f"({body.descripcion or 'sin detalle'}). "
        f"Resultado del sistema: {json.dumps(r, ensure_ascii=False)}")
    await db.commit()
    return {"resolucion": r, "narracion": narracion, "efectos": log}


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
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {**resultado, "combate": camp.combate}


async def _post_accion_combate(db: AsyncSession, camp: Campaign,
                               combate: Combat, char: Character,
                               objetivo: NPC | None) -> tuple[list, str | None]:
    """Lógica común post-acción: remover muertos, victoria/derrota, XP,
    turnos de NPC. Devuelve (eventos_npc, fin)."""
    if objetivo is not None and (objetivo.pg_actual or 0) == 0:
        combate.remover(f"npc_{objetivo.id}")

    fin = None
    if not combate.npcs_restantes():
        fin = "victoria"
        combate.activo = False
        camp.estado = "exploracion"
        camp.combate = None
        # XP automática por CR, dividida entre PJs vivos
        res = await db.execute(select(NPC).where(
            NPC.campaign_id == camp.id, NPC.tipo == "monstruo",
            NPC.vivo == False, NPC.en_escena == False))  # noqa: E712
        xp_total = sum(XP_POR_CR.get((n.stats or {}).get("cr", "0"), 10)
                       for n in res.scalars().all() if n.pg_actual == 0)
        res = await db.execute(select(Character).where(
            Character.campaign_id == camp.id, Character.vivo == True))  # noqa: E712
        vivos = res.scalars().all()
        if vivos and xp_total:
            porcada = max(1, xp_total // len(vivos))
            for c in vivos:
                c.xp += porcada
                if nivel_por_xp(c.xp) > c.nivel:
                    _msg(db, camp.id, "sistema", "Sistema",
                         f"⭐ {c.nombre} tiene XP para subir a nivel "
                         f"{nivel_por_xp(c.xp)} (subida manual pendiente)")
            _msg(db, camp.id, "sistema", "Sistema",
                 f"⚔️ Victoria. +{porcada} XP para cada personaje vivo.")
        # limpiar cadáveres de la escena para próximos combates
        res = await db.execute(select(NPC).where(
            NPC.campaign_id == camp.id, NPC.tipo == "monstruo",
            NPC.pg_actual == 0))
        for n in res.scalars().all():
            n.en_escena = False
    else:
        combate.avanzar_turno()

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
async def atacar(campaign_id: int, body: Atacar,
                 player: Player = Depends(jugador_actual),
                 db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, f"No es tu turno. Turno actual: "
                                 f"{combate.turno_actual['id']}")
    if not char.arma_equipada:
        raise HTTPException(400, "No tenés arma equipada")
    npc = await db.get(NPC, body.objetivo_npc_id)
    if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
        raise HTTPException(404, "Objetivo inválido o ya está fuera de combate")

    cr_pj = hidratar_personaje(char)
    cr_npc = hidratar_npc(npc)
    r = resolver_ataque(cr_pj, cr_npc, ARMAS[char.arma_equipada],
                        dos_manos=body.dos_manos)
    persistir_personaje(cr_pj, char)
    persistir_npc(cr_npc, npc)
    _msg(db, campaign_id, "jugador", char.nombre, f"[ataque] contra {npc.nombre}")
    _roll(db, campaign_id, r, char.id)

    eventos, fin = await _post_accion_combate(db, camp, combate, char, npc)
    await db.commit()

    camp = await db.get(Campaign, campaign_id)
    narracion, log = await _pipeline_narrativo(
        db, camp,
        f"Ataque de {char.nombre} contra {npc.nombre}: "
        f"{json.dumps(r, ensure_ascii=False)}. "
        f"Turnos de enemigos: {json.dumps(eventos, ensure_ascii=False)}. "
        f"{('Fin del combate: ' + fin) if fin else 'El combate continúa.'}")
    await db.commit()
    return {"resolucion": r, "turnos_npc": eventos, "fin_combate": fin,
            "narracion": narracion, "combate": camp.combate}


class Lanzar(BaseModel):
    conjuro: str
    objetivo_npc_id: int | None = None
    objetivo_character_id: int | None = None
    nivel_slot: int | None = None      # None → nivel base del conjuro


@router.post("/combat/cast")
async def lanzar_conjuro(campaign_id: int, body: Lanzar,
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

    cr_pj = hidratar_personaje(char)
    val = puede_lanzar(cr_pj, body.conjuro)
    if not val["ok"]:
        raise HTTPException(400, f"No podés lanzarlo: {val['motivo']}")

    # gasto de slot ANTES de resolver (regla 5e: falla → slot igual gastado)
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

    tipo = conjuro["resolucion"]
    if tipo == "ataque":
        npc = await db.get(NPC, body.objetivo_npc_id or -1)
        if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = npc.nombre
        cr_npc = hidratar_npc(npc)
        r = ataque_magico(cr_pj, cr_npc, atributo,
                          conjuro["danio"], conjuro["tipo_danio"])
        resoluciones.append(r)
        persistir_npc(cr_npc, npc)

    elif tipo == "salvacion":
        npc = await db.get(NPC, body.objetivo_npc_id or -1)
        if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = npc.nombre
        cr_npc = hidratar_npc(npc)
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
                                     "final": final, "efectos": ev["eventos"]})
        elif not salv["exito"]:
            # conjuro de condición (inmovilizar, hechizar): aplica la condición
            cond = body.conjuro
            cr_npc.condiciones.append({"tipo": "paralizado"
                                       if "inmovilizar" in cond else "hechizado",
                                       "origen": cond})
            resoluciones.append({"tipo": "condicion_aplicada", "conjuro": cond})
        persistir_npc(cr_npc, npc)

    elif tipo == "curacion":
        obj = await db.get(Character, body.objetivo_character_id or char.id)
        if obj is None or obj.campaign_id != campaign_id:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = obj.nombre
        cr_obj = hidratar_personaje(obj)
        d = roll(conjuro["curacion"])
        total = d["total"] + (mod(cr_pj.atributos[atributo])
                              if conjuro.get("suma_mod_magico") else 0)
        cur = curar(cr_obj, total)
        resoluciones.append({"tipo": "curacion", **d, "total_final": total, **cur})
        persistir_personaje(cr_obj, obj)

    else:  # auto (proyectil mágico, escudo, bendecir...)
        if conjuro.get("danio") and conjuro.get("proyectiles"):
            npc = await db.get(NPC, body.objetivo_npc_id or -1)
            if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
                raise HTTPException(404, "Objetivo inválido")
            objetivo_nombre = npc.nombre
            cr_npc = hidratar_npc(npc)
            from engine.rules import aplicar_danio
            total = 0
            dados = []
            for _ in range(conjuro["proyectiles"]):
                d = roll(conjuro["danio"])
                dados.append(d["dados"])
                total += d["total"]
            ev = aplicar_danio(cr_npc, total)
            resoluciones.append({"tipo": "danio_auto", "dados": dados,
                                 "total_final": total, "efectos": ev["eventos"]})
            persistir_npc(cr_npc, npc)
        else:
            resoluciones.append({"tipo": "efecto_auto",
                                 "efecto": conjuro.get("efecto", body.conjuro)})

    # concentración: lanzar uno nuevo cancela el anterior
    if conjuro.get("concentracion"):
        cr_pj.spell_state.concentracion_activa = {
            "hechizo": body.conjuro, "desde_ronda": combate.ronda}

    persistir_personaje(cr_pj, char)
    _msg(db, campaign_id, "jugador", char.nombre,
         f"[conjuro] {body.conjuro}" +
         (f" contra {objetivo_nombre}" if objetivo_nombre else ""))
    for r in resoluciones:
        _roll(db, campaign_id, r, char.id)

    npc_obj = npc if tipo in ("ataque", "salvacion") or \
        (tipo == "auto" and conjuro.get("proyectiles")) else None
    eventos, fin = await _post_accion_combate(db, camp, combate, char, npc_obj)
    await db.commit()

    camp = await db.get(Campaign, campaign_id)
    narracion, log = await _pipeline_narrativo(
        db, camp,
        f"{char.nombre} lanza {body.conjuro}"
        f"{' contra ' + objetivo_nombre if objetivo_nombre else ''}. "
        f"Resultados: {json.dumps(resoluciones, ensure_ascii=False)}. "
        f"Turnos de enemigos: {json.dumps(eventos, ensure_ascii=False)}. "
        f"{('Fin del combate: ' + fin) if fin else ''}")
    await db.commit()
    return {"resoluciones": resoluciones, "gasto_slot": gasto,
            "turnos_npc": eventos, "fin_combate": fin,
            "narracion": narracion, "combate": camp.combate}


async def _resolver_turnos_npc(db: AsyncSession, camp: Campaign) -> list[dict]:
    """IA simple del servidor: monstruos atacan al PJ con menos PG.
    Salvaciones de muerte automáticas para PJs a 0."""
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
                break
            cr = hidratar_personaje(char)
            r = salvacion_muerte(cr)
            persistir_personaje(cr, char)
            eventos.append({"actor": char.nombre, "salvacion_muerte": r})
            _roll(db, camp.id, r, char.id)
            if r["evento"] == "muerte":
                _msg(db, camp.id, "sistema", "Sistema", f"💀 {char.nombre} ha muerto.")
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

    camp.combate = combate.to_dict() if combate.activo else None
    return eventos


# ================================================================ estado

@router.get("/state")
async def estado_mundo(campaign_id: int,
                       player: Player = Depends(jugador_actual),
                       db: AsyncSession = Depends(get_db)):
    """Quests, NPCs conocidos y consecuencias — el '!misiones'/'!lore' del
    prompt original, ahora con precisión de DB."""
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
