"""Busca local aplicada ao melhor indivíduo (torna o GA um algoritmo memético)."""

from __future__ import annotations

from typing import List, Tuple

from rotavital.optimization.evaluator import Route, RouteEvaluator


def two_opt_route(evaluator: RouteEvaluator, t: int, nodes: List[int]) -> Tuple[List[int], float]:
    """2-opt intra-rota avaliado pelo custo completo (respeita janelas e restrições)."""
    best = list(nodes)
    best_cost = evaluator.route_cost(t, best)
    if best_cost is None or len(best) < 3:
        return best, best_cost if best_cost is not None else float("inf")
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                cost = evaluator.route_cost(t, candidate)
                if cost is not None and cost < best_cost - 1e-9:
                    best, best_cost = candidate, cost
                    improved = True
    return best, best_cost


def relocate_between_routes(evaluator: RouteEvaluator, routes: List[Route]) -> List[Route]:
    """Move uma parada de uma rota para outra quando isso reduz o custo total."""
    routes = [(t, list(nodes)) for t, nodes in routes]
    improved = True
    while improved:
        improved = False
        for a in range(len(routes)):
            ta, ra = routes[a]
            for pos, node in enumerate(ra):
                reduced = ra[:pos] + ra[pos + 1 :]
                cost_a_old = evaluator.route_cost(ta, ra)
                cost_a_new = evaluator.route_cost(ta, reduced) if reduced else 0.0
                if cost_a_new is None or cost_a_old is None:
                    continue
                gain_a = cost_a_old - cost_a_new
                for b in range(len(routes)):
                    if b == a:
                        continue
                    tb, rb = routes[b]
                    cost_b_old = evaluator.route_cost(tb, rb)
                    if cost_b_old is None:
                        continue
                    for ins in range(len(rb) + 1):
                        cand = rb[:ins] + [node] + rb[ins:]
                        cost_b_new = evaluator.route_cost(tb, cand)
                        if cost_b_new is not None and cost_b_new - cost_b_old < gain_a - 1e-6:
                            routes[a] = (ta, reduced)
                            routes[b] = (tb, cand)
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
        routes = [(t, r) for t, r in routes if r]
    return routes


def improve_tour(evaluator: RouteEvaluator, tour: List[int], relocate: bool = True) -> List[int]:
    """Decodifica, melhora cada rota e devolve o novo tour gigante."""
    routes = evaluator.decode(tour)
    routes = [(t, two_opt_route(evaluator, t, nodes)[0]) for t, nodes in routes]
    if relocate:
        routes = relocate_between_routes(evaluator, routes)
    return evaluator.tour_from_routes(routes)
