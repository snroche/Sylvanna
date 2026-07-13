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


def _bitacora(camp: Campaign, linea: str):
    """Anota un hecho de la ronda de combate en curso (reasignar la lista para
    que SQLAlchemy detecte el cambio en la columna JSON)."""
    b = list(camp.bitacora_combate or [])
    b.append(linea)
    camp.bitacora_combate = b


async def _cerrar_combate(db: AsyncSession, camp: Campaign):
    """Limpieza al terminar el combate: caen la furia, el arma sagrada y la
    concentración de conjuros de TODOS los personajes de la campaña."""
    res = await db.execute(select(Character).where(
        Character.campaign_id == camp.id))
    for c in res.scalars().all():
        if any(x.get("tipo") in ("furia", "arma_sagrada") for x in c.condiciones):
            c.condiciones = [x for x in c.condiciones
                             if x.get("tipo") not in ("furia", "arma_sagrada")]
        if c.concentracion:
            c.concentracion = None


def _narrar_fin_de_ronda(bg: BackgroundTasks, camp: Campaign,
                         ronda_antes: int, fin: str | None) -> bool:
    """El DM narra UNA sola vez por ronda (o al terminar el combate), no tras
    cada ataque. Vuelca la bitácora acumulada y la limpia. Devuelve si narró."""
    activo = camp.combate is not None
    ronda_ahora = camp.combate["ronda"] if activo else ronda_antes
    cierra_ronda = (not activo) or (ronda_ahora > ronda_antes) or bool(fin)
    if not cierra_ronda:
        return False
    lineas = list(camp.bitacora_combate or [])
    if not lineas:
        return False
    if fin:
        cierre = f"El combate termina ({fin})."
    else:
        cierre = f"Termina la ronda {ronda_antes} del combate."
    encolar_narracion(
        bg, camp,
        f"[COMBATE] {cierre} Narrá en prosa, de forma cinematográfica, TODO lo "
        f"que ocurrió esta ronda. No vuelvas a tirar dados ni cambies los "
        f"resultados; respetá exactamente lo que dice la bitácora:\n"
        + "\n".join(lineas),
        None)
    camp.bitacora_combate = []
    return True


def _quitar_esquivando(char: Character):
    char.condiciones = [c for c in char.condiciones
                        if c.get("tipo") != "esquivando"]


def _inicio_de_turno(char: Character):
    """Inicio del turno del PJ: expiran esquivando/ya_ataco, se levanta si
    estaba derribado, y las condiciones con duración descuentan una ronda."""
    from engine.rules import tick_condiciones
    cr_tmp = hidratar_personaje(char)
    tick_condiciones(cr_tmp)
    char.condiciones = [c for c in cr_tmp.condiciones
                        if c.get("tipo") not in ("esquivando", "ya_ataco",
                                                 "ataques_hechos", "derribado",
                                                 "imprudente", "off_usada",
                                                 "reaccion_usada",
                                                 "furtivo_usado")]


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
            from ..narrator import NarradorError
            print(f"[narrador-bg] error: {e}")
            if isinstance(e, NarradorError):
                detalle = e.mensaje_humano()
            else:
                detalle = f"error interno del narrador ({type(e).__name__})"
            _msg(db, campaign_id, "sistema", "Sistema",
                 f"⚠ El DM no pudo narrar: {detalle} "
                 f"La mecánica ya está aplicada; pueden continuar.")
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
        _inicio_de_turno(char)
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
    entre_jugadores: bool = False    # True: charla de party, el DM no interviene


@router.post("/say")
async def accion_narrativa(campaign_id: int, body: AccionNarrativa,
                           bg: BackgroundTasks,
                           player: Player = Depends(jugador_actual),
                           db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if body.entre_jugadores:
        # canal de party: se registra (y el DM lo ve en su contexto como
        # charla entre jugadores) pero NO dispara narración
        _msg(db, campaign_id, "party", char.nombre, body.texto)
        await db.commit()
        return {"ok": True, "narrando": False}
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

    # ¿Este PJ está respondiendo un pedido de tirada del DM? Si es así, usa la
    # CD que fijó el DM (no la 12 por defecto).
    pend = list(camp.tiradas_pendientes or [])
    match = next((p for p in pend
                  if char.id in p.get("pendientes", [])
                  and p.get("habilidad") == body.habilidad), None)
    cd = match["cd"] if match else body.cd

    r = tirada_habilidad(cr, body.habilidad, cd)
    persistir_personaje(cr, char)
    _msg(db, campaign_id, "jugador", char.nombre,
         f"[{body.habilidad}] {body.descripcion}")
    exito = "✓ éxito" if r["exito"] else "✗ fallo"
    detalle_insp = f" +{r['inspiracion']}🎵" if r.get("inspiracion") else ""
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🎲 {char.nombre} — {body.habilidad}: d20={r['natural']} "
         f"+{r['bono']}{detalle_insp} = {r['total']} vs CD {cd} → {exito}")
    _roll(db, campaign_id, r, char.id)

    if match:
        # registrar la tirada; recién narramos cuando TODOS los pedidos tiraron
        restantes = [x for x in match["pendientes"] if x != char.id]
        tiradas = match["tiradas"] + [{"nombre": char.nombre,
                                       "total": r["total"], "exito": r["exito"]}]
        nuevos_pend = []
        for p in pend:
            if p is match:
                if restantes:
                    nuevos_pend.append({**p, "pendientes": restantes,
                                        "tiradas": tiradas})
            else:
                nuevos_pend.append(p)
        camp.tiradas_pendientes = nuevos_pend
        if restantes:
            _msg(db, campaign_id, "sistema", "Sistema",
                 f"⏳ Faltan {len(restantes)} por tirar {body.habilidad} "
                 f"antes de que el DM narre.")
            await db.commit()
            return {"resolucion": r, "narrando": False,
                    "faltan": len(restantes)}
        # última tirada del pedido: el DM narra el desenlace con todas juntas
        resumen = "; ".join(f"{t['nombre']}: {t['total']} "
                            f"({'éxito' if t['exito'] else 'fallo'})"
                            for t in tiradas)
        encolar_narracion(
            bg, camp,
            f"Ya están TODAS las tiradas de {body.habilidad} (CD {cd}): "
            f"{resumen}. Narrá el desenlace para el grupo según quién superó la "
            f"CD y quién no; no pidas otra tirada para esto.", char.id)
        await db.commit()
        return {"resolucion": r, "narrando": True, "tiradas": tiradas}

    # tirada suelta (sin pedido del DM): se narra al toque
    encolar_narracion(
        bg, camp,
        f"{char.nombre} intenta {body.habilidad} "
        f"({body.descripcion or 'sin detalle'}) contra CD {cd}. "
        f"Resultado del sistema: {json.dumps(r, ensure_ascii=False)}",
        char.id)
    await db.commit()
    return {"resolucion": r, "narrando": True}


class TiradaSalvacion(BaseModel):
    atributo: str            # FUE | DES | CON | INT | SAB | CAR
    cd: int = 12
    descripcion: str = ""


