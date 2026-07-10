from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.content import ARMADURAS, ARMAS, CLASES, slots_iniciales
from engine.rules import HABILIDADES, bc, calcular_ca, mod, nivel_por_xp

from ..db import get_db
from ..deps import jugador_actual
from ..hydration import hidratar_personaje
from ..models import Character, Player

router = APIRouter(prefix="/api/characters", tags=["characters"])

ATRIBUTOS = ("FUE", "DES", "CON", "INT", "SAB", "CAR")


class CrearPersonaje(BaseModel):
    nombre: str
    raza: str
    clase: str
    atributos: dict[str, int]        # ya con bonos raciales aplicados
    habilidades: list[str] = []      # competencias elegidas
    conocidos: list[str] = []        # conjuros (si aplica)
    preparados: list[str] = []
    armadura: str | None = None
    escudo: bool = False
    arma_equipada: str | None = None
    inventario: list[dict] = []


def _validar(body: CrearPersonaje):
    if body.clase not in CLASES:
        raise HTTPException(400, f"Clase inválida. Opciones: {list(CLASES)}")
    if set(body.atributos) != set(ATRIBUTOS):
        raise HTTPException(400, f"Atributos requeridos: {ATRIBUTOS}")
    for k, v in body.atributos.items():
        if not (3 <= v <= 18):
            raise HTTPException(400, f"{k}={v} fuera de rango (3-18 en creación)")
    for h in body.habilidades:
        if h not in HABILIDADES:
            raise HTTPException(400, f"Habilidad inválida: {h}")
    if body.armadura and body.armadura not in ARMADURAS:
        raise HTTPException(400, f"Armadura inválida. Opciones: {list(ARMADURAS)}")
    if body.arma_equipada and body.arma_equipada not in ARMAS:
        raise HTTPException(400, f"Arma inválida. Opciones: {list(ARMAS)}")


@router.post("")
async def crear_personaje(body: CrearPersonaje,
                          player: Player = Depends(jugador_actual),
                          db: AsyncSession = Depends(get_db)):
    _validar(body)
    existente = await db.execute(
        select(Character).where(Character.player_id == player.id))
    if existente.scalar_one_or_none():
        raise HTTPException(409, "Ya tenés un personaje en esta campaña")

    info = CLASES[body.clase]
    dado = info["dado_golpe"]                      # "d10"
    pg_max = int(dado[1:]) + mod(body.atributos["CON"])  # máx del dado + CON (nivel 1)

    # salvaciones por clase (simplificación 5e estándar)
    SALVACIONES = {
        "barbaro": ["FUE", "CON"], "guerrero": ["FUE", "CON"],
        "paladin": ["SAB", "CAR"], "ranger": ["FUE", "DES"],
        "clerigo": ["SAB", "CAR"], "druida": ["INT", "SAB"],
        "bardo": ["DES", "CAR"], "monje": ["FUE", "DES"],
        "picaro": ["DES", "INT"], "hechicero": ["CON", "CAR"],
        "mago": ["INT", "SAB"], "brujo": ["SAB", "CAR"],
    }
    ARMAS_COMP = {
        "barbaro": ["simple", "marcial"], "guerrero": ["simple", "marcial"],
        "paladin": ["simple", "marcial"], "ranger": ["simple", "marcial"],
        "clerigo": ["simple"], "druida": ["simple"],
        "bardo": ["simple"], "monje": ["simple"],
        "picaro": ["simple"], "hechicero": ["simple"],
        "mago": ["simple"], "brujo": ["simple"],
    }
    ARMADURAS_COMP = {
        "barbaro": ["ligera", "media", "escudo"],
        "guerrero": ["ligera", "media", "pesada", "escudo"],
        "paladin": ["ligera", "media", "pesada", "escudo"],
        "ranger": ["ligera", "media", "escudo"],
        "clerigo": ["ligera", "media", "escudo"],
        "druida": ["ligera", "media", "escudo"],
        "bardo": ["ligera"], "monje": [], "picaro": ["ligera"],
        "hechicero": [], "mago": [], "brujo": ["ligera"],
    }

    char = Character(
        campaign_id=player.campaign_id, player_id=player.id,
        nombre=body.nombre, raza=body.raza, clase=body.clase,
        atributos=body.atributos,
        pg_actual=max(1, pg_max), pg_max=max(1, pg_max),
        dado_golpe=dado, dados_golpe_disp=1,
        competencias={
            "habilidades": body.habilidades[:4],
            "salvaciones": SALVACIONES[body.clase],
            "armas": ARMAS_COMP[body.clase],
            "armaduras": ARMADURAS_COMP[body.clase],
        },
        armadura=body.armadura, escudo=body.escudo,
        arma_equipada=body.arma_equipada,
        inventario=body.inventario,
        slots=slots_iniciales(body.clase, 1),
        conocidos=body.conocidos, preparados=body.preparados,
    )
    db.add(char)
    await db.commit()
    return {"character_id": char.id, "pg_max": char.pg_max,
            "ca": calcular_ca(hidratar_personaje(char))}


@router.get("/{character_id}/sheet")
async def ficha(character_id: int, player: Player = Depends(jugador_actual),
                db: AsyncSession = Depends(get_db)):
    c = await db.get(Character, character_id)
    if c is None or c.campaign_id != player.campaign_id:
        raise HTTPException(404, "Personaje no encontrado en tu campaña")
    cr = hidratar_personaje(c)
    return {
        "id": c.id, "nombre": c.nombre, "raza": c.raza, "clase": c.clase,
        "nivel": c.nivel, "xp": c.xp, "nivel_por_xp": nivel_por_xp(c.xp),
        "pg_actual": c.pg_actual, "pg_max": c.pg_max,
        "ca": calcular_ca(cr), "velocidad_m": c.velocidad_m,
        "iniciativa_mod": mod(c.atributos["DES"]),
        "bc": bc(c.nivel),
        "atributos": {k: {"valor": v, "mod": mod(v)} for k, v in c.atributos.items()},
        "competencias": c.competencias,
        "condiciones": c.condiciones,
        "dado_golpe": c.dado_golpe, "dados_golpe_disp": c.dados_golpe_disp,
        "armadura": c.armadura, "escudo": c.escudo,
        "arma_equipada": c.arma_equipada,
        "inventario": c.inventario, "monedas": c.monedas,
        "slots": c.slots, "conocidos": c.conocidos, "preparados": c.preparados,
        "concentracion": c.concentracion,
        "vivo": c.vivo,
    }
