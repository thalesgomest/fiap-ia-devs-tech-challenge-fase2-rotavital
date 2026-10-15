import random

import pytest

from rotavital.optimization import operators
from rotavital.optimization.baselines import BASELINES, run_baselines
from rotavital.optimization.evaluator import RouteEvaluator
from rotavital.optimization.ga import GAConfig, GeneticOptimizer


@pytest.mark.parametrize("name", sorted(operators.CROSSOVERS))
def test_crossovers_produce_valid_permutations(name):
    rng = random.Random(0)
    fn = operators.CROSSOVERS[name]
    for _ in range(200):
        p1 = list(range(1, 16))
        p2 = list(range(1, 16))
        rng.shuffle(p1)
        rng.shuffle(p2)
        child = fn(p1, p2, rng)
        assert sorted(child) == list(range(1, 16))


def test_mutation_preserves_permutation():
    rng = random.Random(1)
    tour = list(range(1, 21))
    for _ in range(300):
        tour = operators.mutate(tour, rng)
        assert sorted(tour) == list(range(1, 21))


def test_tournament_with_full_pressure_returns_best():
    rng = random.Random(2)
    pop = [[1], [2], [3], [4]]
    costs = [5.0, 1.0, 9.0, 3.0]
    picks = {tuple(operators.tournament(pop, costs, 50, rng)) for _ in range(20)}
    assert picks == {(2,)}


def test_baselines_visit_all_stops(small_scenario):
    ev = RouteEvaluator(small_scenario)
    for key, (_, fn) in BASELINES.items():
        visited = sorted(n for _, nodes in fn(ev) for n in nodes)
        assert visited == ev.nodes, key


def test_ga_is_reproducible_and_not_worse_than_baselines(small_scenario):
    cfg = GAConfig(population_size=30, generations=40, stagnation_limit=20, seed=42, progress_every=10)
    r1 = GeneticOptimizer(RouteEvaluator(small_scenario), cfg).run()
    r2 = GeneticOptimizer(RouteEvaluator(small_scenario), cfg).run()
    assert r1.best_tour == r2.best_tour
    assert r1.best_cost == pytest.approx(r2.best_cost)
    best_baseline = min(b["custo_total"] for b in run_baselines(RouteEvaluator(small_scenario)))
    assert r1.best_cost <= best_baseline + 0.01


def test_ga_reports_progress_and_can_stop(small_scenario):
    ev = RouteEvaluator(small_scenario)
    ga = GeneticOptimizer(ev, GAConfig(population_size=20, generations=500, stagnation_limit=500, progress_every=1, seed=3))
    seen = []

    def on_progress(snap):
        seen.append(snap.generation)
        if snap.generation >= 5:
            ga.stop()

    result = ga.run(on_progress)
    assert result.stop_reason == "interrompido"
    assert seen[0] == 1 and result.generations <= 6


def test_invalid_crossover_raises(small_scenario):
    with pytest.raises(ValueError):
        GeneticOptimizer(RouteEvaluator(small_scenario), GAConfig(crossover="xyz"))
