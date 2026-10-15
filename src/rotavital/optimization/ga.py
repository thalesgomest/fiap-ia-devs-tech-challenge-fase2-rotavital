"""Algoritmo genético memético para o VRP heterogêneo com janelas de tempo.

Fluxo de cada geração:
  1. avalia a população (custo via Split, com cache);
  2. preserva a elite;
  3. gera filhos por torneio + cruzamento (OX/PMX/ERX) + mutação;
  4. a cada ``local_search_every`` gerações aplica 2-opt no melhor indivíduo;
  5. em estagnação, aumenta a mutação e injeta imigrantes aleatórios.
"""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional

from rotavital.optimization import baselines, operators
from rotavital.optimization.evaluator import RouteEvaluator
from rotavital.optimization.local_search import improve_tour


@dataclass
class GAConfig:
    population_size: int = 120
    generations: int = 400
    crossover: str = "ox"  # ox | pmx | erx
    crossover_rate: float = 0.9
    mutation_rate: float = 0.25
    tournament_k: int = 3
    elitism: int = 2
    seed_ratio: float = 0.1  # fração da população inicial vinda de heurísticas
    local_search_every: int = 10  # 0 desliga a busca local
    stagnation_limit: int = 120
    immigrant_ratio: float = 0.15
    time_limit_s: float = 180.0
    progress_every: int = 5
    seed: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS = {
    "rapido": GAConfig(population_size=60, generations=150, stagnation_limit=50, time_limit_s=30),
    "equilibrado": GAConfig(),
    "qualidade": GAConfig(
        population_size=200, generations=900, stagnation_limit=250, time_limit_s=420,
        crossover="erx",
    ),
}


@dataclass
class Snapshot:
    generation: int
    best_cost: float
    avg_cost: float
    diversity: float
    mutation_rate: float
    elapsed_s: float
    best_tour: List[int]


@dataclass
class GAResult:
    best_tour: List[int]
    best_cost: float
    generations: int
    stop_reason: str
    elapsed_s: float
    evaluations: int
    history: List[dict] = field(default_factory=list)


ProgressCallback = Callable[[Snapshot], None]


class GeneticOptimizer:
    def __init__(self, evaluator: RouteEvaluator, config: Optional[GAConfig] = None):
        self.evaluator = evaluator
        self.config = config or GAConfig()
        if self.config.crossover not in operators.CROSSOVERS:
            raise ValueError(f"Cruzamento desconhecido: {self.config.crossover}")
        self.rng = random.Random(self.config.seed)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    # ---------------------------------------------------------- população
    def _initial_population(self) -> List[List[int]]:
        cfg, ev, rng = self.config, self.evaluator, self.rng
        population: List[List[int]] = []
        n_seeded = int(cfg.population_size * cfg.seed_ratio)
        if n_seeded > 0:
            seeds = [
                baselines.nearest_neighbor_tour(ev),
                baselines.priority_rule_tour(ev),
                ev.tour_from_routes(baselines.clarke_wright_routes(ev)),
            ]
            # variações das sementes (mutadas) preservam qualidade sem clonar
            while len(population) < n_seeded:
                base = seeds[len(population) % len(seeds)]
                population.append(base if len(population) < len(seeds) else operators.mutate(base, rng))
        while len(population) < cfg.population_size:
            population.append(operators.random_tour(ev.nodes, rng))
        return population

    # ---------------------------------------------------------------- loop
    def run(self, on_progress: Optional[ProgressCallback] = None) -> GAResult:
        cfg, ev, rng = self.config, self.evaluator, self.rng
        crossover = operators.CROSSOVERS[cfg.crossover]
        t0 = time.perf_counter()
        population = self._initial_population()
        best_tour, best_cost = None, float("inf")
        stagnation = 0
        mutation_rate = cfg.mutation_rate
        history: List[dict] = []
        stop_reason = "max_geracoes"
        generation = 0

        for generation in range(1, cfg.generations + 1):
            costs = [ev.fitness(ind) for ind in population]
            order = sorted(range(len(population)), key=costs.__getitem__)
            population = [population[i] for i in order]
            costs = [costs[i] for i in order]

            if cfg.local_search_every and generation % cfg.local_search_every == 0:
                improved = improve_tour(ev, population[0], relocate=False)
                improved_cost = ev.fitness(improved)
                if improved_cost < costs[0]:
                    population[0], costs[0] = improved, improved_cost

            if costs[0] < best_cost - 1e-6:
                best_tour, best_cost = list(population[0]), costs[0]
                stagnation = 0
                mutation_rate = cfg.mutation_rate
            else:
                stagnation += 1

            finite = [c for c in costs if c != float("inf")]
            avg = sum(finite) / len(finite) if finite else float("inf")
            diversity = len({tuple(p) for p in population}) / len(population)
            elapsed = time.perf_counter() - t0
            history.append(
                {
                    "geracao": generation,
                    "melhor": round(best_cost, 2),
                    "media": round(avg, 2),
                    "diversidade": round(diversity, 3),
                    "mutacao": round(mutation_rate, 3),
                }
            )

            if on_progress and (generation % cfg.progress_every == 0 or generation == 1):
                on_progress(
                    Snapshot(generation, best_cost, avg, diversity, mutation_rate, elapsed, best_tour)
                )

            if self._stop:
                stop_reason = "interrompido"
                break
            if stagnation >= cfg.stagnation_limit:
                stop_reason = "estagnacao"
                break
            if elapsed >= cfg.time_limit_s:
                stop_reason = "tempo_limite"
                break

            # estagnação parcial: mais mutação + imigrantes para recuperar diversidade
            if stagnation and stagnation % max(cfg.stagnation_limit // 3, 1) == 0:
                mutation_rate = min(0.8, mutation_rate * 1.6)
                n_imm = int(cfg.population_size * cfg.immigrant_ratio)
                for k in range(1, n_imm + 1):
                    population[-k] = operators.random_tour(ev.nodes, rng)
                    costs[-k] = ev.fitness(population[-k])

            next_pop = [list(p) for p in population[: cfg.elitism]]
            while len(next_pop) < cfg.population_size:
                p1 = operators.tournament(population, costs, cfg.tournament_k, rng)
                if rng.random() < cfg.crossover_rate:
                    p2 = operators.tournament(population, costs, cfg.tournament_k, rng)
                    child = crossover(p1, p2, rng)
                else:
                    child = list(p1)
                if rng.random() < mutation_rate:
                    child = operators.mutate(child, rng)
                next_pop.append(child)
            population = next_pop

        # polimento final: 2-opt + realocação entre rotas
        polished = improve_tour(ev, best_tour, relocate=True)
        polished_cost = ev.fitness(polished)
        if polished_cost < best_cost:
            best_tour, best_cost = polished, polished_cost
            if history:
                history[-1]["melhor"] = round(best_cost, 2)

        elapsed = time.perf_counter() - t0
        if on_progress:
            on_progress(Snapshot(generation, best_cost, history[-1]["media"], 0, mutation_rate, elapsed, best_tour))
        return GAResult(
            best_tour=best_tour,
            best_cost=best_cost,
            generations=generation,
            stop_reason=stop_reason,
            elapsed_s=round(elapsed, 2),
            evaluations=ev.evaluations,
            history=history,
        )