@router.post("/saving-throw")
async def tirada_de_salvacion(campaign_id: int, body: TiradaSalvacion,
                              bg: BackgroundTasks,
                              player: Player = Depends(jugador_actual),
                              db: AsyncSession = Depends(get_db)):
    """Tirada de salvación (d20 + mod de atributo + BC si tenés competencia en
    esa salvación). La CD la fija el mundo/DM."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    atr = (body.atributo or "").upper()
    if atr not in ("FUE", "DES", "CON", "INT", "SAB", "CAR"):
        raise HTTPException(400, "Atributo inválido (FUE/DES/CON/INT/SAB/CAR)")
    cr = hidratar_personaje(char)
    r = tirada_salvacion(cr, atr, body.cd)
    persistir_personaje(cr, char)
    competente = atr in char.competencias.get("salvaciones", [])
    _msg(db, campaign_id, "jugador", char.nombre,
         f"[salvación de {atr}] {body.descripcion}")
    exito = "✓ éxito" if r["exito"] else "✗ fallo"
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🛡🎲 {char.nombre} — salvación de {atr}"
         f"{' (competente)' if competente else ''}: d20={r.get('natural')} "
         f"+{r.get('bono')} = {r.get('total')} vs CD {body.cd} → {exito}")
    _roll(db, campaign_id, r, char.id)
    encolar_narracion(
        bg, camp,
        f"{char.nombre} hace una tirada de salvación de {atr} "
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
    camp.bitacora_combate = []   # arranca la bitácora de la ronda 1
    _msg(db, camp.id, "sistema", "Sistema",
         f"⚔️ Combate iniciado. Orden: {[e['id'] for e in combate.orden]}")
    _roll(db, camp.id, {"tipo": "inicio_combate",
                        "iniciativas": combate.tiradas_iniciativa})
    eventos = await _resolver_turnos_npc(db, camp)
    # los turnos enemigos de apertura ya se cuentan en la narración de inicio;
    # que no se repitan al cerrar la ronda 1.
    camp.bitacora_combate = []
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
        await _cerrar_combate(db, camp)
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
            _bitacora(camp, f"🏆 El grupo gana el combate (+{porcada} XP c/u).")
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
    castigo_slot: int | None = None   # Paladín: Castigo Divino con ese slot
    imprudente: bool = False          # Bárbaro: Ataque Temerario
    mano_secundaria: bool = False     # ataque con arma de mano secundaria
    golpe_aturdidor: bool = False     # Monje: Golpe Aturdidor (1 ki)


@router.post("/combat/attack")
async def atacar(campaign_id: int, body: Atacar, bg: BackgroundTasks,
                 player: Player = Depends(jugador_actual),
                 db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    ronda_antes = combate.ronda
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
    arma = ARMAS[char.arma_equipada]

    # Ataque Temerario (Bárbaro nv2+): ventaja al atacar melé; a cambio, los
    # ataques contra el bárbaro tienen ventaja hasta el inicio de su turno.
    imprudente = False
    if body.imprudente:
        if char.clase != "barbaro" or char.nivel < 2:
            raise HTTPException(400, "El Ataque Temerario es del Bárbaro (nivel 2+)")
        if arma.distancia:
            raise HTTPException(400, "El Ataque Temerario es solo cuerpo a cuerpo")
        imprudente = True

    # Combate con Dos Armas: el ataque de mano secundaria es una acción adicional
    # (declaralo ANTES del ataque principal que cierra el turno). Requiere ligera.
    if body.mano_secundaria:
        if not arma.ligera:
            raise HTTPException(400, "El ataque de mano secundaria requiere un "
                                     "arma ligera")
        if any(c.get("tipo") == "off_usada" for c in char.condiciones):
            raise HTTPException(400, "Ya usaste tu ataque de mano secundaria "
                                     "este turno")

    # Castigo Divino (Paladín): gasta un espacio de conjuro para +Nd8 radiante.
    # El slot se descuenta SOLO si el ataque impacta (se declara tras ver el golpe).
    smite_dados = None
    if body.castigo_slot:
        if char.clase != "paladin":
            raise HTTPException(400, "El Castigo Divino es del Paladín")
        if arma.distancia:
            raise HTTPException(400, "El Castigo Divino requiere un arma cuerpo a cuerpo")
        ss = cr_pj.spell_state
        s = ss.slots.get(str(body.castigo_slot)) if ss else None
        if not s or s["usados"] >= s["max"]:
            raise HTTPException(400, "Sin espacio de conjuro para el Castigo Divino")
        from engine.rules import dados_castigo_divino
        smite_dados = dados_castigo_divino(body.castigo_slot, cr_npc)

    # Ataque furtivo del pícaro. El motor ya lo concede si el pícaro tiene
    # VENTAJA en el ataque (objetivo derribado/apresado/aturdido, etc.). Acá
    # pasamos furtivo=True para el caso "aliado adyacente" (flanqueo v1): hay
    # otro personaje consciente en combate, o el pícaro fue ayudado.
    furtivo = False
    furtivo_usado = any(c.get("tipo") == "furtivo_usado" for c in char.condiciones)
    if char.clase == "picaro":
        res_al = await db.execute(select(Character).where(
            Character.campaign_id == campaign_id, Character.id != char.id,
            Character.vivo == True, Character.pg_actual > 0))  # noqa: E712
        furtivo = res_al.scalars().first() is not None \
            or cr_pj.tiene_condicion("ayudado")
        # Swashbuckler — Audacia Temeraria: puede hacer Ataque Furtivo en duelo
        # 1 vs 1 sin necesitar ventaja ni un aliado adyacente.
        if char.subclase == "swashbuckler":
            furtivo = True
    r = resolver_ataque(cr_pj, cr_npc, arma,
                        dos_manos=body.dos_manos, furtivo=furtivo,
                        smite_dados=smite_dados,
                        mano_secundaria=body.mano_secundaria,
                        imprudente=imprudente, furtivo_usado=furtivo_usado)
    # El Ataque Furtivo es una vez por turno: si se aplicó, marcá el turno.
    if r.get("impacta") and any(
            e.get("motivo") == "furtivo"
            for e in (r.get("danio") or {}).get("extras", [])):
        cr_pj.condiciones = [c for c in cr_pj.condiciones
                             if c.get("tipo") != "furtivo_usado"] + [
            {"tipo": "furtivo_usado", "origen": "furtivo"}]
    if smite_dados and r["impacta"]:
        gastar_slot(cr_pj, body.castigo_slot)
        r["castigo_slot"] = body.castigo_slot
    if imprudente:
        cr_pj.condiciones = [c for c in cr_pj.condiciones
                             if c.get("tipo") != "imprudente"] + [
            {"tipo": "imprudente", "origen": "temerario"}]

    # Golpe Aturdidor (Monje nv5+): al impactar melé, gasta 1 ki; el objetivo
    # hace salvación de CON (CD ki) o queda aturdido hasta tu próximo turno.
    recursos_monje = None
    if body.golpe_aturdidor:
        if char.clase != "monje" or char.nivel < 5:
            raise HTTPException(400, "El Golpe Aturdidor es del Monje (nivel 5+)")
        if arma.distancia:
            raise HTTPException(400, "El Golpe Aturdidor requiere un ataque melé")
        import copy
        recursos_monje = copy.deepcopy(char.recursos_clase or {})
        ki = recursos_monje.get("ki")
        if not ki or ki["usados"] >= ki["max"]:
            raise HTTPException(400, "Sin puntos de ki")
        if r["impacta"]:
            from engine.rules import bc, tirada_salvacion
            ki["usados"] += 1
            cd = 8 + bc(char.nivel) + mod(char.atributos["SAB"])
            salv = tirada_salvacion(cr_npc, "CON", cd)
            r["golpe_aturdidor"] = {"cd": cd, "salvacion": salv}
            if not salv["exito"]:
                cr_npc.condiciones = [c for c in cr_npc.condiciones
                                      if c.get("tipo") != "aturdido"] + [
                    {"tipo": "aturdido", "origen": "golpe_aturdidor", "rondas": 2}]
                r["golpe_aturdidor"]["aturdido"] = True
            char.recursos_clase = recursos_monje

    persistir_personaje(cr_pj, char)
    persistir_npc(cr_npc, npc)
    _msg(db, campaign_id, "jugador", char.nombre, f"[ataque] contra {npc.nombre}")
    _roll(db, campaign_id, r, char.id)

    # bitácora de la ronda: el DM la narra entera al cerrar la ronda
    if r["impacta"]:
        _dmg = (r.get("danio") or {}).get("total_final", 0)
        _extras = (r.get("danio") or {}).get("extras", [])
        _furt = " (¡ataque furtivo!)" if any(
            e.get("motivo") == "furtivo" for e in _extras) else ""
        _crit = " ¡crítico!" if r.get("critico") else ""
        _cae = f" {npc.nombre} cae." if (npc.pg_actual or 0) == 0 else ""
        _bitacora(camp, f"⚔️ {char.nombre} ataca a {npc.nombre}: impacta por "
                        f"{_dmg} de daño{_crit}{_furt}.{_cae}")
    else:
        _bitacora(camp, f"⚔️ {char.nombre} ataca a {npc.nombre}: falla.")

    from engine.content import ataques_por_accion
    tiene_oleada = any(c.get("tipo") == "oleada" for c in char.condiciones)
    off_hand = body.mano_secundaria
    ataques_max = ataques_por_accion(char.clase, char.nivel)
    hechos = next((c.get("n", 1) for c in char.condiciones
                   if c.get("tipo") == "ataques_hechos"), 0)
    # ¿quedan ataques del rasgo Ataque Extra después de éste?
    extra_pendiente = (not off_hand and not tiene_oleada
                       and (hechos + 1) < ataques_max)
    if tiene_oleada or extra_pendiente or off_hand:
        # este ataque NO consume el turno (Oleada de Acción / Ataque Extra /
        # mano secundaria como acción adicional de Combate con Dos Armas)
        if off_hand:
            char.condiciones = list(char.condiciones) + [
                {"tipo": "off_usada", "origen": "dos_armas"}]
        elif tiene_oleada:
            char.condiciones = [c for c in char.condiciones
                                if c.get("tipo") != "oleada"]
        else:
            char.condiciones = [c for c in char.condiciones
                                if c.get("tipo") != "ataques_hechos"] + [
                {"tipo": "ataques_hechos", "n": hechos + 1}]
        if (npc.pg_actual or 0) == 0:
            combate.remover(f"npc_{npc.id}")
        eventos, fin = ([], None)
        if not combate.npcs_restantes():
            eventos, fin = await _post_accion_combate(db, camp, combate, char, None)
        else:
            camp.combate = combate.to_dict()
    else:
        char.condiciones = [c for c in char.condiciones
                            if c.get("tipo") != "ataques_hechos"]
        eventos, fin = await _post_accion_combate(db, camp, combate, char, npc)
    # el DM narra una sola vez por ronda (o al terminar el combate), no tras
    # cada ataque: si la ronda no cerró, solo se acumula la bitácora.
    narrando = _narrar_fin_de_ronda(bg, camp, ronda_antes, fin)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {"resolucion": r, "turnos_npc": eventos, "fin_combate": fin,
            "narrando": narrando, "combate": camp.combate}


class Lanzar(BaseModel):
    conjuro: str
    objetivo_npc_id: int | None = None
    objetivo_character_id: int | None = None
    objetivos_npc_ids: list[int] | None = None   # conjuros de área / multiobjetivo
    nivel_slot: int | None = None
    metamagia: list[str] = []                     # hechicero


@router.post("/combat/cast")
async def lanzar_conjuro(campaign_id: int, body: Lanzar, bg: BackgroundTasks,
                         player: Player = Depends(jugador_actual),
                         db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    ronda_antes = combate.ronda
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
    # Conjuro Sutil (metamagia) evita componentes V/S, pero no el material costoso
    _verificar_componente(char, conjuro)

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

    # Metamagia (Hechicero): gasta Puntos de Hechicería y modifica la resolución.
    save_ventaja = 0     # elevado: desventaja del objetivo en su salvación
    empoderar = 0        # empoderado: cantidad de dados de daño a re-tirar
    meta_aplicadas: list[str] = []
    if body.metamagia:
        import copy
        from engine.content import METAMAGIA, costo_metamagia
        if char.clase != "hechicero":
            raise HTTPException(400, "Solo el Hechicero usa Metamagia")
        conocidas = (char.opciones_clase or {}).get("metamagia", [])
        recursos_h = copy.deepcopy(char.recursos_clase or {})
        ph = recursos_h.get("puntos_hechiceria")
        seleccion = list(dict.fromkeys(body.metamagia))
        costo_total = 0
        for mm in seleccion:
            if mm not in METAMAGIA:
                raise HTTPException(400, f"Metamagia desconocida: {mm}")
            if mm not in conocidas:
                raise HTTPException(400, f"No conocés la metamagia '{mm}'")
            costo_total += costo_metamagia(mm, conjuro["nivel"])
        if not ph or ph["pool"] < costo_total:
            raise HTTPException(400, f"Sin Puntos de Hechicería "
                                     f"({costo_total} necesarios)")
        ph["pool"] -= costo_total
        for mm in seleccion:
            if mm == "elevado":
                save_ventaja = -1
            elif mm == "empoderado":
                empoderar = max(1, mod(cr_pj.atributos[atributo]))
            meta_aplicadas.append(mm)
        char.recursos_clase = recursos_h

    # trucos escalan a nivel 5: se duplican los dados de daño
    conjuro = dict(conjuro)
    if conjuro["nivel"] == 0 and char.nivel >= 5 and conjuro.get("danio"):
        import re as _re
        conjuro["danio"] = _re.sub(
            r"^(\d+)d", lambda m: f"{int(m.group(1)) * 2}d", conjuro["danio"])

    # niveles por encima del base = upcasting
    niveles_extra = 0
    if nivel > 0:
        niveles_extra = max(0, (body.nivel_slot or nivel) - nivel)

    from engine.rules import aplicar_danio, tirar_danio_conjuro

    resoluciones: list[dict] = []
    objetivo_nombre = None
    objetivos_npc: list[NPC] = []

    tipo = conjuro["resolucion"]
    es_area = bool(conjuro.get("area"))

    if tipo == "curacion":
        obj = await db.get(Character, body.objetivo_character_id or char.id)
        if obj is None or obj.campaign_id != campaign_id:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = obj.nombre
        cr_obj = hidratar_personaje(obj) if obj.id != char.id else cr_pj
        d = tirar_danio_conjuro(conjuro["curacion"],
                                conjuro.get("escalado_curacion"), niveles_extra)
        total = d["total"] + (mod(cr_pj.atributos[atributo])
                              if conjuro.get("suma_mod_magico") else 0)
        # Discípulo de la Vida: +2 + nivel del conjuro
        if char.subclase == "dominio_de_la_vida" and conjuro["nivel"] >= 1:
            total += 2 + (body.nivel_slot or conjuro["nivel"])
        cur = curar(cr_obj, total)
        resoluciones.append({"tipo": "curacion", **d, "total_final": total, **cur})
        if obj.id != char.id:
            persistir_personaje(cr_obj, obj)

    elif tipo == "salvacion":
        cd = cd_salvacion_magica(cr_pj, atributo)
        ids = body.objetivos_npc_ids or (
            [body.objetivo_npc_id] if body.objetivo_npc_id else [])
        if not ids:
            raise HTTPException(404, "Objetivo inválido")
        if len(ids) > 1 and not es_area:
            raise HTTPException(400, "Este conjuro apunta a un solo objetivo")
        # el daño de área se tira UNA vez y se reparte (mitad en salvación exitosa)
        dmg = (tirar_danio_conjuro(conjuro["danio"], conjuro.get("escalado_danio"),
                                   niveles_extra, empoderar)
               if conjuro.get("danio") else None)
        for nid in dict.fromkeys(ids[:8]):
            t = await db.get(NPC, nid)
            if t is None or t.campaign_id != campaign_id or not t.vivo:
                resoluciones.append({"tipo": "objetivo_invalido", "npc_id": nid})
                continue
            cr_t = hidratar_npc(t)
            salv = tirada_salvacion(cr_t, conjuro["salvacion"], cd,
                                    ventaja=save_ventaja)
            salv["objetivo"] = t.nombre
            resoluciones.append(salv)
            if dmg:
                final = dmg["total"]
                if salv["exito"]:
                    final = (final // 2
                             if conjuro.get("en_salvacion_exitosa") == "mitad"
                             else 0)
                if final:
                    ev = aplicar_danio(cr_t, final)
                    resoluciones.append({"tipo": "danio_conjuro",
                                         "objetivo": t.nombre,
                                         "dados": dmg["dados"], "final": final,
                                         "tipo_danio": conjuro.get("tipo_danio"),
                                         "efectos": ev["eventos"]})
            elif not salv["exito"]:
                cond = ("paralizado" if body.conjuro == "hold_person"
                        else "hechizado")
                cr_t.condiciones.append({"tipo": cond, "origen": body.conjuro})
                resoluciones.append({"tipo": "condicion_aplicada",
                                     "objetivo": t.nombre,
                                     "conjuro": body.conjuro})
            persistir_npc(cr_t, t)
            objetivos_npc.append(t)
        objetivo_nombre = ", ".join(t.nombre for t in objetivos_npc) or None

    elif tipo == "ataque" or (tipo == "auto" and conjuro.get("proyectiles")):
        t = await db.get(NPC, body.objetivo_npc_id or -1)
        if t is None or t.campaign_id != campaign_id or not t.vivo:
            raise HTTPException(404, "Objetivo inválido")
        objetivo_nombre = t.nombre
        cr_t = hidratar_npc(t)
        if tipo == "ataque":
            # Explosión Agonizante (brujo): +mod de CAR al daño de la explosión
            bono_danio = 0
            if char.clase == "brujo" and body.conjuro == "eldritch_blast" \
                    and "explosion_agonizante" in (
                        char.opciones_clase or {}).get("invocaciones", []):
                bono_danio = max(0, mod(cr_pj.atributos[atributo]))
            r = ataque_magico(cr_pj, cr_t, atributo,
                              conjuro["danio"], conjuro["tipo_danio"],
                              bono_danio=bono_danio)
            resoluciones.append(r)
        else:  # proyectil mágico: N proyectiles automáticos (upcasting: +1 c/u)
            n_proj = conjuro["proyectiles"] + \
                conjuro.get("escalado_proyectiles", 0) * niveles_extra
            total, dados = 0, []
            for _ in range(n_proj):
                d = roll(conjuro["danio"])
                dados.append(d["dados"])
                total += d["total"]
            ev = aplicar_danio(cr_t, total)
            resoluciones.append({"tipo": "danio_auto", "proyectiles": n_proj,
                                 "dados": dados, "total_final": total,
                                 "efectos": ev["eventos"]})
        persistir_npc(cr_t, t)
        objetivos_npc.append(t)

    else:  # auto sin proyectiles (escudo, bless...)
        resoluciones.append({"tipo": "efecto_auto",
                             "efecto": conjuro.get("efecto", body.conjuro)})

    if meta_aplicadas:
        resoluciones.append({"tipo": "metamagia", "aplicadas": meta_aplicadas})

    if conjuro.get("concentracion"):
        cr_pj.spell_state.concentracion_activa = {
            "hechizo": body.conjuro, "desde_ronda": combate.ronda}

    persistir_personaje(cr_pj, char)
    _msg(db, campaign_id, "jugador", char.nombre,
         f"[conjuro] {body.conjuro}" +
         (f" contra {objetivo_nombre}" if objetivo_nombre else ""))
    for r in resoluciones:
        _roll(db, campaign_id, r, char.id)
    _bitacora(camp, f"✦ {char.nombre} lanza {body.conjuro.replace('_', ' ')}"
                    + (f" sobre {objetivo_nombre}" if objetivo_nombre else "") + ".")

    # sacar del orden a los objetivos que hayan caído (área puede matar a varios)
    for t in objetivos_npc:
        if (t.pg_actual or 0) == 0:
            combate.remover(f"npc_{t.id}")
    eventos, fin = await _post_accion_combate(db, camp, combate, char, None)
    # el DM narra una sola vez por ronda (o al terminar el combate)
    narrando = _narrar_fin_de_ronda(bg, camp, ronda_antes, fin)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {"resoluciones": resoluciones, "gasto_slot": gasto,
            "turnos_npc": eventos, "fin_combate": fin,
            "narrando": narrando, "combate": camp.combate}


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
                _inicio_de_turno(char)
                if any(c.get("tipo") in ("aturdido", "paralizado")
                       for c in char.condiciones):
                    _msg(db, camp.id, "sistema", "Sistema",
                         f"💫 {char.nombre} está incapacitado y pierde su "
                         f"turno.")
                    combate.avanzar_turno()
                    combate.turno_ts = time.time()
                    camp.combate = combate.to_dict()
                    continue
                break
            if any(c.get("tipo") == "estable" for c in char.condiciones):
                # estabilizado: no tira salvaciones de muerte, pasa el turno
                combate.avanzar_turno()
                combate.turno_ts = time.time()
                camp.combate = combate.to_dict()
                continue
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
                    await _cerrar_combate(db, camp)
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
            await _cerrar_combate(db, camp)
            eventos.append({"fin_combate": "derrota_total"})
            return eventos

        objetivo = min(objetivos, key=lambda c: c.pg_actual)
        cr_npc = hidratar_npc(npc)
        # inicio del turno del NPC: expiran duraciones y se levanta
        from engine.rules import tick_condiciones
        expiradas = tick_condiciones(cr_npc)
        cr_npc.condiciones = [c for c in cr_npc.condiciones
                              if c.get("tipo") != "derribado"]
        if any(cr_npc.tiene_condicion(t) for t in ("aturdido", "paralizado")):
            persistir_npc(cr_npc, npc)
            eventos.append({"actor": npc.nombre, "incapacitado": True})
            combate.avanzar_turno()
            continue
        persistir_npc(cr_npc, npc)
        cr_pj = hidratar_personaje(objetivo)
        # Estilo Protección: un aliado con escudo puede gastar su reacción para
        # imponer desventaja al ataque enemigo contra este objetivo.
        protector = None
        res_prot = await db.execute(select(Character).where(
            Character.campaign_id == camp.id, Character.id != objetivo.id,
            Character.vivo == True, Character.pg_actual > 0))  # noqa: E712
        for p in res_prot.scalars().all():
            if p.estilo_combate == "proteccion" and p.escudo and not any(
                    c.get("tipo") == "reaccion_usada" for c in p.condiciones):
                protector = p
                break
        prot_ventaja = -1 if protector else 0
        ataques_sb = (npc.stats or {}).get("ataques") or []
        if ataques_sb:
            from engine.rules import ataque_statblock
            a = ataques_sb[0]
            r = ataque_statblock(cr_npc, cr_pj, a["nombre"], a["bono"],
                                 a["danio"], ventaja=prot_ventaja)
        else:
            arma_nombre = (npc.stats or {}).get("armas", ["garrote"])[0]
            arma = ARMAS.get(arma_nombre, ARMAS["garrote"])
            r = resolver_ataque(cr_npc, cr_pj, arma, ventaja=prot_ventaja)
        if protector:
            protector.condiciones = list(protector.condiciones) + [
                {"tipo": "reaccion_usada", "origen": "proteccion"}]
            _msg(db, camp.id, "sistema", "Sistema",
                 f"🛡 {protector.nombre} interpone su escudo para proteger a "
                 f"{objetivo.nombre} (desventaja al ataque).")
        if "requiere_check_concentracion" in r.get("efectos", []):
            conc = check_concentracion(cr_pj, r["danio"]["total_final"])
            eventos.append({"actor": objetivo.nombre, "concentracion": conc})
            _roll(db, camp.id, conc, objetivo.id)
        persistir_personaje(cr_pj, objetivo)
        # Forma Salvaje: si la bestia cae a 0 PG, el druida revierte (no queda
        # inconsciente) en vez de morir.
        if objetivo.pg_actual == 0 and \
                (objetivo.recursos_clase or {}).get("_forma_salvaje"):
            _revertir_forma_salvaje(objetivo)
            eventos.append({"actor": objetivo.nombre, "revierte_forma": True})
            _msg(db, camp.id, "sistema", "Sistema",
                 f"✨ La forma salvaje de {objetivo.nombre} se deshace por el "
                 f"daño; vuelve a su forma natural.")
        persistir_npc(cr_npc, npc)
        eventos.append({"actor": npc.nombre, "ataque": r,
                        "objetivo": objetivo.nombre})
        _roll(db, camp.id, r)
        # log visible del ataque enemigo (para que los jugadores lo vean al
        # instante) + bitácora para que el DM lo narre al cerrar la ronda.
        nombre_ataque = r.get("arma") or "ataque"
        if r.get("impacta"):
            dmg = (r.get("danio") or {}).get("total_final", 0)
            crit = " ¡crítico!" if r.get("critico") else ""
            linea = (f"🗡️ {npc.nombre} ataca a {objetivo.nombre} "
                     f"({nombre_ataque}): impacta por {dmg} de daño{crit}.")
            if objetivo.pg_actual == 0:
                linea += f" {objetivo.nombre} cae."
        else:
            linea = (f"🗡️ {npc.nombre} ataca a {objetivo.nombre} "
                     f"({nombre_ataque}): falla.")
        _msg(db, camp.id, "sistema", "Sistema", linea)
        _bitacora(camp, linea)
        combate.avanzar_turno()

    combate.turno_ts = time.time()
    camp.combate = combate.to_dict() if combate.activo else None
    return eventos


# ================================================================ deshacer / regenerar

def _es_marcador(m) -> bool:
    return m.autor == "sistema" and m.contenido[:1] in ("↺", "⌫")


def _par_narrativo(msgs: list):
    """Devuelve (accion, dm) si el final del log es jugador→dm (ignorando
    nuestros marcadores ↺/⌫), o None si hay mecánica en el medio."""
    limpio = [m for m in msgs if not _es_marcador(m)]
    if len(limpio) >= 2 and limpio[-1].autor == "dm" \
            and limpio[-2].autor == "jugador":
        return limpio[-2], limpio[-1]
    return None


async def _ultimos_mensajes(db, campaign_id, n=6):
    res = await db.execute(
        select(Message).where(Message.campaign_id == campaign_id)
        .order_by(Message.id.desc()).limit(n))
    return list(reversed(res.scalars().all()))


@router.post("/narration/regenerate")
async def regenerar_narracion(campaign_id: int, bg: BackgroundTasks,
                              player: Player = Depends(jugador_actual),
                              db: AsyncSession = Depends(get_db)):
    """Borra la última respuesta del DM y vuelve a narrar la misma acción.
    Solo si el final del log es (acción de jugador → dm), sin mecánica en
    el medio: las tiradas y el combate no se re-tiran."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.narrando:
        raise HTTPException(409, "El DM está narrando: esperá")
    if camp.estado == "combate":
        raise HTTPException(409, "No se regenera narración en combate")
    msgs = await _ultimos_mensajes(db, campaign_id)
    par = _par_narrativo(msgs)
    if par is None:
        raise HTTPException(409, "Solo se puede regenerar la respuesta a una "
                                 "acción narrativa simple (sin tiradas ni "
                                 "mecánica en el medio)")
    accion, dm = par
    await db.delete(dm)
    _msg(db, campaign_id, "sistema", "Sistema",
         f"↺ {char.nombre} pidió regenerar la última narración.")
    encolar_narracion(bg, camp,
                      f"{accion.autor_nombre} dice/hace: {accion.contenido} "
                      f"(REGENERACIÓN: narrá esta acción de nuevo, distinto "
                      f"al intento anterior)", char.id)
    await db.commit()
    return {"ok": True, "narrando": True}


