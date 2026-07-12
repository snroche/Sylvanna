from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
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
    raza: str                        # clave de engine.content.RAZAS
    subraza: str | None = None
    clase: str
    genero: str | None = None        # flavor para la descripción (libre)
    metodo: str = "libre"            # "puntos" (point buy 27) | "libre"
    atributos: dict[str, int]        # BASE, sin bonos raciales (los aplica el server)
    bonos_eleccion: list[str] = []   # semielfo: 2 atributos para el +1
    habilidades: list[str] = []
    conocidos: list[str] = []
    preparados: list[str] = []
    armadura: str | None = None
    escudo: bool = False
    arma_equipada: str | None = None
    alineamiento: str = "neutral"
    estilo_combate: str | None = None   # solo guerrero
    subclase: str | None = None         # requerida si la clase elige a nivel 1
    trasfondo: str | None = None        # clave de engine.content.TRASFONDOS
    feat: str | None = None             # dote inicial (solo humano variante)
    feat_atributo: str | None = None
    inventario: list[dict] = []


def _validar(body: CrearPersonaje):
    from engine.content import validar_point_buy
    if body.clase not in CLASES:
        raise HTTPException(400, f"Clase inválida. Opciones: {list(CLASES)}")
    if set(body.atributos) != set(ATRIBUTOS):
        raise HTTPException(400, f"Atributos requeridos: {ATRIBUTOS}")
    if body.metodo == "puntos":
        ok, msg = validar_point_buy(body.atributos)
        if not ok:
            raise HTTPException(400, f"Point buy inválido: {msg}")
    elif body.metodo == "libre":
        for k, v in body.atributos.items():
            if not (3 <= v <= 18):
                raise HTTPException(400, f"{k}={v} fuera de rango (3-18)")
    else:
        raise HTTPException(400, "metodo debe ser 'puntos' o 'libre'")
    from engine.content import CLASE_HABILIDADES, CLASE_HABILIDADES_N
    lista_clase = CLASE_HABILIDADES.get(body.clase, [])
    n_clase = CLASE_HABILIDADES_N.get(body.clase, 2)
    elegidas = list(dict.fromkeys(body.habilidades))
    for h in elegidas:
        if h not in HABILIDADES:
            raise HTTPException(400, f"Habilidad inválida: {h}")
        if lista_clase and h not in lista_clase:
            raise HTTPException(400, f"{h.replace('_', ' ')} no está en la lista "
                                     f"de habilidades del {body.clase}")
    if len(elegidas) > n_clase:
        raise HTTPException(400, f"El {body.clase} elige {n_clase} habilidades "
                                 f"(mandaste {len(elegidas)})")
    if body.armadura and body.armadura not in ARMADURAS:
        raise HTTPException(400, f"Armadura inválida. Opciones: {list(ARMADURAS)}")
    if body.arma_equipada and body.arma_equipada not in ARMAS:
        raise HTTPException(400, f"Arma inválida. Opciones: {list(ARMAS)}")
    # Competencia: no podés equipar armas/armaduras que tu clase no domina
    from engine.content import (competencias_de_clase, puede_usar_arma,
                                puede_usar_armadura, puede_usar_escudo)
    comp = competencias_de_clase(body.clase)
    if body.arma_equipada and not puede_usar_arma(comp, body.arma_equipada):
        raise HTTPException(400, f"Tu clase ({body.clase}) no es competente con "
                                 f"{body.arma_equipada.replace('_', ' ')}")
    if body.armadura and not puede_usar_armadura(comp, body.armadura):
        raise HTTPException(400, f"Tu clase ({body.clase}) no sabe usar "
                                 f"{body.armadura.replace('_', ' ')}")
    if body.escudo and not puede_usar_escudo(comp):
        raise HTTPException(400, f"Tu clase ({body.clase}) no sabe usar escudo")
    from engine.content import ALINEAMIENTOS, ESTILOS_COMBATE, TRASFONDOS
    if body.alineamiento not in ALINEAMIENTOS:
        raise HTTPException(400, f"Alineamiento inválido: {ALINEAMIENTOS}")
    if body.trasfondo and body.trasfondo not in TRASFONDOS:
        raise HTTPException(400, f"Trasfondo inválido. Opciones: "
                                 f"{list(TRASFONDOS)}")
    from engine.content import NIVEL_SUBCLASE, SUBCLASES_SRD
    if NIVEL_SUBCLASE.get(body.clase) == 1:
        if not (body.subclase or "").strip():
            raise HTTPException(400, f"{body.clase} elige subclase a nivel 1. "
                                     f"Del SRD: {SUBCLASES_SRD[body.clase]} "
                                     f"(o texto libre)")
    if body.clase == "guerrero":
        if body.estilo_combate not in ESTILOS_COMBATE:
            raise HTTPException(400, "El guerrero elige estilo de combate: "
                                     f"{list(ESTILOS_COMBATE)}")
    elif body.estilo_combate:
        raise HTTPException(400, "Solo el guerrero tiene estilo de combate (v1)")

    # Conjuros: solo trucos y nivel 1 en creación, y solo los que la clase (o
    # la raza, p. ej. alto elfo con un truco de mago) puede aprender.
    from engine.content import (CONJUROS, clases_de_conjuro,
                                puede_aprender_conjuro)
    raza_truco_mago = body.subraza in ("alto_elfo", "descendiente_alto_elfo")
    for c in dict.fromkeys((body.conocidos or []) + (body.preparados or [])):
        info = CONJUROS.get(c)
        if info is None:
            raise HTTPException(400, f"Conjuro desconocido: {c}")
        if info["nivel"] > 1:
            raise HTTPException(400, f"En creación solo trucos y conjuros de "
                                     f"nivel 1 ({c.replace('_', ' ')})")
        ok = puede_aprender_conjuro(body.clase, c)
        if not ok and raza_truco_mago and info["nivel"] == 0 \
                and "mago" in clases_de_conjuro(info):
            ok = True   # truco de mago del alto elfo
        if not ok:
            raise HTTPException(400, f"Tu clase/raza no puede aprender "
                                     f"{c.replace('_', ' ')}")


