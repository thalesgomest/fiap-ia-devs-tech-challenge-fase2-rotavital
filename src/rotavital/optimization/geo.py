"""Distâncias geográficas."""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

EARTH_RADIUS_KM = 6371.0


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def road_distance_matrix(
    points: Sequence[Tuple[float, float]], circuity: float
) -> List[List[float]]:
    """Matriz simétrica de distância por estrada estimada (linha reta x sinuosidade).

    O fator de sinuosidade (~1,3-1,4 em áreas urbanas brasileiras) aproxima a malha
    viária sem depender de serviços externos de roteamento.
    """
    n = len(points)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_km(points[i], points[j]) * circuity
            matrix[i][j] = d
            matrix[j][i] = d
    return matrix