@router.post("/narration/undo")
async def deshacer_accion(campaign_id: int,
                          player: Player = Depends(jugador_actual),
                          db: AsyncSession = Depends(get_db)):
    """Borra el último par (acción del jugador → respuesta del DM).
    Mismas restricciones que regenerate. Los efectos ya aplicados por esa
    narración (XP, loot) no se revierten: es un deshacer de conversación."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.narrando:
        raise HTTPException(409, "El DM está narrando: esperá")
    if camp.estado == "combate":
        raise HTTPException(409, "No se deshace en combate")
    msgs = await _ultimos_mensajes(db, campaign_id)
    par = _par_narrativo(msgs)
    if par is None:
        raise HTTPException(409, "Solo se puede deshacer un par acción→"
                                 "narración simple")
    accion, dm = par
    await db.delete(dm)
    await db.delete(accion)
    _msg(db, campaign_id, "sistema", "Sistema",
         f"⌫ {char.nombre} deshizo la última acción.")
    await db.commit()
    return {"ok": True}


# ================================================================ typing

@router.post("/typing")
async def escribiendo(campaign_id: int,
                      player: Player = Depends(jugador_actual),
                      db: AsyncSession = Depends(get_db)):
    """Heartbeat liviano: 'este jugador está tipeando'. El cliente lo manda
    cada ~3s mientras el input tiene texto; expira solo a los 6s."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    t = dict(camp.typing or {})
    t[char.nombre] = time.time()
    # limpiar vencidos para que el JSON no crezca
    camp.typing = {k: v for k, v in t.items() if time.time() - v < 10}
    await db.commit()
    return {"ok": True}


