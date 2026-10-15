"""Orquestra uma execução completa: baselines -> GA -> solução detalhada -> histórico.

Roda em thread de fundo para que a API possa expor o progresso em tempo real.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Dict, List, Optional

from rotavital.domain.models import Scenario, min_to_hhmm
from rotavital.optimization.baselines import run_baselines
from rotavital.optimization.evaluator import RouteEvaluator
from rotavital.optimization.ga import GAConfig, GeneticOptimizer, Snapshot
from rotavital.storage.history import HistoryStore


def scenario_summary(scenario: Scenario) -> dict:
    return {
        "id": scenario.id,
        "nome": scenario.name,
        "descricao": scenario.description,
        "inicio_turno": min_to_hhmm(scenario.shift_start),
        "deposito": {
            "nome": scenario.depot.name,
            "lat": scenario.depot.lat,
            "lon": scenario.depot.lon,
        },
        "frota": [
            {
                "codigo": v.code,
                "nome": v.name,
                "quantidade": v.quantity,
                "capacidade_kg": v.capacity_kg,
                "autonomia_km": v.range_km,
                "refrigerado": v.refrigerated,
                "custo_fixo": v.fixed_cost,
                "custo_km": v.cost_per_km,
                "jornada_max_min": v.max_shift_min,
            }
            for v in scenario.fleet
        ],
        "prioridades": {
            code: {"rotulo": r.label, "sla_min": r.sla_min, "multa_min": r.late_penalty_per_min}
            for code, r in scenario.priorities.items()
        },
        "paradas": [
            {
                "id": s.id,
                "nome": s.name,
                "tipo": s.kind,
                "lat": s.lat,
                "lon": s.lon,
                "prioridade": s.priority,
                "refrigerado": s.refrigerated,
                "demanda_kg": s.demand_kg,
            }
            for s in scenario.stops
        ],
    }


def apply_fleet_override(scenario: Scenario, fleet: Optional[List[dict]]) -> Scenario:
    """Permite ajustar a frota pela interface sem editar o arquivo do cenário."""
    if not fleet:
        return scenario
    by_code = {item["codigo"]: item for item in fleet}
    mapping = {
        "quantidade": "quantity",
        "capacidade_kg": "capacity_kg",
        "autonomia_km": "range_km",
        "velocidade_kmh": "speed_kmh",
        "custo_fixo": "fixed_cost",
        "custo_km": "cost_per_km",
        "jornada_max_min": "max_shift_min",
    }
    new_fleet = []
    for vehicle in scenario.fleet:
        item = by_code.get(vehicle.code)
        if item:
            changes = {attr: type(getattr(vehicle, attr))(item[key]) for key, attr in mapping.items() if key in item}
            vehicle = replace(vehicle, **changes)
        new_fleet.append(vehicle)
    return replace(scenario, fleet=new_fleet)


def _route_preview(evaluator: RouteEvaluator, tour: List[int]) -> List[dict]:
    scenario = evaluator.scenario
    preview = []
    used: Dict[int, int] = {}
    for t, nodes in evaluator.decode(tour):
        used[t] = used.get(t, 0) + 1
        preview.append(
            {
                "veiculo": f"{evaluator.types[t].code} #{used[t]}",
                "tipo": evaluator.types[t].code,
                "paradas": [scenario.stops[n - 1].id for n in nodes],
            }
        )
    return preview


class Job:
    def __init__(self, scenario: Scenario, config: GAConfig):
        self.id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.scenario = scenario
        self.config = config
        self.status = "executando"
        self.error: Optional[str] = None
        self.progress: dict = {"geracao": 0, "total": config.generations}
        self.history: List[dict] = []
        self.baselines: List[dict] = []
        self.result: Optional[dict] = None
        self.optimizer: Optional[GeneticOptimizer] = None
        self.lock = threading.Lock()

    def snapshot(self, since: int = 0) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "status": self.status,
                "erro": self.error,
                "progresso": dict(self.progress),
                "historico": self.history[since:],
                "baselines": [
                    {k: v for k, v in b.items() if k != "_routes"} for b in self.baselines
                ],
            }


class JobManager:
    def __init__(self, store: HistoryStore):
        self.store = store
        self.jobs: Dict[str, Job] = {}

    def start(self, scenario: Scenario, config: GAConfig) -> Job:
        job = Job(scenario, config)
        self.jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def stop(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job and job.optimizer:
            job.optimizer.stop()
            return True
        return False

    def _run(self, job: Job) -> None:
        try:
            evaluator = RouteEvaluator(job.scenario)
            baselines = run_baselines(evaluator)
            with job.lock:
                job.baselines = baselines

            job.optimizer = GeneticOptimizer(evaluator, job.config)

            def on_progress(snap: Snapshot) -> None:
                preview = _route_preview(evaluator, snap.best_tour) if snap.best_tour else []
                with job.lock:
                    job.progress = {
                        "geracao": snap.generation,
                        "total": job.config.generations,
                        "melhor": round(snap.best_cost, 2),
                        "media": round(snap.avg_cost, 2),
                        "diversidade": round(snap.diversity, 3),
                        "mutacao": round(snap.mutation_rate, 3),
                        "tempo_s": round(snap.elapsed_s, 1),
                        "rotas": preview,
                    }
                    job.history.append(
                        {
                            "geracao": snap.generation,
                            "melhor": round(snap.best_cost, 2),
                            "media": round(snap.avg_cost, 2),
                            "diversidade": round(snap.diversity, 3),
                        }
                    )

            result = job.optimizer.run(on_progress=on_progress)
            solution = evaluator.solution_from_tour(result.best_tour)
            best_baseline = min(baselines, key=lambda b: b["custo_total"])
            saving = best_baseline["custo_total"] - solution["custo_total"]
            run = {
                "id": job.id,
                "criado_em": datetime.now().isoformat(timespec="seconds"),
                "cenario": scenario_summary(job.scenario),
                "ga": {
                    "config": job.config.to_dict(),
                    "geracoes": result.generations,
                    "motivo_parada": result.stop_reason,
                    "tempo_s": result.elapsed_s,
                    "avaliacoes": result.evaluations,
                    "historico": result.history,
                },
                "solucao": solution,
                "baselines": [{k: v for k, v in b.items() if k != "_routes"} for b in baselines],
                "comparativo": {
                    "melhor_baseline": best_baseline["nome"],
                    "custo_baseline": best_baseline["custo_total"],
                    "economia_rs": round(saving, 2),
                    "economia_pct": round(saving / best_baseline["custo_total"] * 100, 1)
                    if best_baseline["custo_total"]
                    else 0.0,
                },
            }
            self.store.save_run(run)
            with job.lock:
                job.result = run
                job.history = result.history
                job.status = "interrompido" if result.stop_reason == "interrompido" else "concluido"
        except Exception as exc:  # noqa: BLE001 - erro precisa chegar à interface
            traceback.print_exc()
            with job.lock:
                job.status = "erro"
                job.error = str(exc)
