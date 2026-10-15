"""Avaliação de soluções: decodificação do cromossomo em rotas e cálculo de custo.

Representação genética
----------------------
O cromossomo é uma *permutação* das paradas (um "tour gigante", sem depósito). Ele não
diz onde uma rota termina e a próxima começa: isso é decidido pelo procedimento
**Split** (Prins, 2004), uma programação dinâmica que encontra o particionamento ótimo
do tour em rotas consecutivas respeitando as restrições de cada tipo de veículo.

Restrições
----------
Rígidas (rota inviável para aquele tipo de veículo):
  * capacidade de carga (kg);
  * autonomia (km, incluindo o retorno ao depósito);
  * jornada máxima do motorista;
  * cadeia fria: carga refrigerada só em veículo refrigerado.
Flexíveis (viram custo em R$):
  * atraso em relação ao prazo (fim da janela ou SLA da prioridade), com multa por minuto
    proporcional à prioridade;
  * veículos além da quantidade disponível na frota.

O fitness é, portanto, um custo monetário interpretável:
    custo = custo fixo dos veículos + custo por km + multas de atraso + multa de frota
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from rotavital.domain.models import Scenario, min_to_hhmm
from rotavital.domain.scenarios import ScenarioError
from rotavital.optimization.geo import road_distance_matrix

INF = float("inf")
Route = Tuple[int, List[int]]  # (índice do tipo de veículo, nós da rota)


class RouteEvaluator:
    """Pré-calcula matrizes e avalia tours/rotas de um cenário.

    Os nós são numerados com o depósito em 0 e as paradas em 1..n (na ordem do cenário).
    """

    CACHE_LIMIT = 300_000

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        stops = scenario.stops
        points = [(scenario.depot.lat, scenario.depot.lon)] + [(s.lat, s.lon) for s in stops]
        self.dist = road_distance_matrix(points, scenario.circuity)
        self.n = len(stops)
        self.nodes = list(range(1, self.n + 1))

        self.demand = [0.0] + [s.demand_kg for s in stops]
        self.refrig = [False] + [s.refrigerated for s in stops]
        self.win_start = [0] + [s.window_start for s in stops]
        self.deadline = [0] + [scenario.deadline(s) for s in stops]
        self.service = [0] + [s.service_min for s in stops]
        self.late_rate = [0.0] + [
            scenario.priorities[s.priority].late_penalty_per_min for s in stops
        ]
        self.types = scenario.fleet
        self.min_per_km = [60.0 / v.speed_kmh for v in self.types]
        self.start = scenario.shift_start

        self._cache: Dict[tuple, float] = {}
        self.evaluations = 0
        self._check_single_stop_feasibility()

    # ------------------------------------------------------------------ util
    def _check_single_stop_feasibility(self) -> None:
        bad = [
            self.scenario.stops[node - 1].name
            for node in self.nodes
            if all(self.route_cost(t, [node]) is None for t in range(len(self.types)))
        ]
        if bad:
            raise ScenarioError(
                "Paradas inatingíveis por qualquer veículo (autonomia/jornada): "
                + ", ".join(bad)
            )

    def route_distance(self, nodes: Sequence[int]) -> float:
        total, prev = 0.0, 0
        for node in nodes:
            total += self.dist[prev][node]
            prev = node
        return total + self.dist[prev][0]

    # ------------------------------------------------------- custo de 1 rota
    def route_cost(self, t: int, nodes: Sequence[int]) -> Optional[float]:
        """Custo da rota feita pelo tipo ``t`` ou ``None`` se violar restrição rígida."""
        vt = self.types[t]
        mpk = self.min_per_km[t]
        shift_end = self.start + vt.max_shift_min
        load = d = pen = 0.0
        clock = float(self.start)
        prev = 0
        for node in nodes:
            load += self.demand[node]
            if load > vt.capacity_kg or (self.refrig[node] and not vt.refrigerated):
                return None
            leg = self.dist[prev][node]
            d += leg
            clock += leg * mpk
            if clock < self.win_start[node]:
                clock = self.win_start[node]
            late = clock - self.deadline[node]
            if late > 0:
                pen += late * self.late_rate[node]
            clock += self.service[node]
            prev = node
        back = self.dist[prev][0]
        d += back
        clock += back * mpk
        if d > vt.range_km or clock > shift_end:
            return None
        return vt.fixed_cost + vt.cost_per_km * d + pen

    def best_type_for(self, nodes: Sequence[int]) -> Optional[Tuple[int, float]]:
        best = None
        for t in range(len(self.types)):
            cost = self.route_cost(t, nodes)
            if cost is not None and (best is None or cost < best[1]):
                best = (t, cost)
        return best

    # ------------------------------------------------------------- Split
    def split(
        self, tour: Sequence[int], shadow: Optional[Sequence[float]] = None
    ) -> Tuple[float, List[Route]]:
        """Particiona o tour em rotas de custo mínimo (frota ilimitada).

        Para cada par (i, j) testa todos os tipos de veículo e guarda o mais barato.
        A simulação é incremental: estender a rota de j para j+1 custa O(1), então a
        complexidade é O(n · L · T), com L = tamanho máximo de uma rota viável.

        ``shadow`` soma um custo fixo extra por tipo (preço-sombra) e é usado para
        desestimular tipos cuja quantidade disponível foi excedida.
        """
        shadow = shadow or [0.0] * len(self.types)
        n = len(tour)
        V = [INF] * (n + 1)
        V[0] = 0.0
        pred = [0] * (n + 1)
        ptype = [0] * (n + 1)
        dist, demand, refrig = self.dist, self.demand, self.refrig
        win_start, deadline, service, late_rate = (
            self.win_start,
            self.deadline,
            self.service,
            self.late_rate,
        )
        start = float(self.start)

        for i in range(n):
            vi = V[i]
            if vi == INF:
                continue
            for t, vt in enumerate(self.types):
                cap, rng, refr = vt.capacity_kg, vt.range_km, vt.refrigerated
                fixed, cpk, mpk = vt.fixed_cost + shadow[t], vt.cost_per_km, self.min_per_km[t]
                shift_end = start + vt.max_shift_min
                load = d = pen = 0.0
                clock = start
                prev = 0
                for j in range(i, n):
                    node = tour[j]
                    load += demand[node]
                    if load > cap or (refrig[node] and not refr):
                        break
                    leg = dist[prev][node]
                    d += leg
                    if d > rng:
                        break
                    clock += leg * mpk
                    if clock < win_start[node]:
                        clock = win_start[node]
                    late = clock - deadline[node]
                    if late > 0:
                        pen += late * late_rate[node]
                    clock += service[node]
                    if clock > shift_end:
                        break
                    prev = node
                    back = dist[node][0]
                    if d + back > rng or clock + back * mpk > shift_end:
                        continue
                    cost = vi + fixed + cpk * (d + back) + pen
                    if cost < V[j + 1]:
                        V[j + 1] = cost
                        pred[j + 1] = i
                        ptype[j + 1] = t

        routes: List[Route] = []
        j = n
        while j > 0:
            i = pred[j]
            routes.append((ptype[j], list(tour[i:j])))
            j = i
        routes.reverse()
        return V[n], routes

    # ----------------------------------------------------- frota limitada
    def assign_fleet(self, routes: List[Route]) -> Tuple[List[Route], int]:
        """Reparo guloso: realoca rotas de tipos sobre-utilizados para tipos com folga.

        Retorna as rotas reatribuídas e quantos veículos ainda excedem a frota.
        """
        routes = [(t, nodes) for t, nodes in routes]
        quantity = [v.quantity for v in self.types]
        counts = [0] * len(self.types)
        for t, _ in routes:
            counts[t] += 1

        for t in range(len(self.types)):
            while counts[t] > quantity[t]:
                best = None  # (delta, idx, novo_tipo)
                for idx, (rt, nodes) in enumerate(routes):
                    if rt != t:
                        continue
                    current = self.route_cost(t, nodes)
                    for u in range(len(self.types)):
                        if u == t or counts[u] >= quantity[u]:
                            continue
                        cost = self.route_cost(u, nodes)
                        if cost is not None and (best is None or cost - current < best[0]):
                            best = (cost - current, idx, u)
                if best is None:
                    break
                _, idx, u = best
                routes[idx] = (u, routes[idx][1])
                counts[t] -= 1
                counts[u] += 1

        excess = sum(max(0, c - q) for c, q in zip(counts, quantity, strict=True))
        return routes, excess

    def routes_cost(self, routes: List[Route]) -> float:
        total = 0.0
        for t, nodes in routes:
            cost = self.route_cost(t, nodes)
            if cost is None:
                return INF
            total += cost
        return total

    # ------------------------------------------------------------ fitness
    SHADOW_ROUNDS = 3

    def _fleet_aware_split(self, tour: Sequence[int]) -> Tuple[float, List[Route]]:
        """Split + reparo de frota + preços-sombra.

        1. Split com frota ilimitada;
        2. se algum tipo excede a quantidade disponível, tenta realocar rotas (reparo);
        3. se ainda exceder, refaz o Split encarecendo o custo fixo dos tipos excedidos
           (preço-sombra crescente) e fica com a melhor solução de custo REAL.
        """
        penalty = self.scenario.fleet_excess_penalty
        quantity = [v.quantity for v in self.types]
        shadow = [0.0] * len(self.types)
        best_cost, best_routes = INF, []
        for round_ in range(self.SHADOW_ROUNDS + 1):
            cost, routes = self.split(tour, shadow)
            if cost == INF:
                break
            counts = [0] * len(self.types)
            for t, _ in routes:
                counts[t] += 1
            if all(c <= q for c, q in zip(counts, quantity, strict=True)):
                real = cost if round_ == 0 else self.routes_cost(routes)
                excess = 0
            else:
                routes, excess = self.assign_fleet(routes)
                real = self.routes_cost(routes) + excess * penalty
            if real < best_cost:
                best_cost, best_routes = real, routes
            if excess == 0:
                break
            counts = [0] * len(self.types)
            for t, _ in routes:
                counts[t] += 1
            for t, (c, q) in enumerate(zip(counts, quantity, strict=True)):
                if c > q:
                    shadow[t] += penalty / self.SHADOW_ROUNDS
        return best_cost, best_routes

    def fitness(self, tour: Sequence[int]) -> float:
        key = tuple(tour)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        self.evaluations += 1
        cost, _ = self._fleet_aware_split(tour)
        if len(self._cache) > self.CACHE_LIMIT:
            self._cache.clear()
        self._cache[key] = cost
        return cost

    def tour_from_routes(self, routes: List[Route]) -> List[int]:
        return [node for _, nodes in routes for node in nodes]

    # ---------------------------------------------------------- detalhes
    def decode(self, tour: Sequence[int]) -> List[Route]:
        return self._fleet_aware_split(tour)[1]

    def build_solution(self, routes: List[Route]) -> dict:
        """Gera a solução detalhada (horários, atrasos, ocupação) em formato JSON."""
        scenario = self.scenario
        used = [0] * len(self.types)
        out_routes = []
        totals = {
            "operational": 0.0,
            "late_pen": 0.0,
            "distance": 0.0,
            "duration": 0.0,
            "co2": 0.0,
            "late_min": 0.0,
        }
        deliveries = on_time = critical = critical_on_time = 0
        occupancies = []

        for t, nodes in routes:
            vt = self.types[t]
            used[t] += 1
            label = f"{vt.code} #{used[t]}"
            excess = used[t] > vt.quantity
            mpk = self.min_per_km[t]
            load_total = sum(self.demand[n] for n in nodes)
            remaining = load_total
            clock = float(self.start)
            prev = 0
            d = pen = 0.0
            stops_out = []
            for order, node in enumerate(nodes, start=1):
                stop = scenario.stops[node - 1]
                leg = self.dist[prev][node]
                d += leg
                clock += leg * mpk
                arrival = clock
                wait = max(0.0, self.win_start[node] - clock)
                clock += wait
                late = max(0.0, clock - self.deadline[node])
                pen += late * self.late_rate[node]
                service_start = clock
                clock += self.service[node]
                remaining -= self.demand[node]
                prev = node
                deliveries += 1
                if late <= 0.5:
                    on_time += 1
                if stop.priority == "critica":
                    critical += 1
                    if late <= 0.5:
                        critical_on_time += 1
                totals["late_min"] += late
                stops_out.append(
                    {
                        "ordem": order,
                        "id": stop.id,
                        "nome": stop.name,
                        "tipo": stop.kind,
                        "carga": stop.cargo,
                        "prioridade": stop.priority,
                        "refrigerado": stop.refrigerated,
                        "demanda_kg": round(stop.demand_kg, 1),
                        "lat": stop.lat,
                        "lon": stop.lon,
                        "distancia_trecho_km": round(leg, 2),
                        "chegada": min_to_hhmm(arrival),
                        "inicio_atendimento": min_to_hhmm(service_start),
                        "saida": min_to_hhmm(clock),
                        "espera_min": round(wait, 1),
                        "atraso_min": round(late, 1),
                        "prazo": min_to_hhmm(self.deadline[node]),
                        "janela": f"{min_to_hhmm(stop.window_start)}-{min_to_hhmm(stop.window_end)}",
                        "folga_min": round(self.deadline[node] - service_start, 1),
                        "carga_restante_kg": round(max(remaining, 0.0), 1),
                    }
                )
            back = self.dist[prev][0]
            d += back
            clock += back * mpk
            duration = clock - self.start
            operational = vt.fixed_cost + vt.cost_per_km * d
            occupancy = load_total / vt.capacity_kg if vt.capacity_kg else 0.0
            occupancies.append(occupancy)
            totals["operational"] += operational
            totals["late_pen"] += pen
            totals["distance"] += d
            totals["duration"] += duration
            totals["co2"] += d * vt.co2_kg_per_km
            out_routes.append(
                {
                    "veiculo": label,
                    "tipo": vt.code,
                    "tipo_nome": vt.name,
                    "refrigerado": vt.refrigerated,
                    "excedente": excess,
                    "saida_deposito": min_to_hhmm(self.start),
                    "retorno_deposito": min_to_hhmm(clock),
                    "distancia_km": round(d, 2),
                    "duracao_min": round(duration, 1),
                    "carga_kg": round(load_total, 1),
                    "capacidade_kg": vt.capacity_kg,
                    "ocupacao": round(occupancy, 3),
                    "uso_autonomia": round(d / vt.range_km, 3),
                    "custo_operacional": round(operational, 2),
                    "multa_atraso": round(pen, 2),
                    "paradas_atrasadas": sum(1 for s in stops_out if s["atraso_min"] > 0.5),
                    "paradas": stops_out,
                }
            )

        excess_vehicles = sum(max(0, u - v.quantity) for u, v in zip(used, self.types, strict=True))
        fleet_pen = excess_vehicles * scenario.fleet_excess_penalty
        total = totals["operational"] + totals["late_pen"] + fleet_pen
        return {
            "custo_total": round(total, 2),
            "custo_operacional": round(totals["operational"], 2),
            "multa_atraso": round(totals["late_pen"], 2),
            "multa_frota": round(fleet_pen, 2),
            "distancia_km": round(totals["distance"], 2),
            "duracao_total_min": round(totals["duration"], 1),
            "co2_kg": round(totals["co2"], 1),
            "veiculos_usados": len(routes),
            "veiculos_excedentes": excess_vehicles,
            "uso_por_tipo": {v.code: used[i] for i, v in enumerate(self.types)},
            "entregas": deliveries,
            "entregas_no_prazo": on_time,
            "taxa_no_prazo": round(on_time / deliveries, 4) if deliveries else 1.0,
            "criticas_total": critical,
            "criticas_no_prazo": critical_on_time,
            "atraso_total_min": round(totals["late_min"], 1),
            "ocupacao_media": round(sum(occupancies) / len(occupancies), 3) if occupancies else 0.0,
            "rotas": out_routes,
        }

    def solution_from_tour(self, tour: Sequence[int]) -> dict:
        return self.build_solution(self.decode(tour))