# ================================================================ habilidades de clase

class UsarHabilidadClase(BaseModel):
    nombre: str
    objetivo_character_id: int | None = None
    objetivo_npc_id: int | None = None   # aliento de dragón
    cantidad: int | None = None      # imposición de manos: cuántos PG del pool


@router.post("/class-ability")
async def habilidad_clase(campaign_id: int, body: UsarHabilidadClase,
                          player: Player = Depends(jugador_actual),
                          db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    import copy
    recursos = copy.deepcopy(char.recursos_clase or {})
    rec = recursos.get(body.nombre)
    if rec is None:
        raise HTTPException(400, f"Tu clase no tiene '{body.nombre}' (o no al "
                                 f"nivel {char.nivel})")

    en_combate = camp.estado == "combate" and camp.combate
    if en_combate:
        combate = Combat.from_dict(camp.combate)
        if not combate.es_turno_de(f"pj_{char.id}"):
            raise HTTPException(409, "En combate, solo en tu turno")

    resultado: dict = {"habilidad": body.nombre}

    if body.nombre == "furia":
        if not en_combate:
            raise HTTPException(409, "La furia se activa en combate")
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Sin usos de furia hasta descansar")
        if any(c.get("tipo") == "furia" for c in char.condiciones):
            raise HTTPException(409, "Ya estás en furia")
        rec["usados"] += 1
        char.condiciones = list(char.condiciones) + [
            {"tipo": "furia", "origen": "clase"}]
        resultado["efecto"] = "+2 daño melé hasta que termine el combate"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"💢 {char.nombre} entra en FURIA.")

    elif body.nombre == "nuevo_aliento":
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Ya usaste Nuevo Aliento (descanso corto)")
        rec["usados"] += 1
        cr = hidratar_personaje(char)
        d = roll("1d10")
        cur = curar(cr, d["total"] + char.nivel)
        persistir_personaje(cr, char)
        resultado.update({"tipo": "curacion", **d, "curado": cur["curado"],
                          "pg_actual": char.pg_actual})
        _msg(db, campaign_id, "sistema", "Sistema",
             f"❤️ {char.nombre} usa Nuevo Aliento: +{cur['curado']} PG.")

    elif body.nombre == "oleada_de_accion":
        if not en_combate:
            raise HTTPException(409, "Solo en combate")
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Ya usaste Oleada de Acción")
        rec["usados"] += 1
        char.condiciones = list(char.condiciones) + [
            {"tipo": "oleada", "origen": "clase"}]
        resultado["efecto"] = "tu próximo ataque este turno no consume el turno"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"⚡ {char.nombre} usa Oleada de Acción: ¡ataca dos veces!")

    elif body.nombre == "canalizar_divinidad":
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Sin usos (descanso corto)")
        obj = await db.get(Character, body.objetivo_character_id or char.id)
        if obj is None or obj.campaign_id != campaign_id or not obj.vivo:
            raise HTTPException(404, "Objetivo inválido")
        rec["usados"] += 1
        cr_o = hidratar_personaje(obj)
        cur = curar(cr_o, 5 * char.nivel)
        persistir_personaje(cr_o, obj)
        resultado.update({"tipo": "curacion", "curado": cur["curado"],
                          "objetivo": obj.nombre})
        _msg(db, campaign_id, "sistema", "Sistema",
             f"✝️ {char.nombre} canaliza divinidad: {obj.nombre} +{cur['curado']} PG.")

    elif body.nombre == "imposicion_de_manos":
        cant = body.cantidad or 0
        if cant <= 0 or cant > rec.get("pool", 0):
            raise HTTPException(400, f"Cantidad inválida (pool: {rec.get('pool', 0)})")
        obj = await db.get(Character, body.objetivo_character_id or char.id)
        if obj is None or obj.campaign_id != campaign_id or not obj.vivo:
            raise HTTPException(404, "Objetivo inválido")
        rec["pool"] -= cant
        cr_o = hidratar_personaje(obj)
        cur = curar(cr_o, cant)
        persistir_personaje(cr_o, obj)
        resultado.update({"tipo": "curacion", "curado": cur["curado"],
                          "objetivo": obj.nombre, "pool_restante": rec["pool"]})
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🙏 {char.nombre} impone manos: {obj.nombre} +{cur['curado']} PG.")

    elif body.nombre == "inspiracion_bardica":
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Sin inspiraciones hasta descanso largo")
        obj = await db.get(Character, body.objetivo_character_id or -1)
        if obj is None or obj.campaign_id != campaign_id or not obj.vivo \
                or obj.id == char.id:
            raise HTTPException(404, "Elegí a un aliado (no a vos)")
        rec["usados"] += 1
        dado_insp = "1d8" if char.nivel >= 5 else "1d6"
        obj.condiciones = list(obj.condiciones) + [
            {"tipo": "inspirado", "origen": char.nombre, "dado": dado_insp}]
        resultado["efecto"] = f"{obj.nombre} suma {dado_insp} a su próxima tirada"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🎵 {char.nombre} inspira a {obj.nombre} (+1d6 próxima tirada).")

    elif body.nombre == "rafaga_de_golpes":
        if not en_combate:
            raise HTTPException(409, "Solo en combate")
        ki = recursos.get("ki")
        if not ki or ki["usados"] >= ki["max"]:
            raise HTTPException(400, "Sin puntos de ki (descanso corto)")
        ki["usados"] += 1
        char.condiciones = list(char.condiciones) + [
            {"tipo": "oleada", "origen": "ki"}]
        resultado["efecto"] = "un ataque extra este turno"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"👊 {char.nombre} desata una ráfaga de golpes.")

    elif body.nombre == "defensa_paciente":
        if not en_combate:
            raise HTTPException(409, "Solo en combate")
        ki = recursos.get("ki")
        if not ki or ki["usados"] >= ki["max"]:
            raise HTTPException(400, "Sin puntos de ki")
        ki["usados"] += 1
        _quitar_esquivando(char)
        char.condiciones = list(char.condiciones) + [
            {"tipo": "esquivando", "origen": "ki"}]
        resultado["efecto"] = "esquivás sin perder el turno"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🧘 {char.nombre} adopta defensa paciente (y aún puede actuar).")

    elif body.nombre == "frenesi":
        if not en_combate:
            raise HTTPException(409, "Solo en combate")
        if char.subclase != "senda_del_berserker" or char.nivel < 3:
            raise HTTPException(400, "Requiere Berserker nivel 3")
        if not any(c.get("tipo") == "furia" for c in char.condiciones):
            raise HTTPException(409, "El frenesí requiere estar en furia")
        if any(c.get("tipo") == "oleada" for c in char.condiciones):
            raise HTTPException(409, "Ya tenés un ataque extra pendiente")
        char.condiciones = list(char.condiciones) + [
            {"tipo": "oleada", "origen": "frenesi"}]
        resultado["efecto"] = "un ataque extra este turno (frenesí)"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🔥 {char.nombre} entra en frenesí.")

    elif body.nombre == "arma_sagrada":
        if char.subclase != "juramento_de_devocion" or char.nivel < 3:
            raise HTTPException(400, "Requiere Juramento de Devoción nivel 3")
        cd_rec = recursos.get("canalizar_divinidad")
        if not cd_rec or cd_rec["usados"] >= cd_rec["max"]:
            raise HTTPException(400, "Sin usos de Canalizar (descanso corto)")
        cd_rec["usados"] += 1
        valor = max(1, mod(char.atributos["CAR"]))
        char.condiciones = [c for c in char.condiciones
                            if c.get("tipo") != "arma_sagrada"] + [
            {"tipo": "arma_sagrada", "origen": "devocion", "valor": valor}]
        resultado["efecto"] = f"+{valor} a tus ataques hasta el fin del combate"
        _msg(db, campaign_id, "sistema", "Sistema",
             f"✨ El arma de {char.nombre} resplandece (+{valor} al ataque).")

    elif body.nombre == "aliento_de_dragon":
        from engine.content import aliento_de_raza
        from engine.rules import (aplicar_danio, bc, danio_con_resistencia,
                                  tirada_salvacion)
        datos = aliento_de_raza(char.raza)
        if datos is None:
            raise HTTPException(400, "Tu raza no tiene aliento de dragón")
        if not en_combate:
            raise HTTPException(409, "El aliento se usa en combate")
        if rec["usados"] >= rec["max"]:
            raise HTTPException(400, "Aliento agotado (descanso corto)")
        npc = await db.get(NPC, body.objetivo_npc_id or -1)
        if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
            raise HTTPException(404, "Elegí un objetivo")
        rec["usados"] += 1
        cd = 8 + bc(char.nivel) + mod(char.atributos["CON"])
        cr_npc = hidratar_npc(npc)
        salv = tirada_salvacion(cr_npc, datos["salvacion"], cd)
        d = roll("3d6" if char.nivel >= 5 else "2d6")
        total = d["total"] // 2 if salv["exito"] else d["total"]
        total, resistido = danio_con_resistencia(cr_npc, total,
                                                 datos["elemento"])
        eventos_d = aplicar_danio(cr_npc, max(1, total))
        persistir_npc(cr_npc, npc)
        resultado.update({"tipo": "aliento", "elemento": datos["elemento"],
                          "cd": cd, "salvacion": salv, **d,
                          "danio_final": max(1, total),
                          "resistido": resistido,
                          "objetivo": npc.nombre,
                          "objetivo_pg": npc.pg_actual})
        _roll(db, campaign_id, salv, char.id)
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🐉 {char.nombre} exhala {datos['elemento']}: {npc.nombre} "
             f"{'resiste a medias' if salv['exito'] else 'lo recibe de lleno'} "
             f"({max(1, total)} de daño).")
        # el aliento puede matar: cerrar combate si corresponde
        if (npc.pg_actual or 0) == 0:
            combate = Combat.from_dict(camp.combate)
            combate.remover(f"npc_{npc.id}")
            if not combate.npcs_restantes():
                char.recursos_clase = recursos
                _roll(db, campaign_id, {"tipo": "habilidad_clase", **resultado},
                      char.id)
                eventos, fin = await _post_accion_combate(db, camp, combate,
                                                          char, None)
                await db.commit()
                return {**resultado, "fin_combate": fin,
                        "turnos_npc": eventos}
            camp.combate = combate.to_dict()

    else:
        raise HTTPException(400, f"Habilidad sin efecto activo: {body.nombre}")

    char.recursos_clase = recursos
    _roll(db, campaign_id, {"tipo": "habilidad_clase", **resultado}, char.id)
    await db.commit()
    return resultado


