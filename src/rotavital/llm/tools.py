"""Ferramentas consultáveis pela LLM no chat (function calling).

Em vez de despejar o JSON inteiro da execução no prompt, o modelo pede exatamente o que
precisa. Isso reduz tokens, permite perguntas "e se?" (simulação de atraso) e diminui
alucinação, porque todo número da resposta vem de uma consulta real.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional

from rotavital.domain.models import hhmm_to_min, min_to_hhmm
from rotavital.llm.providers.base import ToolSpec
from rotavital.storage.history import HistoryStore


def _norm(text: str) -> str:
    """Minúsculas, sem acentos, sem '#' e com espaços simples ("MOTO #1" -> "moto 1")."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.replace("#", " ").split())


def requested_priority(question: str) -> Optional[str]:
    """Só fixa uma prioridade quando a pergunta menciona uma categoria única."""
    normalized = _norm(question)
    matches = [priority for priority, pattern in (
        ("critica", r"\bcritic[ao]s?\b"), ("alta", r"\balt[ao]s?\b"), ("rotina", r"\brotina\b"),
    ) if re.search(pattern, normalized)]
    return matches[0] if len(matches) == 1 else None


def find_route(run: dict, vehicle: str) -> dict:
    wanted = _norm(str(vehicle))
    routes = run["solucao"]["rotas"]
    for route in routes:
        if _norm(route["veiculo"]) == wanted:
            return route
    if wanted.isdigit() and 1 <= int(wanted) <= len(routes):  # "veículo 2"
        return routes[int(wanted) - 1]
    raise KeyError(vehicle)


def _stop_brief(stop: dict) -> dict:
    return {
        k: stop[k]
        for k in (
            "ordem", "nome", "tipo", "carga", "prioridade", "refrigerado", "demanda_kg",
            "chegada", "inicio_atendimento", "saida", "janela", "prazo", "espera_min",
            "atraso_min", "folga_min", "carga_restante_kg",
        )
    }


