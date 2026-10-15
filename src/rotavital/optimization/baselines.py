"""Abordagens de referência para o comparativo exigido no relatório técnico.

Todas usam o mesmo avaliador do GA, então os custos são diretamente comparáveis.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Dict, List

from rotavital.optimization.evaluator import Route, RouteEvaluator


def nearest_neighbor_tour(evaluator: RouteEvaluator, start: int = 0) -> List[int]:
    """Tour guloso: sempre visita a parada não visitada mais próxima."""
    remaining = set(evaluator.nodes)
    tour, current = [], start
    while remaining:
        nxt = min(remaining, key=lambda n: evaluator.dist[current][n])
        tour.append(nxt)
        remaining.remove(nxt)
        current = nxt
    return tour


def priority_rule_tour(evaluator: RouteEvaluator) -> List[int]:
    """Regra de despacho manual: prioridade, depois prazo, depois distância."""
    scenario = evaluator.scenario
    return sorted(
        evaluator.nodes,
        key=lambda n: (
            scenario.priorities[scenario.stops[n - 1].priority].rank,
            evaluator.deadline[n],
            evaluator.dist[0][n],
        ),
    )


def clarke_wright_routes(evaluator: RouteEvaluator) -> List[Route]:
    """Algoritmo das economias (Clarke & Wright, 1964), versão paralela.

    Começa com uma rota por parada e une rotas pelas pontas, na ordem decrescente da
    economia s(i,j) = d(0,i) + d(0,j) - d(i,j). Adaptação para este problema: a união só
    é aceita se a rota resultante for viável para algum veículo E não custar mais que as
    duas rotas separadas (o custo inclui multas de atraso, então janelas são respeitadas).
    """
    d = evaluator.dist
    routes: Dict[int, List[int]] = {n: [n] for n in evaluator.nodes}
    cost_of: Dict[int, float] = {n: evaluator.best_type_for([n])[1] for n in evaluator.nodes}
    owner = {n: n for n in evaluator.nodes}
    savings = sorted(
        (
            (d[0][i] + d[0][j] - d[i][j], i, j)
            for i in evaluator.nodes
            for j in evaluator.nodes
            if i < j
        ),
        reverse=True,
    )
    for saving, i, j in savings:
        if saving <= 0:
            break
        ri, rj = owner[i], owner[j]
        if ri == rj:
            continue
        a, b = routes[ri], routes[rj]
        candidates = []
        if a[-1] == i and b[0] == j:
            candidates.append(a + b)
        if b[-1] == j and a[0] == i:
            candidates.append(b + a)
        if a[0] == i and b[0] == j:
            candidates.append(a[::-1] + b)
        if a[-1] == i and b[-1] == j:
            candidates.append(a + b[::-1])
        merged, merged_cost = None, cost_of[ri] + cost_of[rj]
        for cand in candidates:
            best = evaluator.best_type_for(cand)
            if best is not None and best[1] < merged_cost:
                merged, merged_cost = cand, best[1]
        if merged is None:
            continue
        routes[ri] = merged
        cost_of[ri] = merged_cost
        del routes[rj]
        for node in merged:
            owner[node] = ri

    assigned = []
    for nodes in routes.values():
        best = evaluator.best_type_for(nodes)
        assigned.append((best[0] if best else 0, nodes))
    assigned, _ = evaluator.assign_fleet(assigned)
    return assigned


def _from_tour(fn: Callable[[RouteEvaluator], List[int]]) -> Callable[[RouteEvaluator], List[Route]]:
    return lambda ev: ev.decode(fn(ev))


def random_routes(evaluator: RouteEvaluator, samples: int = 30, seed: int = 7) -> List[Route]:
    """Melhor de N tours aleatórios (limite inferior de qualidade)."""
    rng = random.Random(seed)
    best_tour, best_cost = None, float("inf")
    for _ in range(samples):
        tour = list(evaluator.nodes)
        rng.shuffle(tour)
        cost = evaluator.fitness(tour)
        if cost < best_cost:
            best_tour, best_cost = tour, cost
    return evaluator.decode(best_tour)


BASELINES = {
    "aleatorio": ("Aleatório (melhor de 30)", random_routes),
    "regra_prioridade": ("Regra manual por prioridade", _from_tour(priority_rule_tour)),
    "vizinho_mais_proximo": ("Vizinho mais próximo + Split", _from_tour(nearest_neighbor_tour)),
    "clarke_wright": ("Clarke-Wright (economias)", clarke_wright_routes),
}


def run_baselines(evaluator: RouteEvaluator) -> List[dict]:
    """Executa todas as heurísticas de referência e devolve KPIs resumidos."""
    results = []
    for key, (label, fn) in BASELINES.items():
        t0 = time.perf_counter()
        routes = fn(evaluator)
        elapsed = time.perf_counter() - t0
        solution = evaluator.build_solution(routes)
        results.append(
            {
                "id": key,
                "nome": label,
                "tempo_s": round(elapsed, 3),
                "custo_total": solution["custo_total"],
                "distancia_km": solution["distancia_km"],
                "veiculos_usados": solution["veiculos_usados"],
                "taxa_no_prazo": solution["taxa_no_prazo"],
                "multa_atraso": solution["multa_atraso"],
                "atraso_total_min": solution["atraso_total_min"],
                "rotas": [[p["id"] for p in r["paradas"]] for r in solution["rotas"]],
                "_routes": routes,
            }
        )
    return results
