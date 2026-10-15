"""Geração de instruções para motoristas e relatórios (execução e período).

Fluxo de cada texto: monta os FATOS (JSON enxuto) -> renderiza o prompt versionado ->
chama o provedor -> avalia a qualidade -> persiste no histórico. Em modo offline (ou se
a LLM falhar) usa os templates determinísticos, para nunca deixar a equipe sem a folha.
"""

from __future__ import annotations

import json
from typing import Optional

from rotavital.llm import templates
from rotavital.llm.evaluation import evaluate
from rotavital.llm.prompts import load, render
from rotavital.llm.providers.base import LLMError, LLMProvider
from rotavital.llm.tools import aggregate_runs, find_route
from rotavital.storage.history import HistoryStore

STOP_FIELDS = (
    "ordem", "nome", "tipo", "carga", "prioridade", "refrigerado", "demanda_kg", "chegada",
    "saida", "janela", "prazo", "espera_min", "atraso_min", "folga_min", "carga_restante_kg",
)


def route_facts(route: dict) -> dict:
    return {
        "veiculo": route["veiculo"],
        "tipo": route["tipo_nome"],
        "refrigerado": route["refrigerado"],
        "saida": route["saida_deposito"],
        "retorno": route["retorno_deposito"],
        "distancia_km": route["distancia_km"],
        "duracao_min": route["duracao_min"],
        "carga_kg": route["carga_kg"],
        "paradas": [{k: s[k] for k in STOP_FIELDS} for s in route["paradas"]],
    }


def execution_facts(run: dict) -> dict:
    sol = run["solucao"]
    at_risk = [
        {
            "nome": s["nome"],
            "veiculo": r["veiculo"],
            "prioridade": s["prioridade"],
            "chegada": s["chegada"],
            "prazo": s["prazo"],
            "atraso_min": s["atraso_min"],
            "folga_min": s["folga_min"],
        }
        for r in sol["rotas"]
        for s in r["paradas"]
        if s["atraso_min"] > 0.5 or s["folga_min"] < 15
    ]
    return {
        "cenario": run["cenario"]["nome"],
        "kpis": {k: v for k, v in sol.items() if k != "rotas"},
        "comparativo": run["comparativo"],
        "baselines": [
            {k: b[k] for k in ("nome", "custo_total", "distancia_km", "veiculos_usados", "taxa_no_prazo")}
            for b in run["baselines"]
        ],
        "rotas": [
            {
                "veiculo": r["veiculo"],
                "tipo": r["tipo_nome"],
                "paradas": len(r["paradas"]),
                "distancia_km": r["distancia_km"],
                "duracao_min": r["duracao_min"],
                "ocupacao": r["ocupacao"],
                "uso_autonomia": r["uso_autonomia"],
                "paradas_atrasadas": r["paradas_atrasadas"],
            }
            for r in sol["rotas"]
        ],
        "em_risco": at_risk,
        "sugestoes": templates.rule_based_suggestions(sol, sol["rotas"]),
        "ga": {k: run["ga"][k] for k in ("geracoes", "motivo_parada", "tempo_s")},
    }


def _generate(provider: LLMProvider, prompt: str, fallback_text: str) -> tuple:
    """Chama a LLM; em falha devolve o template e o motivo."""
    if provider.offline:
        return fallback_text, provider.name, provider.model, None
    try:
        text = provider.complete(load("sistema_base"), prompt)
        if text.strip():
            return text, provider.name, provider.model, None
        reason = "resposta vazia"
    except LLMError as exc:
        reason = str(exc)
    note = f"\n\n> Texto gerado em modo de contingência (LLM indisponível: {reason})."
    return fallback_text + note, "offline", "modelos determinísticos", reason


def driver_instructions(
    run: dict, vehicle: str, provider: LLMProvider, store: Optional[HistoryStore] = None
) -> dict:
    route = find_route(run, vehicle)
    facts = route_facts(route)
    prompt = render(
        "instrucoes_motorista",
        veiculo=route["veiculo"],
        dados=json.dumps(facts, ensure_ascii=False, indent=1),
    )
    text, prov, model, error = _generate(provider, prompt, templates.driver_sheet(facts))
    quality = evaluate(provider, "folha de rota do motorista", text, facts, [p["nome"] for p in facts["paradas"]])
    if store:
        store.save_llm_output(run["id"], "instrucoes", text, prov, model, route["veiculo"], quality)
    return {"veiculo": route["veiculo"], "markdown": text, "provedor": prov, "modelo": model, "avaliacao": quality, "erro_llm": error}


def execution_report(run: dict, provider: LLMProvider, store: Optional[HistoryStore] = None) -> dict:
    facts = execution_facts(run)
    prompt = render(
        "relatorio_execucao",
        cenario=facts["cenario"],
        dados=json.dumps(facts, ensure_ascii=False, indent=1),
    )
    text, prov, model, error = _generate(provider, prompt, templates.execution_report(facts))
    quality = evaluate(provider, "relatório gerencial da operação", text, facts)
    if store:
        store.save_llm_output(run["id"], "relatorio_execucao", text, prov, model, None, quality)
    return {"markdown": text, "provedor": prov, "modelo": model, "avaliacao": quality, "erro_llm": error}


def period_report(store: HistoryStore, days: int, provider: LLMProvider) -> dict:
    label = "diário" if days == 1 else ("semanal" if days == 7 else f"dos últimos {days} dias")
    agg = aggregate_runs(store.runs_since(days), days)
    if not agg.get("execucoes"):
        text = templates.period_report(agg, label)
        return {"dias": days, "execucoes": 0, "agregado": agg, "markdown": text,
                "provedor": "offline", "modelo": "-", "avaliacao": None, "erro_llm": None}
    prompt = render("relatorio_periodo", periodo=label.upper(), dados=json.dumps(agg, ensure_ascii=False, indent=1))
    text, prov, model, error = _generate(provider, prompt, templates.period_report(agg, label))
    quality = evaluate(provider, f"relatório {label}", text, agg)
    store.save_llm_output(None, f"relatorio_periodo_{days}d", text, prov, model, None, quality)
    return {"dias": days, "execucoes": agg["execucoes"], "agregado": agg, "markdown": text,
            "provedor": prov, "modelo": model, "avaliacao": quality, "erro_llm": error}