# ================================================================ forma salvaje

def _revertir_forma_salvaje(char: Character) -> dict | None:
    """Devuelve la forma a la que estaba transformado y restaura los stats
    originales. None si no estaba transformado."""
    import copy
    recursos = copy.deepcopy(char.recursos_clase or {})
    forma = recursos.pop("_forma_salvaje", None)
    if not forma:
        return None
    b = forma["backup"]
    char.atributos = b["atributos"]
    char.pg_max = b["pg_max"]
    char.pg_actual = b["pg_actual"]     # vuelve con los PG previos a transformarse
    char.arma_equipada = b["arma_equipada"]
    char.armadura = b["armadura"]
    char.escudo = b["escudo"]
    char.velocidad_m = b["velocidad_m"]
    # al revertir ya no está inconsciente por la bestia caída
    char.condiciones = [c for c in char.condiciones
                        if c.get("tipo") not in ("inconsciente", "derribado")]
    char.recursos_clase = recursos
    return forma


class FormaSalvaje(BaseModel):
    bestia: str


@router.post("/wild-shape")
async def forma_salvaje(campaign_id: int, body: FormaSalvaje,
                        player: Player = Depends(jugador_actual),
                        db: AsyncSession = Depends(get_db)):
    from engine.content import formas_salvajes_disponibles
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if char.clase != "druida" or char.nivel < 2:
        raise HTTPException(400, "La Forma Salvaje es del Druida (nivel 2+)")
    import copy
    recursos = copy.deepcopy(char.recursos_clase or {})
    if "_forma_salvaje" in recursos:
        raise HTTPException(409, "Ya estás transformado (revertí primero)")
    rec = recursos.get("forma_salvaje")
    if not rec or rec["usados"] >= rec["max"]:
        raise HTTPException(400, "Sin usos de Forma Salvaje (descanso corto)")
    disponibles = formas_salvajes_disponibles(char.nivel)
    if body.bestia not in disponibles:
        raise HTTPException(400, f"Forma no disponible a tu nivel. "
                                 f"Opciones: {disponibles}")
    en_combate = camp.estado == "combate" and camp.combate
    if en_combate:
        combate = Combat.from_dict(camp.combate)
        if not combate.es_turno_de(f"pj_{char.id}"):
            raise HTTPException(409, "En combate, solo en tu turno")

    beast = MONSTRUOS[body.bestia]
    rec["usados"] += 1
    recursos["_forma_salvaje"] = {
        "beast": body.bestia, "nombre": beast["nombre"],
        "ca_fija": beast.get("ca_fija"),
        "backup": {"pg_actual": char.pg_actual, "pg_max": char.pg_max,
                   "atributos": dict(char.atributos),
                   "arma_equipada": char.arma_equipada,
                   "armadura": char.armadura, "escudo": char.escudo,
                   "velocidad_m": char.velocidad_m}}
    char.atributos = {**char.atributos,
                      **{k: beast["atributos"][k] for k in ("FUE", "DES", "CON")}}
    char.pg_max = beast["pg"]
    char.pg_actual = beast["pg"]
    char.armadura = None
    char.escudo = False
    char.arma_equipada = (beast.get("armas") or ["garra"])[0]
    char.velocidad_m = beast["velocidad_m"]
    char.recursos_clase = recursos
    _quitar_esquivando(char)
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🐾 {char.nombre} adopta la forma de {beast['nombre']} "
         f"({beast['pg']} PG, CA {beast.get('ca_fija')}).")
    resultado = {"forma": beast["nombre"], "pg": beast["pg"],
                 "ca": beast.get("ca_fija"),
                 "usos_restantes": rec["max"] - rec["usados"]}
    _roll(db, campaign_id, {"tipo": "forma_salvaje", **resultado}, char.id)
    eventos = []
    if en_combate:   # transformarse consume la acción
        eventos = await _cerrar_turno(db, camp, combate, char)
    await db.commit()
    return {**resultado, "turnos_npc": eventos}


@router.post("/wild-shape/revert")
async def revertir_forma(campaign_id: int,
                         player: Player = Depends(jugador_actual),
                         db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    forma = _revertir_forma_salvaje(char)
    if forma is None:
        raise HTTPException(400, "No estás transformado")
    _msg(db, campaign_id, "sistema", "Sistema",
         f"✨ {char.nombre} vuelve a su forma natural "
         f"({char.pg_actual}/{char.pg_max} PG).")
    await db.commit()
    return {"ok": True, "pg_actual": char.pg_actual, "pg_max": char.pg_max}


# ================================================================ acciones de combate

def _combate_activo(camp: Campaign, char: Character) -> Combat:
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "No hay combate activo")
    combate = Combat.from_dict(camp.combate)
    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, "No es tu turno")
    return combate


async def _cerrar_turno(db, camp, combate, char):
    combate.avanzar_turno()
    combate.turno_ts = time.time()
    camp.combate = combate.to_dict()
    return await _resolver_turnos_npc(db, camp)