class RunTools:
    """Implementações das ferramentas sobre um registro de execução."""

    def __init__(self, run: dict, store: Optional[HistoryStore] = None):
        self.run = run
        self.store = store

    def resumo_execucao(self) -> dict:
        sol = self.run["solucao"]
        return {
            "cenario": self.run["cenario"]["nome"],
            "kpis": {k: v for k, v in sol.items() if k != "rotas"},
            "comparativo": self.run["comparativo"],
            "algoritmo_genetico": {
                k: self.run["ga"][k] for k in ("geracoes", "motivo_parada", "tempo_s", "avaliacoes")
            },
        }

    def listar_rotas(self) -> List[dict]:
        return [
            {
                "veiculo": r["veiculo"],
                "tipo": r["tipo_nome"],
                "refrigerado": r["refrigerado"],
                "paradas": len(r["paradas"]),
                "saida": r["saida_deposito"],
                "retorno": r["retorno_deposito"],
                "distancia_km": r["distancia_km"],
                "duracao_min": r["duracao_min"],
                "ocupacao_pct": round(r["ocupacao"] * 100, 1),
                "uso_autonomia_pct": round(r["uso_autonomia"] * 100, 1),
                "paradas_atrasadas": r["paradas_atrasadas"],
                "custo_operacional": r["custo_operacional"],
                "multa_atraso": r["multa_atraso"],
            }
            for r in self.run["solucao"]["rotas"]
        ]

    def detalhar_rota(self, veiculo: str) -> dict:
        route = find_route(self.run, veiculo)
        data = {k: v for k, v in route.items() if k != "paradas"}
        data["paradas"] = [_stop_brief(s) for s in route["paradas"]]
        return data

    def buscar_parada(self, nome: str) -> List[dict]:
        wanted = _norm(nome)
        hits = []
        for route in self.run["solucao"]["rotas"]:
            for stop in route["paradas"]:
                if wanted in _norm(stop["nome"]) or wanted == _norm(stop["id"]):
                    hits.append(dict(_stop_brief(stop), veiculo=route["veiculo"]))
        return hits or [{"erro": f"nenhuma parada encontrada para '{nome}'"}]

    def entregas_em_risco(self, folga_minima_min: float = 15, prioridade: Optional[str] = None) -> List[dict]:
        if prioridade not in (None, "critica", "alta", "rotina"):
            raise ValueError("Prioridade deve ser critica, alta ou rotina.")
        risky = []
        for route in self.run["solucao"]["rotas"]:
            for stop in route["paradas"]:
                if prioridade is not None and stop["prioridade"] != prioridade:
                    continue
                if stop["atraso_min"] > 0.5 or stop["folga_min"] < folga_minima_min:
                    risky.append(
                        dict(
                            _stop_brief(stop),
                            veiculo=route["veiculo"],
                            situacao="atrasada" if stop["atraso_min"] > 0.5 else "folga baixa",
                        )
                    )
        risky.sort(key=lambda s: (s["situacao"] != "atrasada", s["folga_min"]))
        if risky:
            return risky
        label = {"critica": "crítica", "alta": "alta", "rotina": "rotina"}.get(prioridade)
        category = f" de prioridade {label}" if label else ""
        return [{"mensagem": f"Nenhuma entrega{category} está atrasada ou com folga inferior a {folga_minima_min:g} minutos.",
                 "quantidade": 0, "prioridade_filtrada": prioridade,
                 "observacao": "Zero é uma contagem calculada, não informação ausente."}]

    def comparar_abordagens(self) -> dict:
        sol = self.run["solucao"]
        rows = [
            {
                "abordagem": "Algoritmo genético (RotaVital)",
                "custo_total": sol["custo_total"],
                "distancia_km": sol["distancia_km"],
                "veiculos": sol["veiculos_usados"],
                "taxa_no_prazo": sol["taxa_no_prazo"],
            }
        ]
        for b in self.run["baselines"]:
            rows.append(
                {
                    "abordagem": b["nome"],
                    "custo_total": b["custo_total"],
                    "distancia_km": b["distancia_km"],
                    "veiculos": b["veiculos_usados"],
                    "taxa_no_prazo": b["taxa_no_prazo"],
                }
            )
        return {"tabela": rows, "comparativo": self.run["comparativo"]}

    def simular_atraso(self, veiculo: str, minutos: float, a_partir_da_parada: int = 1) -> dict:
        """Propaga um atraso pela rota; a espera em janelas pode absorver parte dele."""
        route = find_route(self.run, veiculo)
        rules = self.run["cenario"]["prioridades"]
        shift = float(minutos)
        impacts, extra_penalty = [], 0.0
        for stop in route["paradas"]:
            if stop["ordem"] < a_partir_da_parada:
                continue
            arrival = hhmm_to_min(stop["chegada"]) + shift
            window_start = hhmm_to_min(stop["janela"].split("-")[0])
            start = max(arrival, window_start)
            original_start = hhmm_to_min(stop["inicio_atendimento"])
            shift = max(0.0, start - original_start)
            new_late = max(0.0, start - hhmm_to_min(stop["prazo"]))
            delta_late = new_late - stop["atraso_min"]
            extra_penalty += max(0.0, delta_late) * rules[stop["prioridade"]]["multa_min"]
            impacts.append(
                {
                    "ordem": stop["ordem"],
                    "nome": stop["nome"],
                    "prioridade": stop["prioridade"],
                    "nova_chegada": min_to_hhmm(arrival),
                    "prazo": stop["prazo"],
                    "atraso_original_min": stop["atraso_min"],
                    "novo_atraso_min": round(new_late, 1),
                    "passa_a_atrasar": stop["atraso_min"] <= 0.5 < new_late,
                }
            )
        return {
            "veiculo": route["veiculo"],
            "atraso_inicial_min": minutos,
            "paradas_que_passam_a_atrasar": [i["nome"] for i in impacts if i["passa_a_atrasar"]],
            "multa_adicional_estimada": round(extra_penalty, 2),
            "atraso_residual_no_retorno_min": round(shift, 1),
            "impacto_por_parada": impacts,
        }

    def historico(self, dias: int = 7) -> dict:
        if not self.store:
            return {"erro": "histórico indisponível"}
        runs = self.store.runs_since(int(dias))
        return aggregate_runs(runs, int(dias))


