from dataclasses import replace

import pytest

from rotavital.domain.models import Depot, Scenario, VehicleType
from rotavital.domain.scenarios import ScenarioError
from rotavital.optimization.evaluator import RouteEvaluator
from tests.conftest import make_stop


def test_split_covers_every_stop_once(small_scenario):
    ev = RouteEvaluator(small_scenario)
    _, routes = ev.split(ev.nodes)
    visited = [n for _, nodes in routes for n in nodes]
    assert sorted(visited) == ev.nodes


def test_routes_respect_capacity_and_cold_chain(small_scenario):
    ev = RouteEvaluator(small_scenario)
    sol = ev.solution_from_tour([6, 5, 4, 3, 2, 1])
    for route in sol["rotas"]:
        assert route["carga_kg"] <= route["capacidade_kg"]
        if any(p["refrigerado"] for p in route["paradas"]):
            assert route["refrigerado"], "carga refrigerada em veículo comum"


def test_route_cost_rejects_overload_and_refrigeration(small_scenario):
    ev = RouteEvaluator(small_scenario)
    ref, seco = 0, 1
    assert ev.route_cost(ref, [2, 4]) is None  # 70 kg > 60 kg
    assert ev.route_cost(seco, [1]) is None  # refrigerada em veículo seco
    assert ev.route_cost(seco, [2, 4]) is not None


def test_fitness_matches_detailed_solution(small_scenario):
    ev = RouteEvaluator(small_scenario)
    tour = [3, 1, 5, 2, 6, 4]
    assert ev.fitness(tour) == pytest.approx(ev.solution_from_tour(tour)["custo_total"], abs=0.05)


def test_split_is_optimal_versus_naive_one_route_per_stop(small_scenario):
    ev = RouteEvaluator(small_scenario)
    naive = sum(ev.best_type_for([n])[1] for n in ev.nodes)
    cost, _ = ev.split(ev.nodes)
    assert cost <= naive


def test_lateness_is_penalized():
    stop = make_stop(1, -23.40, -46.40, priority="critica", window=(420, 425))
    scenario = Scenario(
        id="t", name="t", description="", depot=Depot("CD", -23.557, -46.669), stops=[stop],
        fleet=[VehicleType("V", "Van", 1, 100, 300, 30, True, 0, 0, 600)],
    )
    sol = RouteEvaluator(scenario).solution_from_tour([1])
    assert sol["multa_atraso"] > 0
    assert sol["rotas"][0]["paradas"][0]["atraso_min"] > 0
    assert sol["taxa_no_prazo"] == 0


def test_insufficient_fleet_is_penalized_not_crashing(small_scenario):
    tiny = [replace(v, quantity=1, capacity_kg=45) for v in small_scenario.fleet]
    ev = RouteEvaluator(replace(small_scenario, fleet=tiny))
    sol = ev.solution_from_tour(ev.nodes)
    assert sol["veiculos_excedentes"] > 0
    assert sol["multa_frota"] == sol["veiculos_excedentes"] * small_scenario.fleet_excess_penalty


def test_unreachable_stop_is_rejected():
    far = make_stop(1, -10.0, -40.0)  # ~1.700 km do depósito
    scenario = Scenario(
        id="t", name="t", description="", depot=Depot("CD", -23.557, -46.669), stops=[far],
        fleet=[VehicleType("V", "Van", 1, 100, 300, 30, False, 0, 1, 600)],
    )
    with pytest.raises(ScenarioError):
        RouteEvaluator(scenario)


def test_scheduled_window_after_sla_uses_window(small_scenario):
    late_window = make_stop(9, -23.55, -46.60, priority="alta", window=(14 * 60, 16 * 60))
    assert small_scenario.deadline(late_window) == 16 * 60
    early = make_stop(10, -23.55, -46.60, priority="critica")
    assert small_scenario.deadline(early) == small_scenario.shift_start + 120