def _inventario_inicial(body: "CrearPersonaje") -> list[dict]:
    """Equipo base: lo elegido + kit de aventurero estándar."""
    inv = list(body.inventario)
    def agregar(nombre, cant=1):
        ex = next((x for x in inv if x.get("nombre") == nombre), None)
        if ex:
            ex["cantidad"] = ex.get("cantidad", 1) + cant
        else:
            inv.append({"nombre": nombre, "cantidad": cant})
    if body.arma_equipada:
        agregar(body.arma_equipada)
    if body.armadura:
        agregar(body.armadura)
    agregar("pocion_de_curacion", 2)
    agregar("antorcha", 3)
    agregar("racion", 5)
    return inv


@router.post("")
async def crear_personaje(body: CrearPersonaje, bg: BackgroundTasks,
                          player: Player = Depends(jugador_actual),
                          db: AsyncSession = Depends(get_db)):
    _validar(body)
    from engine.content import aplicar_bonos_raciales
    try:
        atributos_finales, velocidad, rasgos = aplicar_bonos_raciales(
            body.atributos, body.raza, body.subraza, body.bonos_eleccion)
    except ValueError as e:
        raise HTTPException(400, str(e))
    existente = await db.execute(
        select(Character).where(Character.player_id == player.id,
                                Character.vivo == True))  # noqa: E712
    if existente.scalars().first():
        raise HTTPException(409, "Ya tenés un personaje VIVO en esta campaña")

    info = CLASES[body.clase]
    dado = info["dado_golpe"]                      # "d10"
    pg_max = int(dado[1:]) + mod(atributos_finales["CON"])
    if body.subraza == "enano_de_las_colinas":
        pg_max += 1  # +1 PG por nivel
    if body.clase == "hechicero" and \
            (body.subclase or "").strip() == "linaje_draconico":
        pg_max += 1  # resiliencia dracónica

    # competencias por clase (fuente única en engine.content)
    from engine.content import competencias_de_clase
    comp_clase = competencias_de_clase(body.clase)

    # Trasfondo: competencias, equipo, oro inicial y rasgo narrativo
    from engine.content import CLASE_HABILIDADES_N, TRASFONDOS
    tras = TRASFONDOS.get(body.trasfondo) if body.trasfondo else None
    n_clase = CLASE_HABILIDADES_N.get(body.clase, 2)
    # habilidades del PJ = las elegidas de la clase (tope por clase) + las del
    # trasfondo (forzadas por el PHB, p. ej. soldado → atletismo + intimidación)
    habilidades = list(dict.fromkeys(
        list(dict.fromkeys(body.habilidades))[:n_clase]
        + (tras["competencias"] if tras else [])))
    inventario = _inventario_inicial(body)
    # riqueza inicial: la de la clase (PHB) + la del trasfondo
    from engine.content import oro_inicial_clase
    monedas = {"mo": oro_inicial_clase(body.clase), "mp": 0, "mc": 0}
    opciones = {}
    if tras:
        for item in tras.get("equipo", []):
            ex = next((x for x in inventario
                       if x.get("nombre") == item["nombre"]), None)
            if ex:
                ex["cantidad"] = ex.get("cantidad", 1) + item.get("cantidad", 1)
            else:
                inventario.append(dict(item))
        monedas["mo"] += tras.get("oro", 0)
        opciones = {"trasfondo": body.trasfondo,
                    "rasgo_trasfondo": tras["rasgo"],
                    "rasgo_trasfondo_desc": tras["rasgo_desc"]}

    char = Character(
        campaign_id=player.campaign_id, player_id=player.id,
        nombre=body.nombre,
        raza=body.raza + (f" ({body.subraza})" if body.subraza else ""),
        clase=body.clase,
        genero=(body.genero or "").strip()[:20],
        atributos=atributos_finales,
        velocidad_m=velocidad,
        pg_actual=max(1, pg_max), pg_max=max(1, pg_max),
        dado_golpe=dado, dados_golpe_disp=1,
        competencias={
            "habilidades": habilidades,
            "salvaciones": comp_clase["salvaciones"],
            "armas": comp_clase["armas"],
            "armaduras": comp_clase["armaduras"],
        },
        armadura=body.armadura, escudo=body.escudo,
        arma_equipada=body.arma_equipada,
        inventario=inventario,
        monedas=monedas,
        opciones_clase=opciones,
        slots=slots_iniciales(body.clase, 1),
        conocidos=body.conocidos, preparados=body.preparados,
        alineamiento=body.alineamiento,
        estilo_combate=body.estilo_combate,
        subclase=(body.subclase or "").strip()[:60] or None,
        recursos_clase={
            **__import__("engine.content", fromlist=["x"])
                .recursos_clase_iniciales(body.clase, 1,
                                          mod(atributos_finales["CAR"])),
            **__import__("engine.content", fromlist=["x"])
                .recursos_raciales(body.raza + (f" ({body.subraza})"
                                                if body.subraza else ""), 1),
        },
    )
    # Dote inicial: solo el humano variante la tiene a nivel 1
    if body.feat:
        if not (body.raza == "humano" and body.subraza == "variante"):
            raise HTTPException(400, "Solo el humano variante recibe una dote "
                                     "inicial a nivel 1")
        from ..feats import aplicar_feat
        try:
            aplicar_feat(char, body.feat, body.feat_atributo)
        except ValueError as e:
            raise HTTPException(400, str(e))
    # el monje pelea con artes marciales por defecto
    if body.clase == "monje" and not body.arma_equipada:
        char.arma_equipada = "artes_marciales"
    # ¿es el primer personaje de la campaña? → el DM abre la escena
    otros = await db.execute(select(Character).where(
        Character.campaign_id == player.campaign_id))
    es_primero = otros.scalars().first() is None

    db.add(char)
    await db.flush()
    if es_primero:
        from ..models import Campaign
        from .actions import encolar_narracion
        camp = await db.get(Campaign, player.campaign_id)
        encolar_narracion(
            bg, camp,
            f"APERTURA DE CAMPAÑA. Es el primer momento de juego. "
            f"Presentá la escena inicial: dónde se encuentra {char.nombre} "
            f"({char.raza} {char.clase}), qué ve, qué se siente en el aire, y "
            f"un gancho concreto que invite a actuar. Respetá la ambientación. "
            f"Podés declarar nueva_ubicacion en el bloque JSON.",
            char.id)
    else:
        db.add(__import__("app.models", fromlist=["Message"]).Message(
            campaign_id=player.campaign_id, autor="sistema",
            autor_nombre="Sistema",
            contenido=f"🚪 {char.nombre} ({char.raza} {char.clase}) "
                      f"se une a la party."))
    await db.commit()
    return {"character_id": char.id, "pg_max": char.pg_max,
            "ca": calcular_ca(hidratar_personaje(char)),
            "atributos_finales": atributos_finales,
            "velocidad_m": velocidad, "rasgos": rasgos}


