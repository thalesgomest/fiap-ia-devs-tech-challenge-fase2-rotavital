"""Operadores genéticos para cromossomos de permutação.

Todos recebem um ``random.Random`` explícito para que execuções com a mesma semente
sejam reprodutíveis (necessário para os experimentos comparativos).
"""

from __future__ import annotations

import random
from typing import Callable, Dict, List, Sequence

Tour = List[int]


# ------------------------------------------------------------------ seleção
def tournament(
    population: Sequence[Tour], costs: Sequence[float], k: int, rng: random.Random
) -> Tour:
    """Seleção por torneio: sorteia k indivíduos e devolve o de menor custo."""
    best = rng.randrange(len(population))
    for _ in range(k - 1):
        challenger = rng.randrange(len(population))
        if costs[challenger] < costs[best]:
            best = challenger
    return population[best]


# --------------------------------------------------------------- cruzamento
def order_crossover(p1: Tour, p2: Tour, rng: random.Random) -> Tour:
    """OX: herda um bloco contíguo de p1 e completa na ordem relativa de p2."""
    n = len(p1)
    if n < 2:
        return list(p1)
    a, b = sorted(rng.sample(range(n + 1), 2))
    middle = p1[a:b]
    taken = set(middle)
    rest = [g for g in p2 if g not in taken]
    return rest[:a] + middle + rest[a:]


def pmx_crossover(p1: Tour, p2: Tour, rng: random.Random) -> Tour:
    """PMX: troca um segmento e resolve conflitos pelo mapeamento entre pais."""
    n = len(p1)
    if n < 2:
        return list(p1)
    a, b = sorted(rng.sample(range(n + 1), 2))
    child = [None] * n
    child[a:b] = p1[a:b]
    mapping = {p1[i]: p2[i] for i in range(a, b)}
    in_segment = set(p1[a:b])
    for i in list(range(0, a)) + list(range(b, n)):
        gene = p2[i]
        while gene in in_segment:
            gene = mapping[gene]
        child[i] = gene
    return child  # type: ignore[return-value]


def edge_recombination(p1: Tour, p2: Tour, rng: random.Random) -> Tour:
    """ERX: prioriza arestas presentes nos dois pais (preserva vizinhanças boas)."""
    n = len(p1)
    if n < 3:
        return list(p1)
    adjacency: Dict[int, set] = {g: set() for g in p1}
    for parent in (p1, p2):
        for i, g in enumerate(parent):
            adjacency[g].add(parent[i - 1])
            adjacency[g].add(parent[(i + 1) % n])
    current = rng.choice((p1[0], p2[0]))
    child = [current]
    remaining = set(p1)
    remaining.discard(current)
    while remaining:
        for neighbors in adjacency.values():
            neighbors.discard(current)
        candidates = adjacency[current] & remaining
        if candidates:
            fewest = min(len(adjacency[c]) for c in candidates)
            options = [c for c in candidates if len(adjacency[c]) == fewest]
            current = rng.choice(options)
        else:
            current = rng.choice(tuple(remaining))
        child.append(current)
        remaining.discard(current)
    return child


CROSSOVERS: Dict[str, Callable[[Tour, Tour, random.Random], Tour]] = {
    "ox": order_crossover,
    "pmx": pmx_crossover,
    "erx": edge_recombination,
}


# ------------------------------------------------------------------ mutação
def mutate(tour: Tour, rng: random.Random) -> Tour:
    """Aplica um movimento aleatório: troca, inserção ou inversão (2-opt)."""
    child = list(tour)
    n = len(child)
    if n < 2:
        return child
    move = rng.random()
    if move < 0.33:
        i, j = rng.sample(range(n), 2)
        child[i], child[j] = child[j], child[i]
    elif move < 0.66:
        i, j = rng.sample(range(n), 2)
        gene = child.pop(i)
        child.insert(j, gene)
    else:
        i, j = sorted(rng.sample(range(n), 2))
        child[i : j + 1] = reversed(child[i : j + 1])
    return child


def random_tour(nodes: Sequence[int], rng: random.Random) -> Tour:
    tour = list(nodes)
    rng.shuffle(tour)
    return tour
