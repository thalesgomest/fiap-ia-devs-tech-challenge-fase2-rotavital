"""Carregamento, validação e importação de cenários.

Um cenário é um arquivo JSON em ``scenarios/`` com chaves em português. Para adaptar o
sistema a um caso novo basta criar outro arquivo (ou importar um CSV de paradas pela
interface) - nenhum código precisa ser alterado.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Dict, List, Optional

from rotavital.config import settings
from rotavital.domain.models import (
    DEFAULT_PRIORITIES,
    Depot,
    PriorityRule,
    Scenario,
    Stop,
    VehicleType,
    hhmm_to_min,
    min_to_hhmm,
)


class ScenarioError(ValueError):
    """Cenário inválido ou inviável."""


CSV_COLUMNS = [
    "id",
    "nome",
    "tipo",
    "lat",
    "lon",
    "demanda_kg",
    "prioridade",
    "refrigerado",
    "janela_inicio",
    "janela_fim",
    "tempo_servico_min",
    "carga",
]


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "sim", "s", "yes", "y")


def _parse_stop(raw: dict) -> Stop:
    return Stop(
        id=str(raw["id"]),
        name=str(raw["nome"]),
        kind=str(raw.get("tipo", "hospital")),
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        demand_kg=float(raw["demanda_kg"]),
        priority=str(raw.get("prioridade", "rotina")).strip().lower(),
        refrigerated=_as_bool(raw.get("refrigerado", False)),
        window_start=hhmm_to_min(str(raw.get("janela_inicio", "07:00"))),
        window_end=hhmm_to_min(str(raw.get("janela_fim", "18:00"))),
        service_min=int(float(raw.get("tempo_servico_min", 10))),
        cargo=str(raw.get("carga", "")),
    )


def _parse_vehicle(raw: dict) -> VehicleType:
    return VehicleType(
        code=str(raw["codigo"]),
        name=str(raw["nome"]),
        quantity=int(raw["quantidade"]),
        capacity_kg=float(raw["capacidade_kg"]),
        range_km=float(raw["autonomia_km"]),
        speed_kmh=float(raw["velocidade_kmh"]),
        refrigerated=_as_bool(raw.get("refrigerado", False)),
        fixed_cost=float(raw.get("custo_fixo", 0.0)),
        cost_per_km=float(raw.get("custo_km", 1.0)),
        max_shift_min=int(raw.get("jornada_max_min", 600)),
        co2_kg_per_km=float(raw.get("co2_kg_km", 0.2)),
    )


def _parse_priorities(raw: Optional[dict]) -> Dict[str, PriorityRule]:
    if not raw:
        return dict(DEFAULT_PRIORITIES)
    rules = {}
    for rank, (code, item) in enumerate(raw.items()):
        sla = item.get("sla_min")
        rules[code] = PriorityRule(
            code=code,
            label=item.get("rotulo", code.title()),
            sla_min=int(sla) if sla is not None else None,
            late_penalty_per_min=float(item.get("multa_min", 1.0)),
            rank=int(item.get("ordem", rank)),
        )
    return rules


def scenario_from_dict(data: dict) -> Scenario:
    try:
        depot_raw = data["deposito"]
        scenario = Scenario(
            id=str(data["id"]),
            name=str(data["nome"]),
            description=str(data.get("descricao", "")),
            depot=Depot(
                name=depot_raw["nome"],
                lat=float(depot_raw["lat"]),
                lon=float(depot_raw["lon"]),
            ),
            stops=[_parse_stop(s) for s in data["paradas"]],
            fleet=[_parse_vehicle(v) for v in data["frota"]],
            shift_start=hhmm_to_min(data.get("inicio_turno", "07:00")),
            circuity=float(data.get("fator_sinuosidade", 1.35)),
            priorities=_parse_priorities(data.get("prioridades")),
            fleet_excess_penalty=float(data.get("multa_veiculo_excedente", 2500.0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ScenarioError(f"Cenário mal formado: {exc}") from exc
    validate_scenario(scenario)
    return scenario


def scenario_to_file_dict(scenario: Scenario) -> dict:
    """Serializa no mesmo formato (chaves em português) usado pelos arquivos."""
    return {
        "id": scenario.id,
        "nome": scenario.name,
        "descricao": scenario.description,
        "inicio_turno": min_to_hhmm(scenario.shift_start),
        "fator_sinuosidade": scenario.circuity,
        "multa_veiculo_excedente": scenario.fleet_excess_penalty,
        "deposito": {
            "nome": scenario.depot.name,
            "lat": scenario.depot.lat,
            "lon": scenario.depot.lon,
        },
        "prioridades": {
            code: {
                "rotulo": rule.label,
                "sla_min": rule.sla_min,
                "multa_min": rule.late_penalty_per_min,
                "ordem": rule.rank,
            }
            for code, rule in scenario.priorities.items()
        },
        "frota": [
            {
                "codigo": v.code,
                "nome": v.name,
                "quantidade": v.quantity,
                "capacidade_kg": v.capacity_kg,
                "autonomia_km": v.range_km,
                "velocidade_kmh": v.speed_kmh,
                "refrigerado": v.refrigerated,
                "custo_fixo": v.fixed_cost,
                "custo_km": v.cost_per_km,
                "jornada_max_min": v.max_shift_min,
                "co2_kg_km": v.co2_kg_per_km,
            }
            for v in scenario.fleet
        ],
        "paradas": [
            {
                "id": s.id,
                "nome": s.name,
                "tipo": s.kind,
                "lat": s.lat,
                "lon": s.lon,
                "demanda_kg": s.demand_kg,
                "prioridade": s.priority,
                "refrigerado": s.refrigerated,
                "janela_inicio": min_to_hhmm(s.window_start),
                "janela_fim": min_to_hhmm(s.window_end),
                "tempo_servico_min": s.service_min,
                "carga": s.cargo,
            }
            for s in scenario.stops
        ],
    }


def validate_scenario(scenario: Scenario) -> None:
    """Rejeita cenários sem solução possível antes de rodar o otimizador."""
    errors: List[str] = []
    if not scenario.stops:
        errors.append("o cenário não tem paradas")
    if not scenario.fleet:
        errors.append("o cenário não tem veículos")
    ids = [s.id for s in scenario.stops]
    if len(ids) != len(set(ids)):
        errors.append("há paradas com id repetido")
    for stop in scenario.stops:
        if stop.priority not in scenario.priorities:
            errors.append(f"{stop.name}: prioridade desconhecida '{stop.priority}'")
        if stop.window_end < stop.window_start:
            errors.append(f"{stop.name}: janela termina antes de começar")
        if stop.demand_kg <= 0:
            errors.append(f"{stop.name}: demanda deve ser positiva")
        compatible = [
            v
            for v in scenario.fleet
            if v.capacity_kg >= stop.demand_kg and (v.refrigerated or not stop.refrigerated)
        ]
        if not compatible:
            errors.append(
                f"{stop.name}: nenhum veículo comporta {stop.demand_kg:g} kg"
                + (" refrigerados" if stop.refrigerated else "")
            )
    if errors:
        raise ScenarioError("; ".join(errors))


def stops_from_csv(content: str) -> List[dict]:
    """Lê um CSV (separador , ou ;) com as colunas de ``CSV_COLUMNS``."""
    sample = content[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    missing = [c for c in ("id", "nome", "lat", "lon", "demanda_kg") if c not in (reader.fieldnames or [])]
    if missing:
        raise ScenarioError(f"CSV sem colunas obrigatórias: {', '.join(missing)}")
    rows = []
    for row in reader:
        clean = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        for key in ("lat", "lon", "demanda_kg"):
            clean[key] = clean[key].replace(",", ".")
        rows.append(clean)
    return rows


def scenarios_dir() -> Path:
    return settings.scenarios_dir


def list_scenarios() -> List[dict]:
    items = []
    for path in sorted(scenarios_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "id": data.get("id", path.stem),
                "nome": data.get("nome", path.stem),
                "descricao": data.get("descricao", ""),
                "paradas": len(data.get("paradas", [])),
                "veiculos": sum(int(v.get("quantidade", 0)) for v in data.get("frota", [])),
            }
        )
    return items


def load_scenario(scenario_id: str) -> Scenario:
    for path in scenarios_dir().glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("id", path.stem) == scenario_id:
            return scenario_from_dict(data)
    raise ScenarioError(f"Cenário '{scenario_id}' não encontrado")


def save_scenario(scenario: Scenario) -> Path:
    path = scenarios_dir() / f"{scenario.id}.json"
    path.write_text(
        json.dumps(scenario_to_file_dict(scenario), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
