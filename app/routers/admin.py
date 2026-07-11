"""Panel de administración (DM humano).

Protegido por ADMIN_TOKEN (env). Sin token configurado, el panel queda
deshabilitado. Pensado para corregir rarezas del narrador en segundos:
PG desajustados, items fantasma, NPCs duplicados, crónica desviada.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..models import (NPC, Campaign, Character, Message, PendingConsequence,
                      Quest)

router = APIRouter(prefix="/api/admin/campaigns/{campaign_id}",
                   tags=["admin"])


def admin_ok(x_admin_token: str = Header(default="")):
    s = get_settings()
    if not s.admin_token:
        raise HTTPException(403, "Panel de admin deshabilitado "
                                 "(configurá ADMIN_TOKEN)")
    if x_admin_token != s.admin_token:
        raise HTTPException(401, "Token de admin inválido")
    return True


@router.get("/full")
async def dump_completo(campaign_id: int, _=Depends(admin_ok),
                        db: AsyncSession = Depends(get_db)):
    camp = await db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaña inexistente")
    chars = (await db.execute(select(Character).where(
        Character.campaign_id == campaign_id))).scalars().all()
    npcs = (await db.execute(select(NPC).where(
        NPC.campaign_id == campaign_id))).scalars().all()
    quests = (await db.execute(select(Quest).where(
        Quest.campaign_id == campaign_id))).scalars().all()
    cons = (await db.execute(select(PendingConsequence).where(
        PendingConsequence.campaign_id == campaign_id))).scalars().all()
    return {
        "campania": {"id": camp.id, "nombre": camp.nombre,
                     "estado": camp.estado, "descripcion": camp.descripcion,
                     "resumen": camp.resumen_actual,
                     "ubicacion": camp.ubicacion_actual,
                     "en_combate": bool(camp.combate)},
        "personajes": [{
            "id": c.id, "nombre": c.nombre, "clase": c.clase,
            "nivel": c.nivel, "pg_actual": c.pg_actual, "pg_max": c.pg_max,
            "oro": (c.monedas or {}).get("mo", 0), "xp": c.xp, "vivo": c.vivo,
            "condiciones": c.condiciones, "inventario": c.inventario,
        } for c in chars],
        "npcs": [{"id": n.id, "nombre": n.nombre, "tipo": n.tipo,
                  "actitud": n.actitud, "en_escena": n.en_escena,
                  "vivo": n.vivo, "pg_actual": n.pg_actual,
                  "condiciones": n.condiciones} for n in npcs],
        "quests": [{"id": q.id, "titulo": q.titulo, "estado": q.estado}
                   for q in quests],
        "consecuencias": [{"id": p.id, "descripcion": p.descripcion}
                          for p in cons],
    }


# Campos editables por entidad (whitelist estricta)
CAMPOS_PJ = {"pg_actual": int, "pg_max": int, "xp": int,
             "vivo": bool, "condiciones": list, "inventario": list}
CAMPOS_NPC = {"pg_actual": int, "actitud": str, "en_escena": bool,
              "vivo": bool, "condiciones": list, "descripcion": str}
CAMPOS_CAMP = {"descripcion": str, "resumen_actual": str,
               "ubicacion_actual": str}


class Patch(BaseModel):
    campos: dict


def _aplicar_patch(entidad, campos: dict, whitelist: dict) -> list[str]:
    aplicados = []
    for k, v in campos.items():
        if k not in whitelist:
            raise HTTPException(400, f"Campo no editable: {k}. "
                                     f"Permitidos: {list(whitelist)}")
        if not isinstance(v, whitelist[k]):
            raise HTTPException(400, f"{k} debe ser {whitelist[k].__name__}")
        setattr(entidad, k, v)
        aplicados.append(k)
    return aplicados


@router.post("/character/{char_id}")
async def editar_pj(campaign_id: int, char_id: int, body: Patch,
                    _=Depends(admin_ok), db: AsyncSession = Depends(get_db)):
    c = await db.get(Character, char_id)
    if c is None or c.campaign_id != campaign_id:
        raise HTTPException(404, "Personaje inexistente")
    campos = dict(body.campos)
    if "oro" in campos:   # "oro" es virtual: monedas["mo"]
        if not isinstance(campos["oro"], int) or campos["oro"] < 0:
            raise HTTPException(400, "oro debe ser un entero >= 0")
        c.monedas = {**(c.monedas or {}), "mo": campos.pop("oro")}
    aplicados = _aplicar_patch(c, campos, CAMPOS_PJ)
    if "oro" in body.campos:
        aplicados.append("oro")
    if "pg_actual" in body.campos:
        c.pg_actual = max(0, min(c.pg_actual, c.pg_max))
    await db.commit()
    return {"ok": True, "aplicados": aplicados}


@router.post("/npc/{npc_id}")
async def editar_npc(campaign_id: int, npc_id: int, body: Patch,
                     _=Depends(admin_ok), db: AsyncSession = Depends(get_db)):
    n = await db.get(NPC, npc_id)
    if n is None or n.campaign_id != campaign_id:
        raise HTTPException(404, "NPC inexistente")
    aplicados = _aplicar_patch(n, body.campos, CAMPOS_NPC)
    await db.commit()
    return {"ok": True, "aplicados": aplicados}


@router.delete("/npc/{npc_id}")
async def borrar_npc(campaign_id: int, npc_id: int, _=Depends(admin_ok),
                     db: AsyncSession = Depends(get_db)):
    n = await db.get(NPC, npc_id)
    if n is None or n.campaign_id != campaign_id:
        raise HTTPException(404, "NPC inexistente")
    await db.delete(n)
    await db.commit()
    return {"ok": True}


@router.post("/edit")
async def editar_campania(campaign_id: int, body: Patch, _=Depends(admin_ok),
                          db: AsyncSession = Depends(get_db)):
    camp = await db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaña inexistente")
    aplicados = _aplicar_patch(camp, body.campos, CAMPOS_CAMP)
    await db.commit()
    return {"ok": True, "aplicados": aplicados}


class HablarComoDM(BaseModel):
    texto: str


@router.post("/say-as-dm")
async def hablar_como_dm(campaign_id: int, body: HablarComoDM,
                         _=Depends(admin_ok),
                         db: AsyncSession = Depends(get_db)):
    """El mensaje entra como narración del DM: los jugadores no distinguen
    (y el narrador IA lo ve en su contexto y construye sobre él)."""
    db.add(Message(campaign_id=campaign_id, autor="dm", autor_nombre="DM",
                   contenido=body.texto[:4000]))
    await db.commit()
    return {"ok": True}


@router.post("/end-combat")
async def forzar_fin_combate(campaign_id: int, _=Depends(admin_ok),
                             db: AsyncSession = Depends(get_db)):
    camp = await db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaña inexistente")
    camp.combate = None
    camp.estado = "exploracion"
    camp.narrando = False
    db.add(Message(campaign_id=campaign_id, autor="sistema",
                   autor_nombre="Sistema",
                   contenido="⚙ El administrador dio por terminado el combate."))
    await db.commit()
    return {"ok": True}


@router.post("/quest/{quest_id}/{estado}")
async def cambiar_quest(campaign_id: int, quest_id: int, estado: str,
                        _=Depends(admin_ok),
                        db: AsyncSession = Depends(get_db)):
    if estado not in ("activa", "completada", "fallida"):
        raise HTTPException(400, "estado: activa|completada|fallida")
    q = await db.get(Quest, quest_id)
    if q is None or q.campaign_id != campaign_id:
        raise HTTPException(404, "Quest inexistente")
    q.estado = estado
    await db.commit()
    return {"ok": True}


@router.delete("/consequence/{con_id}")
async def borrar_consecuencia(campaign_id: int, con_id: int,
                              _=Depends(admin_ok),
                              db: AsyncSession = Depends(get_db)):
    p = await db.get(PendingConsequence, con_id)
    if p is None or p.campaign_id != campaign_id:
        raise HTTPException(404, "Consecuencia inexistente")
    await db.delete(p)
    await db.commit()
    return {"ok": True}