def _habilidades_activas(c: Character) -> list[dict]:
    """Botones de habilidad que la UI debe mostrar, con su recurso y estado."""
    rec = c.recursos_clase or {}
    out = []

    def usos(nombre):
        r = rec.get(nombre)
        if r is None:
            return None
        return (r["pool"], r["pool_max"]) if "pool" in r \
            else (r["max"] - r["usados"], r["max"])

    def agregar(nombre, recurso=None, **extra):
        u = usos(recurso) if recurso else None
        out.append({"nombre": nombre, "recurso": recurso,
                    "restante": u[0] if u else None,
                    "max": u[1] if u else None, **extra})

    if c.clase == "barbaro":
        agregar("furia", "furia", combate=True)
        if c.subclase == "senda_del_berserker" and c.nivel >= 3:
            agregar("frenesi", None, combate=True)
    if c.clase == "guerrero":
        agregar("nuevo_aliento", "nuevo_aliento")
        if c.nivel >= 2:
            agregar("oleada_de_accion", "oleada_de_accion", combate=True)
    if c.clase == "monje" and c.nivel >= 2:
        agregar("rafaga_de_golpes", "ki", combate=True)
        agregar("defensa_paciente", "ki", combate=True)
    if c.clase == "druida" and c.nivel >= 2:
        from engine.content import formas_salvajes_disponibles
        transformado = bool((c.recursos_clase or {}).get("_forma_salvaje"))
        agregar("forma_salvaje", "forma_salvaje", combate=True,
                transformado=transformado,
                formas=formas_salvajes_disponibles(c.nivel))
    if c.clase == "clerigo" and c.nivel >= 2:
        agregar("canalizar_divinidad", "canalizar_divinidad", aliado=True)
        agregar("expulsar_no_muertos", "canalizar_divinidad", combate=True)
    if c.clase == "paladin":
        agregar("imposicion_de_manos", "imposicion_de_manos",
                aliado=True, cantidad=True)
        if c.subclase == "juramento_de_devocion" and c.nivel >= 3:
            agregar("arma_sagrada", "canalizar_divinidad", combate=True)
    if c.clase == "bardo":
        agregar("inspiracion_bardica", "inspiracion_bardica",
                aliado=True, requiere_aliado=True)
    if c.clase == "hechicero" and c.nivel >= 2:
        from engine.content import METAMAGIA, metamagias_conocidas_max
        ph = rec.get("puntos_hechiceria", {})
        conocidas = (c.opciones_clase or {}).get("metamagia", [])
        out.append({"nombre": "fuente_de_magia", "recurso": "puntos_hechiceria",
                    "restante": ph.get("pool"), "max": ph.get("pool_max"),
                    "metamagia_conocida": conocidas,
                    "metamagia_max": metamagias_conocidas_max(c.nivel),
                    "metamagia_opciones": {k: v["nombre"]
                                           for k, v in METAMAGIA.items()}})
    from engine.content import aliento_de_raza
    if aliento_de_raza(c.raza):
        agregar("aliento_de_dragon", "aliento_de_dragon",
                combate=True, enemigo=True)
    return out


@router.get("/{character_id}/sheet")
async def ficha(character_id: int, player: Player = Depends(jugador_actual),
                db: AsyncSession = Depends(get_db)):
    c = await db.get(Character, character_id)
    if c is None or c.campaign_id != player.campaign_id:
        raise HTTPException(404, "Personaje no encontrado en tu campaña")
    cr = hidratar_personaje(c)
    return {
        "id": c.id, "nombre": c.nombre, "raza": c.raza, "clase": c.clase,
        "genero": getattr(c, "genero", "") or "",
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
        "alineamiento": c.alineamiento,
        "subclase": c.subclase,
        "estilo_combate": c.estilo_combate,
        "recursos_clase": {k: v for k, v in (c.recursos_clase or {}).items()
                           if not k.startswith("_")},
        "forma_salvaje": (c.recursos_clase or {}).get("_forma_salvaje"),
        "habilidades_activas": _habilidades_activas(c),
        "feats": c.feats or [],
        "opciones_clase": c.opciones_clase or {},
        "vivo": c.vivo,
    }
