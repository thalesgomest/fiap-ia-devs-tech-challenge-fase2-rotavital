"""Entidades do domínio: depósito, paradas, frota e regras de prioridade.

Todas as grandezas de tempo são em MINUTOS a partir da meia-noite (ex.: 07:00 = 420)
e todas as distâncias em quilômetros. Manter uma única unidade evita a classe de bug
em que SLA e tempo acumulado são comparados em unidades diferentes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


def hhmm_to_min(value: str) -> int:
    """Converte "HH:MM" em minutos desde a meia-noite."""
    hours, minutes = value.strip().split(":")
    return int(hours) * 60 + int(minutes)


def min_to_hhmm(value: float) -> str:
    """Converte minutos desde a meia-noite em "HH:MM" (arredondado)."""
    total = int(round(value))
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


@dataclass(frozen=True)
class PriorityRule:
    """Regra de nível de serviço associada a uma prioridade."""

    code: str
    label: str
    sla_min: Optional[int]  # prazo máximo a partir do início do turno (None = só janela)
    late_penalty_per_min: float  # R$ por minuto de atraso
    rank: int  # 0 = mais urgente


DEFAULT_PRIORITIES: Dict[str, PriorityRule] = {
    "critica": PriorityRule("critica", "Crítica", 120, 40.0, 0),
    "alta": PriorityRule("alta", "Alta", 240, 10.0, 1),
    "rotina": PriorityRule("rotina", "Rotina", None, 1.5, 2),
}


@dataclass(frozen=True)
class Depot:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Stop:
    """Ponto de entrega (hospital, UBS, laboratório ou paciente domiciliar)."""

    id: str
    name: str
    kind: str
    lat: float
    lon: float
    demand_kg: float
    priority: str
    refrigerated: bool
    window_start: int
    window_end: int
    service_min: int
    cargo: str = ""


@dataclass(frozen=True)
class VehicleType:
    """Tipo de veículo da frota (a frota é heterogênea)."""

    code: str
    name: str
    quantity: int
    capacity_kg: float
    range_km: float
    speed_kmh: float
    refrigerated: bool
    fixed_cost: float
    cost_per_km: float
    max_shift_min: int
    co2_kg_per_km: float = 0.2


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    depot: Depot
    stops: List[Stop]
    fleet: List[VehicleType]
    shift_start: int = 7 * 60
    circuity: float = 1.35  # fator rodovia/linha reta
    priorities: Dict[str, PriorityRule] = field(
        default_factory=lambda: dict(DEFAULT_PRIORITIES)
    )
    fleet_excess_penalty: float = 2500.0  # R$ por veículo além do disponível

    def deadline(self, stop: Stop) -> int:
        """Horário limite efetivo: o menor entre fim da janela e o SLA da prioridade.

        Entregas agendadas cuja janela só abre depois do SLA (ex.: visita domiciliar
        marcada para a tarde) seguem a janela combinada - caso contrário nasceriam
        atrasadas por definição.
        """
        rule = self.priorities[stop.priority]
        if rule.sla_min is None:
            return stop.window_end
        sla_deadline = self.shift_start + rule.sla_min
        if sla_deadline < stop.window_start:
            return stop.window_end
        return min(stop.window_end, sla_deadline)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["shift_start"] = min_to_hhmm(self.shift_start)
        for stop in data["stops"]:
            stop["window_start"] = min_to_hhmm(stop["window_start"])
            stop["window_end"] = min_to_hhmm(stop["window_end"])
        for vehicle in data["fleet"]:
            vehicle["max_shift_min"] = int(vehicle["max_shift_min"])
        return data
