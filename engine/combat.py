"""Máquina de estados de campaña y motor de turnos de combate.

Combat es una entidad pura (serializable a JSON) que la capa API persiste
en la tabla Combat de la DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .entities import Criatura
from .rules import iniciativa, mod


class CampaignState(str, Enum):
    EXPLORACION = "exploracion"
    COMBATE = "combate"
    DESCANSO = "descanso"
    PAUSADA = "pausada"


TRANSICIONES_VALIDAS = {
    CampaignState.EXPLORACION: {CampaignState.COMBATE, CampaignState.DESCANSO,
                                CampaignState.PAUSADA},
    CampaignState.COMBATE: {CampaignState.EXPLORACION},
    CampaignState.DESCANSO: {CampaignState.EXPLORACION, CampaignState.COMBATE},
    CampaignState.PAUSADA: {CampaignState.EXPLORACION},
}


def validar_transicion(desde: CampaignState, hacia: CampaignState) -> bool:
    return hacia in TRANSICIONES_VALIDAS.get(desde, set())


@dataclass
class Combat:
    ronda: int = 1
    # orden: [{"tipo": "pj"|"npc", "id": str, "init": int, "des": int}]
    orden: list[dict] = field(default_factory=list)
    turno_idx: int = 0
    activo: bool = True
    tiradas_iniciativa: list[dict] = field(default_factory=list)

    @classmethod
    def iniciar(cls, pjs: list[Criatura], npcs: list[Criatura]) -> "Combat":
        """Tira iniciativa por todos y arma el orden de turnos."""
        c = cls()
        entradas = []
        for cr in pjs:
            t = iniciativa(cr)
            c.tiradas_iniciativa.append(t)
            entradas.append({"tipo": "pj", "id": cr.id, "init": t["total"],
                             "des": mod(cr.atributos["DES"])})
        for cr in npcs:
            t = iniciativa(cr)
            c.tiradas_iniciativa.append(t)
            entradas.append({"tipo": "npc", "id": cr.id, "init": t["total"],
                             "des": mod(cr.atributos["DES"])})
        # Orden: init desc → PJ antes que NPC en empate → mayor DES → estable
        entradas.sort(key=lambda e: (-e["init"], 0 if e["tipo"] == "pj" else 1,
                                     -e["des"]))
        c.orden = entradas
        return c

    @property
    def turno_actual(self) -> dict:
        return self.orden[self.turno_idx]

    def es_turno_de(self, criatura_id: str) -> bool:
        return self.activo and self.turno_actual["id"] == criatura_id

    def avanzar_turno(self) -> dict:
        """Pasa al siguiente turno. Devuelve {nueva_ronda: bool, turno: dict}."""
        self.turno_idx += 1
        nueva_ronda = False
        if self.turno_idx >= len(self.orden):
            self.turno_idx = 0
            self.ronda += 1
            nueva_ronda = True
        return {"nueva_ronda": nueva_ronda, "ronda": self.ronda,
                "turno": self.turno_actual}

    def remover(self, criatura_id: str) -> None:
        """Saca a una criatura del orden (muerte, huida). Ajusta el índice."""
        idx = next((i for i, e in enumerate(self.orden) if e["id"] == criatura_id),
                   None)
        if idx is None:
            return
        self.orden.pop(idx)
        if not self.orden:
            self.activo = False
            return
        if idx < self.turno_idx:
            self.turno_idx -= 1
        self.turno_idx %= len(self.orden)

    def npcs_restantes(self) -> list[str]:
        return [e["id"] for e in self.orden if e["tipo"] == "npc"]

    def pjs_restantes(self) -> list[str]:
        return [e["id"] for e in self.orden if e["tipo"] == "pj"]

    def to_dict(self) -> dict:
        return {"ronda": self.ronda, "orden": self.orden,
                "turno_idx": self.turno_idx, "activo": self.activo}

    @classmethod
    def from_dict(cls, d: dict) -> "Combat":
        return cls(ronda=d["ronda"], orden=d["orden"],
                   turno_idx=d["turno_idx"], activo=d["activo"])
