"""Bateria de experimentos: configurações do GA x sementes x heurísticas de referência.

Uso:
    python -m rotavital.optimization.experiments --cenario sp-hemorrede-40 --sementes 5

Gera em ``experiments/<data-hora>/``:
  * resultados.csv  - uma linha por (configuração, semente);
  * resumo.md       - tabela média ± desvio padrão pronta para o relatório técnico;
  * convergencia.json - curvas de convergência para gráficos.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from rotavital.config import PROJECT_ROOT
from rotavital.domain.scenarios import load_scenario
from rotavital.optimization.baselines import run_baselines
from rotavital.optimization.evaluator import RouteEvaluator
from rotavital.optimization.ga import GAConfig, GeneticOptimizer

BASE = GAConfig(generations=400, stagnation_limit=120, time_limit_s=300)

EXPERIMENTS: Dict[str, GAConfig] = {
    "E1-base (pop 120, OX, mut 0.25)": BASE,
    "E2-populacao-pequena (pop 40)": replace(BASE, population_size=40),
    "E3-populacao-grande (pop 250)": replace(BASE, population_size=250),
    "E4-mutacao-alta (0.6)": replace(BASE, mutation_rate=0.6),
    "E5-cruzamento-PMX": replace(BASE, crossover="pmx"),
    "E6-cruzamento-ERX": replace(BASE, crossover="erx"),
    "E7-sem-busca-local": replace(BASE, local_search_every=0),
    "E8-sem-sementes-heuristicas": replace(BASE, seed_ratio=0.0),
}


def run_experiments(scenario_id: str, seeds: int, only: List[str] = None) -> Path:
    scenario = load_scenario(scenario_id)
    out_dir = PROJECT_ROOT / "experiments" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, curves = [], {}
    evaluator = RouteEvaluator(scenario)
    for b in run_baselines(evaluator):
        rows.append({"experimento": f"Baseline: {b['nome']}", "semente": "-", "custo_total": b["custo_total"],
                     "distancia_km": b["distancia_km"], "veiculos": b["veiculos_usados"],
                     "taxa_no_prazo": b["taxa_no_prazo"], "geracoes": 0, "tempo_s": b["tempo_s"]})

    for name, config in EXPERIMENTS.items():
        if only and not any(name.startswith(o) for o in only):
            continue
        for seed in range(1, seeds + 1):
            evaluator = RouteEvaluator(scenario)  # cache limpo = comparação justa de tempo
            result = GeneticOptimizer(evaluator, replace(config, seed=seed)).run()
            sol = evaluator.solution_from_tour(result.best_tour)
            rows.append({"experimento": name, "semente": seed, "custo_total": sol["custo_total"],
                         "distancia_km": sol["distancia_km"], "veiculos": sol["veiculos_usados"],
                         "taxa_no_prazo": sol["taxa_no_prazo"], "geracoes": result.generations,
                         "tempo_s": result.elapsed_s})
            curves.setdefault(name, []).append([h["melhor"] for h in result.history])
            print(f"{name} | semente {seed}: R$ {sol['custo_total']:.2f} em {result.elapsed_s}s")

    with open(out_dir / "resultados.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "convergencia.json").write_text(json.dumps(curves), encoding="utf-8")
    (out_dir / "resumo.md").write_text(_summary(scenario.name, rows, seeds), encoding="utf-8")
    return out_dir


def _summary(scenario_name: str, rows: List[dict], seeds: int) -> str:
    groups: Dict[str, List[dict]] = {}
    for row in rows:
        groups.setdefault(row["experimento"], []).append(row)
    best_baseline = min(r["custo_total"] for r in rows if str(r["experimento"]).startswith("Baseline"))
    lines = [
        f"# Experimentos - {scenario_name}",
        f"{seeds} semente(s) por configuração. Custo em R$ (menor é melhor).",
        "",
        "| Experimento | Custo médio | Desvio | Melhor | vs melhor baseline | No prazo | Tempo médio (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, items in groups.items():
        costs = [r["custo_total"] for r in items]
        mean = statistics.mean(costs)
        std = statistics.stdev(costs) if len(costs) > 1 else 0.0
        gap = (best_baseline - mean) / best_baseline * 100
        lines.append(
            f"| {name} | {mean:.2f} | {std:.2f} | {min(costs):.2f} | {gap:+.1f}% | "
            f"{statistics.mean(r['taxa_no_prazo'] for r in items) * 100:.1f}% | "
            f"{statistics.mean(float(r['tempo_s']) for r in items):.1f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Experimentos do algoritmo genético")
    parser.add_argument("--cenario", default="sp-hemorrede-40")
    parser.add_argument("--sementes", type=int, default=3)
    parser.add_argument("--apenas", nargs="*", help="prefixos dos experimentos (ex.: E1 E5)")
    args = parser.parse_args()
    out = run_experiments(args.cenario, args.sementes, args.apenas)
    print(f"\nResultados em {out}")
    print((out / "resumo.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
