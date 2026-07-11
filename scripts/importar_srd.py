"""Importa monstruos y conjuros del SRD 5.1 desde la API de Open5e
(https://open5e.com, contenido CC-BY del SRD de Wizards).

Genera:
    data/monstruos_srd.json
    data/conjuros_srd.json

engine/content.py los mergea automáticamente al arrancar (sin pisar el
contenido curado). Correr desde la raíz del proyecto, con internet:

    pip install httpx
    python scripts/importar_srd.py            # todo
    python scripts/importar_srd.py --cr-max 5 # monstruos hasta CR 5
    python scripts/importar_srd.py --solo monstruos

Los monstruos vienen con estructura mecánica completa (PG, CA, atributos,
ataques con bono y dados). Los conjuros traen nivel/escuela/concentración
seguros, y la resolución mecánica (ataque/salvación/daño) se deduce por
heurística del texto — los que no se pueden deducir quedan como "auto" con
su descripción para que el DM los narre.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import httpx

# Open5e deprecó la v1: ahora requiere el prefijo /v1/ explícito.
# (La v2 cambió el formato de campos; nos quedamos en v1 que sigue online.)
API = "https://api.open5e.com/v1"
RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"

CR_ORDEN = ["0", "1/8", "1/4", "1/2"] + [str(i) for i in range(1, 31)]

# XP por CR (tabla estándar 5e, DMG/SRD)
XP_POR_CR = {
    "0": 10, "1/8": 25, "1/4": 50, "1/2": 100, "1": 200, "2": 450, "3": 700,
    "4": 1100, "5": 1800, "6": 2300, "7": 2900, "8": 3900, "9": 5000,
    "10": 5900, "11": 7200, "12": 8400, "13": 10000, "14": 11500,
    "15": 13000, "16": 15000, "17": 18000, "18": 20000, "19": 22000,
    "20": 25000, "21": 33000, "22": 41000, "23": 50000, "24": 62000,
    "25": 75000, "26": 90000, "27": 105000, "28": 120000, "29": 135000,
    "30": 155000,
}

SALVACIONES_EN = {"strength": "FUE", "dexterity": "DES", "constitution": "CON",
                  "intelligence": "INT", "wisdom": "SAB", "charisma": "CAR"}


def slug(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def paginar(cliente: httpx.Client, url: str):
    while url:
        r = cliente.get(url, timeout=60)
        r.raise_for_status()
        d = r.json()
        yield from d["results"]
        url = d.get("next")


# ---------------------------------------------------------------- monstruos

def importar_monstruos(cliente: httpx.Client, cr_max: str) -> dict:
    limite = CR_ORDEN.index(cr_max)
    salida: dict = {}
    url = f"{API}/monsters/?document__slug=wotc-srd&limit=100"
    for m in paginar(cliente, url):
        cr = str(m.get("challenge_rating", "0"))
        if cr not in CR_ORDEN or CR_ORDEN.index(cr) > limite:
            continue
        ataques = []
        for a in m.get("actions") or []:
            if a.get("attack_bonus") is not None and a.get("damage_dice"):
                # formatos vistos: "1d6+2", "2d8", "4d4 + 4", "1d8+4+2d6"
                dd = str(a["damage_dice"]).replace(" ", "")
                mm = re.match(r"(\d+d\d+)([+-]\d+)?", dd)
                if not mm:
                    continue
                ataques.append({
                    "nombre": a["name"],
                    "bono": int(a["attack_bonus"]),
                    "danio": mm.group(1) + (mm.group(2) or ""),
                })
        clave = slug(m["name"])
        salida[clave] = {
            "nombre": m["name"], "cr": cr,
            "pg": m.get("hit_points", 10),
            "ca_fija": m.get("armor_class", 10),
            "velocidad_m": round((m.get("speed", {}).get("walk", 30) or 30)
                                 * 0.3),
            "atributos": {
                "FUE": m.get("strength", 10), "DES": m.get("dexterity", 10),
                "CON": m.get("constitution", 10),
                "INT": m.get("intelligence", 10),
                "SAB": m.get("wisdom", 10), "CAR": m.get("charisma", 10),
            },
            "ataques": ataques[:3],
            "tipo_criatura": m.get("type", ""),
        }
    return salida


# ---------------------------------------------------------------- conjuros

def deducir_resolucion(desc: str) -> dict:
    """Heurística sobre el texto del conjuro (en inglés, SRD)."""
    d = desc.lower()
    dado = re.search(r"(\d+d\d+)", d)
    danio = dado.group(1) if dado else None
    if "spell attack" in d:
        return {"resolucion": "ataque", "danio": danio or "1d8",
                "tipo_danio": "?"}
    m = re.search(r"(strength|dexterity|constitution|intelligence|wisdom|"
                  r"charisma) saving throw", d)
    if m:
        return {"resolucion": "salvacion",
                "salvacion": SALVACIONES_EN[m.group(1)],
                "danio": danio,
                "en_salvacion_exitosa": "mitad" if "half as much damage" in d
                                        else "nada"}
    if re.search(r"regains? .*hit points|hit points equal", d) and danio:
        return {"resolucion": "curacion", "curacion": danio,
                "suma_mod_magico": True}
    return {"resolucion": "auto"}


def importar_conjuros(cliente: httpx.Client, nivel_max: int) -> dict:
    salida: dict = {}
    url = f"{API}/spells/?document__slug=wotc-srd&limit=100"
    for c in paginar(cliente, url):
        nivel = c.get("level_int", 0)
        if nivel > nivel_max:
            continue
        base = deducir_resolucion(c.get("desc", ""))
        salida[slug(c["name"])] = {
            "nombre": c["name"],
            "nivel": nivel,
            "escuela": c.get("school", ""),
            "concentracion": str(c.get("concentration", "no")).lower() == "yes",
            "clases": [x.strip().lower()
                       for x in (c.get("dnd_class") or "").split(",") if x],
            "descripcion": (c.get("desc") or "")[:600],
            **base,
        }
    return salida


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cr-max", default="30",
                   help="CR máximo de monstruos (default 30 = todos)")
    p.add_argument("--nivel-max", type=int, default=9,
                   help="Nivel máximo de conjuros (default 9 = todos)")
    p.add_argument("--solo", choices=["monstruos", "conjuros", "objetos"],
                   default=None)
    args = p.parse_args()

    if args.cr_max not in CR_ORDEN:
        sys.exit(f"CR inválido: {args.cr_max}")
    DATA.mkdir(exist_ok=True)

    with httpx.Client() as cliente:
        if args.solo in (None, "monstruos"):
            print(f"Importando monstruos hasta CR {args.cr_max}…")
            monstruos = importar_monstruos(cliente, args.cr_max)
            (DATA / "monstruos_srd.json").write_text(
                json.dumps(monstruos, ensure_ascii=False, indent=1),
                encoding="utf-8")
            print(f"  → {len(monstruos)} monstruos en data/monstruos_srd.json")
        if args.solo in (None, "conjuros"):
            print(f"Importando conjuros hasta nivel {args.nivel_max}…")
            conjuros = importar_conjuros(cliente, args.nivel_max)
            (DATA / "conjuros_srd.json").write_text(
                json.dumps(conjuros, ensure_ascii=False, indent=1),
                encoding="utf-8")
            con_mecanica = sum(1 for c in conjuros.values()
                               if c["resolucion"] != "auto")
            print(f"  → {len(conjuros)} conjuros ({con_mecanica} con "
                  f"resolución mecánica deducida)")
        if args.solo in (None, "objetos"):
            print("Importando objetos mágicos…")
            objetos = {}
            for o in paginar(cliente,
                             f"{API}/magicitems/?document__slug=wotc-srd&limit=100"):
                objetos[slug(o["name"])] = {
                    "nombre": o["name"], "tipo": o.get("type", ""),
                    "rareza": o.get("rarity", ""),
                    "descripcion": (o.get("desc") or "")[:400],
                }
            (DATA / "objetos_magicos_srd.json").write_text(
                json.dumps(objetos, ensure_ascii=False, indent=1),
                encoding="utf-8")
            print(f"  → {len(objetos)} objetos mágicos")
    print("Listo. Los archivos se cargan solos al reiniciar el servidor.")


if __name__ == "__main__":
    main()