def aggregate_runs(runs: List[dict], days: int) -> dict:
    """Consolida KPIs de várias execuções (base dos relatórios diários/semanais)."""
    if not runs:
        return {"dias": days, "execucoes": 0}
    sols = [r["solucao"] for r in runs]
    n = len(runs)
    scenarios = {}
    for r in runs:
        scenarios[r["cenario"]["nome"]] = scenarios.get(r["cenario"]["nome"], 0) + 1
    return {
        "dias": days,
        "execucoes": n,
        "custo_total_soma": round(sum(s["custo_total"] for s in sols), 2),
        "custo_medio": round(sum(s["custo_total"] for s in sols) / n, 2),
        "economia_media_pct": round(sum(r["comparativo"]["economia_pct"] for r in runs) / n, 1),
        "economia_total_rs": round(sum(r["comparativo"]["economia_rs"] for r in runs), 2),
        "taxa_no_prazo_media_pct": round(sum(s["taxa_no_prazo"] for s in sols) / n * 100, 1),
        "criticas_atrasadas": sum(s["criticas_total"] - s["criticas_no_prazo"] for s in sols),
        "distancia_total_km": round(sum(s["distancia_km"] for s in sols), 1),
        "co2_total_kg": round(sum(s["co2_kg"] for s in sols), 1),
        "ocupacao_media_pct": round(sum(s["ocupacao_media"] for s in sols) / n * 100, 1),
        "veiculos_medios": round(sum(s["veiculos_usados"] for s in sols) / n, 1),
        "execucoes_com_frota_insuficiente": sum(1 for s in sols if s["veiculos_excedentes"] > 0),
        "atraso_total_min": round(sum(s["atraso_total_min"] for s in sols), 1),
        "entregas_total": sum(s["entregas"] for s in sols),
        "execucoes_por_cenario": scenarios,
    }


def build_tools(run: dict, store: Optional[HistoryStore] = None,
                risk_priority: Optional[str] = None) -> List[ToolSpec]:
    impl = RunTools(run, store)

    def scoped_risks(folga_minima_min: float = 15, prioridade: Optional[str] = risk_priority):
        if risk_priority is not None and prioridade != risk_priority:
            raise ValueError(f"A pergunta está restrita à prioridade {risk_priority}.")
        return impl.entregas_em_risco(folga_minima_min, prioridade)

    risk_description = "Entregas atrasadas ou com folga menor que o limite em relação ao prazo."
    if risk_priority:
        risk_description += f" Consulta restrita à prioridade {risk_priority} solicitada pelo usuário."
    priority_parameter = {"type": "string", "enum": [risk_priority] if risk_priority else ["critica", "alta", "rotina"],
                          "description": "Filtrar por prioridade; sem filtro consulta todas."}
    if risk_priority:
        priority_parameter["default"] = risk_priority
    vehicle_param = {
        "type": "string",
        "description": "Identificador do veículo exatamente como em listar_rotas, ex.: 'MOTO #1'",
    }
    return [
        ToolSpec(
            "resumo_execucao",
            "KPIs gerais da execução: custo, multas, prazo, distância, CO2, economia vs heurísticas.",
            {"type": "object", "properties": {}},
            impl.resumo_execucao,
        ),
        ToolSpec(
            "listar_rotas",
            "Lista todas as rotas/veículos com distância, duração, ocupação e atrasos.",
            {"type": "object", "properties": {}},
            impl.listar_rotas,
        ),
        ToolSpec(
            "detalhar_rota",
            "Sequência completa de paradas de um veículo com horários, janelas, prazos e carga.",
            {"type": "object", "properties": {"veiculo": vehicle_param}, "required": ["veiculo"]},
            impl.detalhar_rota,
        ),
        ToolSpec(
            "buscar_parada",
            "Encontra uma parada pelo nome (ou parte dele) e informa veículo, ordem e horário.",
            {
                "type": "object",
                "properties": {"nome": {"type": "string", "description": "Nome ou parte do nome"}},
                "required": ["nome"],
            },
            impl.buscar_parada,
        ),
        ToolSpec(
            "entregas_em_risco",
            risk_description,
            {
                "type": "object",
                "properties": {
                    "folga_minima_min": {"type": "number", "description": "Folga mínima aceitável em minutos (padrão 15)"},
                    "prioridade": priority_parameter
                },
            },
            scoped_risks,
        ),
        ToolSpec(
            "comparar_abordagens",
            "Compara o algoritmo genético com as heurísticas de referência (custo, km, prazo).",
            {"type": "object", "properties": {}},
            impl.comparar_abordagens,
        ),
        ToolSpec(
            "simular_atraso",
            "Simula um atraso em um veículo e mostra quais entregas passam a atrasar e a multa extra.",
            {
                "type": "object",
                "properties": {
                    "veiculo": vehicle_param,
                    "minutos": {"type": "number", "description": "Minutos de atraso"},
                    "a_partir_da_parada": {"type": "integer", "description": "Ordem da parada onde o atraso começa (padrão 1)"},
                },
                "required": ["veiculo", "minutos"],
            },
            impl.simular_atraso,
        ),
        ToolSpec(
            "historico",
            "KPIs consolidados das execuções dos últimos N dias (tendências).",
            {
                "type": "object",
                "properties": {"dias": {"type": "integer", "description": "Janela em dias (padrão 7)"}},
            },
            impl.historico,
        ),
    ]