@router.post("/combat/dodge")
async def esquivar(campaign_id: int,
                   player: Player = Depends(jugador_actual),
                   db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    combate = _combate_activo(camp, char)
    _quitar_esquivando(char)
    char.condiciones = list(char.condiciones) + [
        {"tipo": "esquivando", "origen": "accion"}]
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🛡 {char.nombre} se pone a la defensiva (los ataques en su contra "
         f"tienen desventaja hasta su próximo turno).")
    eventos = await _cerrar_turno(db, camp, combate, char)
    await db.commit()
    return {"ok": True, "turnos_npc": eventos}


class Ayudar(BaseModel):
    aliado_character_id: int


@router.post("/combat/help")
async def ayudar(campaign_id: int, body: Ayudar,
                 player: Player = Depends(jugador_actual),
                 db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    combate = _combate_activo(camp, char)
    obj = await db.get(Character, body.aliado_character_id)
    if obj is None or obj.campaign_id != campaign_id or not obj.vivo \
            or obj.id == char.id:
        raise HTTPException(404, "Elegí a un aliado (no a vos)")
    obj.condiciones = list(obj.condiciones) + [
        {"tipo": "ayudado", "origen": char.nombre}]
    _quitar_esquivando(char)
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🤝 {char.nombre} ayuda a {obj.nombre}: ventaja en su próximo ataque.")
    eventos = await _cerrar_turno(db, camp, combate, char)
    await db.commit()
    return {"ok": True, "turnos_npc": eventos}


class Empujar(BaseModel):
    objetivo_npc_id: int


@router.post("/combat/shove")
async def empujar(campaign_id: int, body: Empujar,
                  player: Player = Depends(jugador_actual),
                  db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    combate = _combate_activo(camp, char)
    npc = await db.get(NPC, body.objetivo_npc_id)
    if npc is None or npc.campaign_id != campaign_id or not npc.vivo:
        raise HTTPException(404, "Objetivo inválido")
    _quitar_esquivando(char)
    cr_pj = hidratar_personaje(char)
    cr_npc = hidratar_npc(npc)
    cd = 10 + mod(cr_npc.atributos["DES"])
    r = tirada_habilidad(cr_pj, "atletismo", cd)
    persistir_personaje(cr_pj, char)
    if r["exito"]:
        cr_npc.condiciones.append({"tipo": "derribado", "origen": "empujon"})
        persistir_npc(cr_npc, npc)
        _msg(db, campaign_id, "sistema", "Sistema",
             f"💥 {char.nombre} derriba a {npc.nombre} (los ataques melé en "
             f"su contra tienen ventaja).")
    else:
        _msg(db, campaign_id, "sistema", "Sistema",
             f"{char.nombre} intenta derribar a {npc.nombre} y falla.")
    _roll(db, campaign_id, r, char.id)
    eventos = await _cerrar_turno(db, camp, combate, char)
    await db.commit()
    return {"resolucion": r, "derribado": r["exito"], "turnos_npc": eventos}


@router.post("/combat/flee")
async def huir(campaign_id: int, bg: BackgroundTasks,
               player: Player = Depends(jugador_actual),
               db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    combate = _combate_activo(camp, char)
    if any(c.get("tipo") == "agarrado" for c in char.condiciones):
        raise HTTPException(409, "Estás agarrado: primero liberate "
                                 "(tirada de atletismo o acrobacias)")
    _quitar_esquivando(char)
    cr_pj = hidratar_personaje(char)
    r = tirada_habilidad(cr_pj, "acrobacias", 12)
    _roll(db, campaign_id, r, char.id)
    eventos = []
    if r["exito"]:
        combate.remover(f"pj_{char.id}")
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🏃 {char.nombre} escapa del combate.")
        if not combate.pjs_restantes():
            camp.estado = "exploracion"
            camp.combate = None
            for n in (await db.execute(select(NPC).where(
                    NPC.campaign_id == campaign_id, NPC.tipo == "monstruo",
                    NPC.en_escena == True))).scalars().all():  # noqa: E712
                n.en_escena = False
            _msg(db, campaign_id, "sistema", "Sistema",
                 "El grupo entero huyó. El combate termina... por ahora.")
            encolar_narracion(bg, camp,
                              "El grupo huyó del combate. Narrá la retirada "
                              "y sus posibles consecuencias.", char.id)
        else:
            camp.combate = combate.to_dict()
            eventos = await _resolver_turnos_npc(db, camp)
    else:
        # fallo: un enemigo lo castiga y no escapa
        npcs_ids = combate.npcs_restantes()
        if npcs_ids:
            npc = await db.get(NPC, int(npcs_ids[0].split("_")[1]))
            arma_n = (npc.stats or {}).get("armas", ["garrote"])[0]
            atk = resolver_ataque(hidratar_npc(npc), cr_pj,
                                  ARMAS.get(arma_n, ARMAS["garrote"]))
            eventos.append({"actor": npc.nombre, "ataque": atk,
                            "objetivo": char.nombre})
            _roll(db, campaign_id, atk)
        _msg(db, campaign_id, "sistema", "Sistema",
             f"{char.nombre} intenta huir, tropieza, y recibe un golpe "
             f"de oportunidad.")
        eventos += await _cerrar_turno(db, camp, combate, char)
    persistir_personaje(cr_pj, char)
    await db.commit()
    return {"resolucion": r, "escapo": r["exito"], "turnos_npc": eventos}


# ================================================================ clérigo / medicina

def _es_no_muerto(npc: NPC) -> bool:
    tipo = ((npc.stats or {}).get("tipo_criatura") or "").lower()
    return "no_muerto" in tipo or "undead" in tipo


def _verificar_componente(char: Character, conjuro: dict) -> None:
    """Exige (y consume, si corresponde) el componente material costoso de un
    conjuro. Lanza HTTPException si falta en el inventario."""
    comp = conjuro.get("componente_costoso")
    if not comp:
        return
    inv = [dict(x) for x in (char.inventario or [])]
    item = next((x for x in inv if x.get("nombre") == comp["nombre"]
                 and x.get("cantidad", 0) > 0), None)
    if item is None:
        raise HTTPException(400, f"Este conjuro requiere un componente material: "
                                 f"{comp['nombre']} ({comp['costo']} po)")
    if comp.get("consumido"):
        item["cantidad"] -= 1
        char.inventario = [x for x in inv if x.get("cantidad", 0) > 0]


@router.post("/channel/turn-undead")
async def expulsar_no_muertos(campaign_id: int,
                              player: Player = Depends(jugador_actual),
                              db: AsyncSession = Depends(get_db)):
    """Expulsar Muertos Vivientes (Clérigo nv2, Canalizar Divinidad). Cada
    no-muerto en combate hace salvación de SAB (CD del clérigo) o queda expulsado
    (asustado). A nivel 5+ los de CR ≤ 1/2 que fallan son destruidos."""
    from engine.content import cr_a_numero
    from engine.rules import bc
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if char.clase != "clerigo" or char.nivel < 2:
        raise HTTPException(400, "Expulsar Muertos Vivientes es del Clérigo (nv2+)")
    if camp.estado != "combate" or not camp.combate:
        raise HTTPException(409, "Se usa en combate")
    combate = Combat.from_dict(camp.combate)
    if not combate.es_turno_de(f"pj_{char.id}"):
        raise HTTPException(409, "Solo en tu turno")
    import copy
    recursos = copy.deepcopy(char.recursos_clase or {})
    cd_rec = recursos.get("canalizar_divinidad")
    if not cd_rec or cd_rec["usados"] >= cd_rec["max"]:
        raise HTTPException(400, "Sin usos de Canalizar Divinidad (descanso corto)")
    cd_rec["usados"] += 1
    dc = 8 + bc(char.nivel) + mod(char.atributos["SAB"])
    activos = set(combate.npcs_restantes())
    res = await db.execute(select(NPC).where(
        NPC.campaign_id == campaign_id, NPC.vivo == True,  # noqa: E712
        NPC.tipo == "monstruo"))
    resultados = []
    destruidos = []
    for npc in res.scalars().all():
        if f"npc_{npc.id}" not in activos or not _es_no_muerto(npc):
            continue
        cr_npc = hidratar_npc(npc)
        salv = tirada_salvacion(cr_npc, "SAB", dc)
        entry = {"npc": npc.nombre, "salvacion": salv}
        if not salv["exito"]:
            if char.nivel >= 5 and cr_a_numero((npc.stats or {}).get("cr", "0")) <= 0.5:
                cr_npc.pg_actual = 0
                entry["destruido"] = True
                destruidos.append(f"npc_{npc.id}")
            else:
                cr_npc.condiciones = [c for c in cr_npc.condiciones
                                      if c.get("tipo") not in ("asustado",
                                                               "expulsado")] + [
                    {"tipo": "asustado", "origen": "expulsar", "rondas": 3},
                    {"tipo": "expulsado", "origen": "clerigo", "rondas": 3}]
                entry["expulsado"] = True
        persistir_npc(cr_npc, npc)
        resultados.append(entry)
    char.recursos_clase = recursos
    _quitar_esquivando(char)
    _msg(db, campaign_id, "sistema", "Sistema",
         f"☀️ {char.nombre} canaliza divinidad y expulsa a los muertos "
         f"vivientes (CD {dc}). "
         f"{sum(1 for r in resultados if r.get('destruido'))} destruidos, "
         f"{sum(1 for r in resultados if r.get('expulsado'))} expulsados.")
    _roll(db, campaign_id, {"tipo": "expulsar_no_muertos", "cd": dc,
                            "resultados": resultados}, char.id)
    for nid in destruidos:
        combate.remover(nid)
    eventos, fin = await _post_accion_combate(db, camp, combate, char, None)
    await db.commit()
    camp = await db.get(Campaign, campaign_id)
    return {"cd": dc, "resultados": resultados, "turnos_npc": eventos,
            "fin_combate": fin, "combate": camp.combate}


class Estabilizar(BaseModel):
    objetivo_character_id: int


@router.post("/medicine/stabilize")
async def estabilizar(campaign_id: int, body: Estabilizar,
                      player: Player = Depends(jugador_actual),
                      db: AsyncSession = Depends(get_db)):
    """Estabiliza a un aliado inconsciente con una tirada de Medicina (CD 10).
    En combate consume tu turno."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    obj = await db.get(Character, body.objetivo_character_id)
    if obj is None or obj.campaign_id != campaign_id:
        raise HTTPException(404, "Objetivo inválido")
    if not (obj.pg_actual == 0 and obj.vivo):
        raise HTTPException(400, "El objetivo no está agonizando")
    if any(c.get("tipo") == "estable" for c in obj.condiciones):
        raise HTTPException(400, "Ya está estabilizado")
    en_combate = camp.estado == "combate" and camp.combate
    combate = None
    if en_combate:
        combate = Combat.from_dict(camp.combate)
        if not combate.es_turno_de(f"pj_{char.id}"):
            raise HTTPException(409, "En combate, solo en tu turno")
    cr = hidratar_personaje(char)
    r = tirada_habilidad(cr, "medicina", 10)
    _roll(db, campaign_id, r, char.id)
    if r["exito"]:
        obj.muerte_exitos = 0
        obj.muerte_fallos = 0
        obj.condiciones = [c for c in obj.condiciones
                           if c.get("tipo") != "estable"] + [
            {"tipo": "estable", "origen": "medicina"}]
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🩹 {char.nombre} estabiliza a {obj.nombre} (Medicina "
             f"{r['total']} ≥ 10): deja de tirar salvaciones de muerte.")
    else:
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🩹 {char.nombre} no logra estabilizar a {obj.nombre} "
             f"(Medicina {r['total']} < 10).")
    eventos = []
    if en_combate:
        _quitar_esquivando(char)
        eventos = await _cerrar_turno(db, camp, combate, char)
    await db.commit()
    return {"resolucion": r, "estabilizado": r["exito"], "turnos_npc": eventos}


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
    if (char.recursos_clase or {}).get("_forma_salvaje"):
        _revertir_forma_salvaje(char)   # descansar deshace la Forma Salvaje
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
    # recursos de clase con reset corto (deepcopy: trampa de mutación JSON)
    import copy
    recursos = copy.deepcopy(char.recursos_clase or {})
    for nombre, rec in recursos.items():
        if rec.get("reset") == "corto" and "usados" in rec:
            rec["usados"] = 0
    # Recuperación Arcana del mago: 1 vez por día, automática en el corto
    ra = recursos.get("recuperacion_arcana")
    if ra and ra["usados"] < ra["max"] and cr.spell_state:
        presupuesto = (char.nivel + 1) // 2
        recuperados = []
        for nv in sorted(cr.spell_state.slots, key=int):
            s = cr.spell_state.slots[nv]
            while s["usados"] > 0 and presupuesto >= int(nv):
                s["usados"] -= 1
                presupuesto -= int(nv)
                recuperados.append(nv)
        if recuperados:
            ra["usados"] = 1
            r["recuperacion_arcana"] = recuperados
    char.recursos_clase = recursos
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
    from engine.content import recursos_clase_iniciales, recursos_raciales
    for c in res.scalars().all():
        if (c.recursos_clase or {}).get("_forma_salvaje"):
            _revertir_forma_salvaje(c)   # descansar deshace la Forma Salvaje
        cr = hidratar_personaje(c)
        r = descanso_largo(cr)
        persistir_personaje(cr, c)
        c.pg_actual = c.pg_max  # persistir_personaje ya lo hace; explícito
        breakdown = (c.opciones_clase or {}).get("multiclase") or {c.clase: c.nivel}
        rec: dict = {}
        for cls, lvl in breakdown.items():
            rec.update(recursos_clase_iniciales(cls, lvl,
                                                mod(c.atributos["CAR"])))
        rec.update(recursos_raciales(c.raza, c.nivel))
        c.recursos_clase = rec
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
    from engine.content import (puede_usar_arma, puede_usar_armadura,
                                puede_usar_escudo)
    comp = char.competencias or {}
    nombres_inv = {x.get("nombre") for x in char.inventario}
    if body.arma is not None:
        if body.arma not in ARMAS:
            raise HTTPException(400, "Arma desconocida")
        if body.arma not in nombres_inv and body.arma != char.arma_equipada:
            raise HTTPException(400, f"No tenés {body.arma} en el inventario")
        if not puede_usar_arma(comp, body.arma):
            raise HTTPException(400, f"No sos competente con "
                                     f"{body.arma.replace('_', ' ')}")
        char.arma_equipada = body.arma
    if body.armadura is not None:
        if body.armadura and body.armadura not in ARMADURAS:
            raise HTTPException(400, "Armadura desconocida")
        if body.armadura and body.armadura not in nombres_inv \
                and body.armadura != char.armadura:
            raise HTTPException(400, f"No tenés {body.armadura}")
        if not puede_usar_armadura(comp, body.armadura):
            raise HTTPException(400, f"No sabés usar "
                                     f"{body.armadura.replace('_', ' ')}")
        char.armadura = body.armadura or None
    if body.escudo is not None:
        if body.escudo and not puede_usar_escudo(comp):
            raise HTTPException(400, "No sabés usar escudo")
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


# ================================================================ conjuros

class GestionarConjuros(BaseModel):
    lista: list[str]


@router.post("/spells/manage")
async def gestionar_conjuros(campaign_id: int, body: GestionarConjuros,
                             player: Player = Depends(jugador_actual),
                             db: AsyncSession = Depends(get_db)):
    """Setea los conjuros preparados (mago/clérigo/druida/paladín) o
    conocidos (bardo/hechicero/brujo/ranger), con validación completa:
    existencia, nivel lanzable y cantidad máxima. Solo fuera de combate."""
    from engine.content import limite_conjuros, nivel_max_conjuro
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "No podés reorganizar conjuros en combate")

    atributo = CLASES[char.clase]["atributo_magico"]
    if not atributo:
        raise HTTPException(400, "Tu clase no lanza conjuros")
    sistema, limite = limite_conjuros(char.clase, char.nivel,
                                      mod(char.atributos[atributo]))
    if sistema == "ninguno" or limite == 0:
        raise HTTPException(400, "Tu clase no maneja conjuros a este nivel")

    nv_max = nivel_max_conjuro(char.clase, char.nivel)
    trucos, con_nivel = [], []
    for nombre in dict.fromkeys(body.lista):   # dedup preservando orden
        c = CONJUROS.get(nombre)
        if c is None:
            raise HTTPException(400, f"Conjuro desconocido: {nombre}")
        if c["nivel"] == 0:
            trucos.append(nombre)
        else:
            if c["nivel"] > nv_max:
                raise HTTPException(400, f"{nombre} es nivel {c['nivel']} y tu "
                                         f"máximo lanzable es {nv_max}")
            con_nivel.append(nombre)
    if len(con_nivel) > limite:
        raise HTTPException(400, f"Máximo {limite} conjuros con nivel "
                                 f"({sistema}); mandaste {len(con_nivel)}")
    if len(trucos) > 6:
        raise HTTPException(400, "Máximo 6 trucos")

    final = trucos + con_nivel
    if sistema == "preparados":
        char.preparados = final
    else:
        char.conocidos = final
    _msg(db, campaign_id, "sistema", "Sistema",
         f"📜 {char.nombre} reorganiza sus conjuros ({len(con_nivel)}/{limite} "
         f"con nivel + {len(trucos)} trucos).")
    await db.commit()
    return {"sistema": sistema, "limite": limite, "nivel_max": nv_max,
            "lista": final}


class LanzarRitual(BaseModel):
    conjuro: str


@router.post("/spells/ritual")
async def lanzar_ritual(campaign_id: int, body: LanzarRitual,
                        bg: BackgroundTasks,
                        player: Player = Depends(jugador_actual),
                        db: AsyncSession = Depends(get_db)):
    """Lanza un conjuro con la etiqueta ritual SIN gastar espacio de conjuro,
    tomando 10 minutos extra. Solo fuera de combate."""
    from engine.content import CLASES_RITUALISTAS
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "Los rituales tardan 10 minutos: no en combate")
    conjuro = CONJUROS.get(body.conjuro)
    if conjuro is None:
        raise HTTPException(400, f"Conjuro desconocido: {body.conjuro}")
    if not conjuro.get("ritual"):
        raise HTTPException(400, f"{body.conjuro} no es un conjuro ritual")
    if char.clase not in CLASES_RITUALISTAS:
        raise HTTPException(400, "Tu clase no puede lanzar rituales")
    if body.conjuro not in (char.preparados or []) \
            and body.conjuro not in (char.conocidos or []):
        raise HTTPException(400, "No tenés ese conjuro preparado/conocido")
    _verificar_componente(char, conjuro)
    camp.tiempo_juego_min += 10
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🔯 {char.nombre} lanza el ritual {body.conjuro} (sin gastar espacio, "
         f"+10 min): {conjuro.get('efecto', '')}")
    _roll(db, campaign_id, {"tipo": "ritual", "conjuro": body.conjuro}, char.id)
    encolar_narracion(bg, camp,
                      f"{char.nombre} realiza el ritual de {body.conjuro}. "
                      f"Efecto mecánico: {conjuro.get('efecto', '')}. "
                      f"Narrá el ritual y su resultado en la ficción.",
                      char.id)
    await db.commit()
    return {"ok": True, "conjuro": body.conjuro,
            "efecto": conjuro.get("efecto"), "narrando": True}


# ================================================================ hechicería

class SeleccionMetamagia(BaseModel):
    opciones: list[str]


@router.post("/metamagic/select")
async def seleccionar_metamagia(campaign_id: int, body: SeleccionMetamagia,
                                player: Player = Depends(jugador_actual),
                                db: AsyncSession = Depends(get_db)):
    """Elige las opciones de Metamagia conocidas (Hechicero nv3+)."""
    from engine.content import METAMAGIA, metamagias_conocidas_max
    char = await _mi_personaje(campaign_id, player, db)
    if char.clase != "hechicero" or char.nivel < 3:
        raise HTTPException(400, "La Metamagia es del Hechicero (nivel 3+)")
    maxn = metamagias_conocidas_max(char.nivel)
    opciones = list(dict.fromkeys(body.opciones))
    for o in opciones:
        if o not in METAMAGIA:
            raise HTTPException(400, f"Metamagia desconocida: {o}. "
                                     f"Opciones: {list(METAMAGIA)}")
    if len(opciones) > maxn:
        raise HTTPException(400, f"A nivel {char.nivel} conocés hasta {maxn} "
                                 f"metamagias")
    opc = dict(char.opciones_clase or {})
    opc["metamagia"] = opciones
    char.opciones_clase = opc
    await db.commit()
    return {"metamagia": opciones, "max": maxn}


class FuenteDeMagia(BaseModel):
    direccion: str      # "slot_a_puntos" | "puntos_a_slot"
    nivel: int


@router.post("/sorcery/font")
async def fuente_de_magia(campaign_id: int, body: FuenteDeMagia,
                          player: Player = Depends(jugador_actual),
                          db: AsyncSession = Depends(get_db)):
    """Fuente de Magia (Hechicero nv2+): convierte espacios de conjuro en
    Puntos de Hechicería y viceversa. Es una acción adicional: no cierra turno."""
    from engine.content import COSTO_SLOT_EN_PH
    char = await _mi_personaje(campaign_id, player, db)
    if char.clase != "hechicero" or char.nivel < 2:
        raise HTTPException(400, "La Fuente de Magia es del Hechicero (nivel 2+)")
    import copy
    recursos = copy.deepcopy(char.recursos_clase or {})
    ph = recursos.get("puntos_hechiceria")
    if not ph:
        raise HTTPException(400, "No tenés Puntos de Hechicería")
    slots = copy.deepcopy(char.slots or {})

    if body.direccion == "slot_a_puntos":
        s = slots.get(str(body.nivel))
        if body.nivel < 1 or not s or s["usados"] >= s["max"]:
            raise HTTPException(400, f"Sin espacio de nivel {body.nivel} para "
                                     f"convertir")
        s["usados"] += 1
        ph["pool"] = min(ph["pool_max"], ph["pool"] + body.nivel)
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🔮 {char.nombre} sacrifica un espacio de nivel {body.nivel}: "
             f"+{body.nivel} Puntos de Hechicería ({ph['pool']}/{ph['pool_max']}).")
    elif body.direccion == "puntos_a_slot":
        costo = COSTO_SLOT_EN_PH.get(body.nivel)
        if costo is None:
            raise HTTPException(400, "Podés crear espacios de nivel 1 a 5")
        if ph["pool"] < costo:
            raise HTTPException(400, f"Necesitás {costo} PH (tenés {ph['pool']})")
        ph["pool"] -= costo
        s = slots.get(str(body.nivel))
        if s and s["usados"] > 0:
            s["usados"] -= 1
        elif s:
            s["max"] += 1
        else:
            slots[str(body.nivel)] = {"usados": 0, "max": 1}
        _msg(db, campaign_id, "sistema", "Sistema",
             f"🔮 {char.nombre} teje {costo} Puntos de Hechicería en un espacio "
             f"de conjuro de nivel {body.nivel}.")
    else:
        raise HTTPException(400, "direccion: 'slot_a_puntos' o 'puntos_a_slot'")

    char.recursos_clase = recursos
    char.slots = slots
    await db.commit()
    return {"puntos_hechiceria": ph["pool"], "slots": slots}


# ================================================================ brujo / pícaro / bardo

class SeleccionInvocaciones(BaseModel):
    invocaciones: list[str]


@router.post("/invocations/select")
async def seleccionar_invocaciones(campaign_id: int, body: SeleccionInvocaciones,
                                   player: Player = Depends(jugador_actual),
                                   db: AsyncSession = Depends(get_db)):
    """Elige las Invocaciones Sobrenaturales conocidas (Brujo nv2+)."""
    from engine.content import INVOCACIONES, invocaciones_conocidas_max
    char = await _mi_personaje(campaign_id, player, db)
    if char.clase != "brujo" or char.nivel < 2:
        raise HTTPException(400, "Las Invocaciones son del Brujo (nivel 2+)")
    maxn = invocaciones_conocidas_max(char.nivel)
    elegidas = list(dict.fromkeys(body.invocaciones))
    conocidos = set(char.conocidos or [])
    for inv in elegidas:
        meta = INVOCACIONES.get(inv)
        if not meta:
            raise HTTPException(400, f"Invocación desconocida: {inv}. "
                                     f"Opciones: {list(INVOCACIONES)}")
        if char.nivel < meta["nivel_min"]:
            raise HTTPException(400, f"{meta['nombre']} requiere nivel "
                                     f"{meta['nivel_min']}")
        req = meta.get("requisito_conjuro")
        if req and req not in conocidos:
            raise HTTPException(400, f"{meta['nombre']} requiere conocer {req}")
    if len(elegidas) > maxn:
        raise HTTPException(400, f"A nivel {char.nivel} conocés hasta {maxn} "
                                 f"invocaciones")
    opc = dict(char.opciones_clase or {})
    opc["invocaciones"] = elegidas
    char.opciones_clase = opc
    await db.commit()
    return {"invocaciones": elegidas, "max": maxn}


class SeleccionExpertise(BaseModel):
    habilidades: list[str]


@router.post("/expertise/select")
async def seleccionar_expertise(campaign_id: int, body: SeleccionExpertise,
                                player: Player = Depends(jugador_actual),
                                db: AsyncSession = Depends(get_db)):
    """Elige las habilidades con Expertise (doble competencia). Pícaro: 2 a nv1,
    4 a nv6. Bardo: 2 a nv3, 4 a nv10."""
    from engine.rules import HABILIDADES
    char = await _mi_personaje(campaign_id, player, db)
    if char.clase == "picaro":
        maxn = 4 if char.nivel >= 6 else 2
    elif char.clase == "bardo":
        maxn = 4 if char.nivel >= 10 else (2 if char.nivel >= 3 else 0)
    else:
        raise HTTPException(400, "Expertise es de Pícaro o Bardo")
    if maxn == 0:
        raise HTTPException(400, "Todavía no tenés Expertise a este nivel")
    elegidas = list(dict.fromkeys(body.habilidades))
    props = set(char.competencias.get("habilidades", []))
    for h in elegidas:
        if h not in HABILIDADES:
            raise HTTPException(400, f"Habilidad desconocida: {h}")
        if h not in props:
            raise HTTPException(400, "Solo podés poner Expertise en habilidades "
                                     f"en las que ya tenés competencia: {h}")
    if len(elegidas) > maxn:
        raise HTTPException(400, f"A nivel {char.nivel} tenés hasta {maxn} "
                                 f"expertise")
    opc = dict(char.opciones_clase or {})
    opc["expertise"] = elegidas
    char.opciones_clase = opc
    await db.commit()
    return {"expertise": elegidas, "max": maxn}


# ================================================================ nivel

class SubirNivel(BaseModel):
    metodo: str = "fijo"   # "fijo" (mitad+1) | "tirar"
    # Mejora de atributos (niveles 4/8/12/16/19): {"FUE": 2} o {"DES": 1, "CON": 1}
    asi: dict[str, int] | None = None
    feat: str | None = None            # dote en lugar del +2 (clave de FEATS)
    feat_atributo: str | None = None   # atributo elegido si la dote lo pide
    subclase: str | None = None   # requerida al llegar al nivel de subclase
    clase_multiclase: str | None = None  # clase en la que ganás este nivel


@router.post("/level-up")
async def subir_nivel(campaign_id: int, body: SubirNivel,
                      player: Player = Depends(jugador_actual),
                      db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    objetivo = nivel_por_xp(char.xp)
    if objetivo <= char.nivel:
        raise HTTPException(400, f"Todavía no tenés XP para subir "
                                 f"(nivel {char.nivel}, {char.xp} XP)")
    nuevo_nivel = char.nivel + 1
    ya_multiclase = len((char.opciones_clase or {}).get("multiclase") or {}) > 1
    # subclase al llegar al nivel correspondiente (solo para monoclase; una vez
    # multiclaseado, las subclases se cargan como texto libre)
    from engine.content import NIVEL_SUBCLASE, SUBCLASES_SRD
    if not body.clase_multiclase and not ya_multiclase \
            and nuevo_nivel == NIVEL_SUBCLASE.get(char.clase) and not char.subclase:
        opciones = SUBCLASES_SRD.get(char.clase, [])
        if body.subclase not in opciones and not (body.subclase or "").strip():
            raise HTTPException(400,
                f"Nivel {nuevo_nivel}: elegí subclase. Del SRD: {opciones} "
                f"(o escribí la tuya como texto libre)")
        char.subclase = (body.subclase or "").strip()[:60]
    # Mejora de Puntuación de Característica: niveles 4/8/12/16/19 (SRD).
    # Se puede elegir una DOTE en lugar del +2 a atributos.
    feat_res = None
    if nuevo_nivel in (4, 8, 12, 16, 19):
        if body.feat:
            from ..feats import aplicar_feat
            try:
                feat_res = aplicar_feat(char, body.feat, body.feat_atributo)
            except ValueError as e:
                raise HTTPException(400, str(e))
        else:
            asi = body.asi or {}
            valido = (sum(asi.values()) == 2
                      and all(a in ("FUE", "DES", "CON", "INT", "SAB", "CAR")
                              and 1 <= v <= 2 for a, v in asi.items()))
            if not valido:
                raise HTTPException(400,
                    "Nivel {}: mandá 'asi' con +2 puntos a repartir "
                    '(ej {{"FUE": 2}}) o una \'feat\'.'.format(nuevo_nivel))
            atrs = dict(char.atributos)
            for a, v in asi.items():
                if atrs[a] + v > 20:
                    raise HTTPException(400, f"{a} superaría 20")
                atrs[a] += v
            char.atributos = atrs
    char.nivel = nuevo_nivel

    # --- multiclase: registro de niveles por clase ---
    from engine.content import cumple_requisitos_multiclase
    opc = dict(char.opciones_clase or {})
    breakdown = dict(opc.get("multiclase") or {char.clase: nuevo_nivel - 1})
    if sum(breakdown.values()) != nuevo_nivel - 1:
        breakdown = {char.clase: nuevo_nivel - 1}   # reconstruir si no cuadra
    objetivo_clase = body.clase_multiclase or char.clase
    if objetivo_clase not in CLASES:
        raise HTTPException(400, f"Clase inválida: {objetivo_clase}")
    if objetivo_clase not in breakdown:   # abrís una clase nueva: chequeo PHB
        ok_n, falta_n = cumple_requisitos_multiclase(objetivo_clase, char.atributos)
        ok_p, falta_p = cumple_requisitos_multiclase(char.clase, char.atributos)
        if not (ok_n and ok_p):
            raise HTTPException(400, "No cumplís los requisitos para "
                                     f"multiclasear en {objetivo_clase} "
                                     f"(necesitás {falta_n or falta_p})")
    breakdown[objetivo_clase] = breakdown.get(objetivo_clase, 0) + 1
    opc["multiclase"] = breakdown
    char.opciones_clase = opc
    es_multiclase = len(breakdown) > 1

    caras = int(CLASES[objetivo_clase]["dado_golpe"][1:])   # dado de la clase ganada
    con = mod(char.atributos["CON"])
    if body.metodo == "tirar":
        d = roll(f"1{char.dado_golpe}")
        ganancia = max(1, d["dados"][0] + con)
        detalle = {"metodo": "tirar", "dado": d["dados"][0]}
    else:
        ganancia = max(1, (caras // 2 + 1) + con)
        detalle = {"metodo": "fijo", "valor": caras // 2 + 1}
    # PG extra por rasgos: enano de las colinas y linaje dracónico
    if "colinas" in (char.raza or "") or char.subclase == "linaje_draconico":
        ganancia += 1
    # PG extra por dote Vigoroso (+2 por nivel): el nivel nuevo suma su parte
    from engine.content import efectos_feats
    ganancia += efectos_feats(char.feats or [])["hp_por_nivel"]
    char.pg_max += ganancia
    char.pg_actual += ganancia
    char.dados_golpe_disp = min(char.nivel, char.dados_golpe_disp + 1)

    # recursos de clase del nuevo nivel: se recalculan por cada clase según su
    # propio nivel (usos gastados se preservan). Se conserva la Forma Salvaje.
    from engine.content import (recursos_clase_iniciales, recursos_raciales,
                                slots_multiclase)
    nuevos_rec: dict = {}
    for cls, lvl in breakdown.items():
        nuevos_rec.update(recursos_clase_iniciales(cls, lvl,
                                                   mod(char.atributos["CAR"])))
    nuevos_rec.update(recursos_raciales(char.raza, char.nivel))
    viejos_rec = char.recursos_clase or {}
    if viejos_rec.get("_forma_salvaje"):
        nuevos_rec["_forma_salvaje"] = viejos_rec["_forma_salvaje"]
    for nombre, rec in nuevos_rec.items():
        if nombre in viejos_rec and isinstance(rec, dict):
            if "usados" in rec:
                rec["usados"] = min(viejos_rec[nombre].get("usados", 0),
                                    rec["max"])
            if "pool" in rec:
                gastado = viejos_rec[nombre].get("pool_max", 0) - \
                    viejos_rec[nombre].get("pool", 0)
                rec["pool"] = max(0, rec["pool_max"] - gastado)
    char.recursos_clase = nuevos_rec

    # recalcular slots preservando los gastados. En multiclase se usa la tabla
    # combinada del PHB; en monoclase, la tabla propia de la clase.
    if es_multiclase and any(CLASES[c]["lanzador"] for c in breakdown):
        nuevos = slots_multiclase(breakdown)
    else:
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
            "pg_max": char.pg_max, "slots": char.slots,
            "feat": feat_res, "multiclase": breakdown,
            "clase_ganada": objetivo_clase, **detalle}


# ================================================================ sintonía de objetos

MAX_SINTONIA = 3


class Sintonia(BaseModel):
    item: str


@router.post("/attunement/attune")
async def sintonizar(campaign_id: int, body: Sintonia,
                     player: Player = Depends(jugador_actual),
                     db: AsyncSession = Depends(get_db)):
    """Entra en sintonía con un objeto mágico del inventario (máx 3).
    Requiere un descanso corto en la ficción; fuera de combate."""
    from engine.content import OBJETOS_MAGICOS
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    if camp.estado == "combate":
        raise HTTPException(409, "La sintonía requiere un descanso corto")
    nombre = body.item.strip()
    if not any(x.get("nombre") == nombre for x in (char.inventario or [])):
        raise HTTPException(400, f"No tenés '{nombre}' en el inventario")
    opc = dict(char.opciones_clase or {})
    sintonia = list(opc.get("sintonia", []))
    if nombre in sintonia:
        raise HTTPException(400, "Ya estás en sintonía con ese objeto")
    if len(sintonia) >= MAX_SINTONIA:
        raise HTTPException(400, f"Ya estás en sintonía con {MAX_SINTONIA} "
                                 f"objetos (el máximo). Terminá una primero.")
    info = OBJETOS_MAGICOS.get(nombre, {})
    if info and info.get("requiere_sintonia") is False:
        raise HTTPException(400, f"'{nombre}' no requiere sintonía")
    sintonia.append(nombre)
    opc["sintonia"] = sintonia
    char.opciones_clase = opc
    camp.tiempo_juego_min += 60
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🔗 {char.nombre} entra en sintonía con {nombre} "
         f"({len(sintonia)}/{MAX_SINTONIA}).")
    await db.commit()
    return {"sintonia": sintonia, "max": MAX_SINTONIA}


@router.post("/attunement/end")
async def terminar_sintonia(campaign_id: int, body: Sintonia,
                            player: Player = Depends(jugador_actual),
                            db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    opc = dict(char.opciones_clase or {})
    sintonia = list(opc.get("sintonia", []))
    if body.item.strip() not in sintonia:
        raise HTTPException(400, "No estás en sintonía con ese objeto")
    sintonia.remove(body.item.strip())
    opc["sintonia"] = sintonia
    char.opciones_clase = opc
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🔓 {char.nombre} termina su sintonía con {body.item.strip()}.")
    await db.commit()
    return {"sintonia": sintonia, "max": MAX_SINTONIA}


# ================================================================ monturas

class Montura(BaseModel):
    bestia: str


@router.post("/mount")
async def montar(campaign_id: int, body: Montura,
                 player: Player = Depends(jugador_actual),
                 db: AsyncSession = Depends(get_db)):
    """Monta una bestia (montura). Mientras cabalgás usás la velocidad de la
    montura. La montura tiene sus propios PG y puede ser objetivo."""
    char = await _mi_personaje(campaign_id, player, db)
    camp = await db.get(Campaign, campaign_id)
    bestia = MONSTRUOS.get(body.bestia)
    if bestia is None or bestia.get("tipo_criatura") != "bestia":
        bestias = [k for k, v in MONSTRUOS.items()
                   if v.get("tipo_criatura") == "bestia"]
        raise HTTPException(400, f"Montura inválida. Bestias: {bestias}")
    opc = dict(char.opciones_clase or {})
    if opc.get("montura"):
        raise HTTPException(409, "Ya estás montando (desmontá primero)")
    opc["montura"] = {"bestia": body.bestia, "nombre": bestia["nombre"],
                      "pg_actual": bestia["pg"], "pg_max": bestia["pg"],
                      "velocidad_m": bestia["velocidad_m"],
                      "ca": bestia.get("ca_fija")}
    char.opciones_clase = opc
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🐎 {char.nombre} monta un {bestia['nombre']} "
         f"(velocidad {bestia['velocidad_m']}m).")
    await db.commit()
    return {"montura": opc["montura"]}


@router.post("/dismount")
async def desmontar(campaign_id: int,
                    player: Player = Depends(jugador_actual),
                    db: AsyncSession = Depends(get_db)):
    char = await _mi_personaje(campaign_id, player, db)
    opc = dict(char.opciones_clase or {})
    montura = opc.pop("montura", None)
    if not montura:
        raise HTTPException(400, "No estás montando")
    char.opciones_clase = opc
    _msg(db, campaign_id, "sistema", "Sistema",
         f"🚶 {char.nombre} desmonta de su {montura['nombre']}.")
    await db.commit()
    return {"ok": True}


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
