"""Aplicación de dotes (feats) a un Character.

Se usa tanto al crear el personaje (humano variante) como al subir de nivel en
los niveles de Mejora de Característica (4/8/12/16/19), donde se puede elegir
una dote en vez del +2 a atributos.
"""
from __future__ import annotations

from engine.content import FEATS
from engine.rules import mod

from .models import Character

_ATRS = ("FUE", "DES", "CON", "INT", "SAB", "CAR")


def aplicar_feat(char: Character, feat_key: str,
                 atributo: str | None = None) -> dict:
    """Valida y aplica una dote al personaje (muta char). Devuelve un resumen.
    Lanza ValueError si la dote no existe, no cumple requisito, ya la tiene o
    falta el atributo elegido."""
    meta = FEATS.get(feat_key)
    if meta is None:
        raise ValueError(f"Dote desconocida: {feat_key}. Opciones: {list(FEATS)}")
    if any((f.get("clave") if isinstance(f, dict) else f) == feat_key
           for f in (char.feats or [])):
        raise ValueError(f"Ya tenés la dote '{meta['nombre']}'")
    for atr, minimo in meta.get("requisito", {}).items():
        if char.atributos.get(atr, 10) < minimo:
            raise ValueError(f"{meta['nombre']} requiere {atr} {minimo}+")

    ef = meta.get("efectos", {})
    atrs = dict(char.atributos)
    resumen = {"clave": feat_key, "nombre": meta["nombre"]}

    # +1 a un atributo a elección
    if "asi_eleccion" in ef:
        if atributo not in ef["asi_eleccion"]:
            raise ValueError(f"{meta['nombre']}: elegí un atributo de "
                             f"{ef['asi_eleccion']}")
        atrs[atributo] = min(20, atrs.get(atributo, 10) + 1)
        resumen["asi"] = {atributo: 1}
    # +n fijo a atributo(s)
    for atr, n in ef.get("asi", {}).items():
        atrs[atr] = min(20, atrs.get(atr, 10) + n)
        resumen.setdefault("asi", {})[atr] = n
    char.atributos = atrs

    comp = {k: list(v) if isinstance(v, list) else v
            for k, v in (char.competencias or {}).items()}
    # competencia en una salvación a elección
    if "competencia_salvacion_eleccion" in ef:
        if atributo not in ef["competencia_salvacion_eleccion"]:
            raise ValueError(f"{meta['nombre']}: elegí un atributo de "
                             f"{ef['competencia_salvacion_eleccion']}")
        salv = list(comp.get("salvaciones", []))
        if atributo not in salv:
            salv.append(atributo)
        comp["salvaciones"] = salv
        resumen["competencia_salvacion"] = atributo
    # competencias de habilidad fijas
    if ef.get("competencias"):
        habs = list(comp.get("habilidades", []))
        for h in ef["competencias"]:
            if h not in habs:
                habs.append(h)
        comp["habilidades"] = habs
    char.competencias = comp

    # PG por nivel (Vigoroso): se aplican retroactivamente a todo el nivel actual
    hp = ef.get("hp_por_nivel", 0)
    if hp:
        ganancia = hp * char.nivel
        char.pg_max += ganancia
        char.pg_actual += ganancia
        resumen["pg_ganados"] = ganancia

    char.feats = list(char.feats or []) + [
        {"clave": feat_key, "atributo": atributo}]
    return resumen
