"""Assistente conversacional: responde perguntas em linguagem natural sobre as rotas.

Estratégia em camadas:
  1. LLM com ferramentas (function calling) - padrão;
  2. se o modelo não suporta ferramentas, injeta um contexto compacto no prompt;
  3. sem LLM (offline ou falha), um roteador de intenções usa as mesmas ferramentas.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from rotavital.config import settings
from rotavital.llm import templates
from rotavital.llm.prompts import load, render
from rotavital.llm.providers.base import ChatResult, LLMError, LLMProvider, ToolCall, ToolsUnsupported
from rotavital.llm.tools import RunTools, _norm, build_tools, requested_priority
from rotavital.storage.history import HistoryStore

MAX_HISTORY = 12


def _to_wire(messages: List[dict]) -> List[Dict[str, str]]:
    role = {"usuario": "user", "assistente": "assistant"}
    return [{"role": role[m["papel"]], "content": m["conteudo"]} for m in messages[-MAX_HISTORY:]]


def _trace_out(calls: List[ToolCall]) -> List[dict]:
    return [
        {"nome": c.name, "argumentos": c.arguments, "resumo": c.result[:600]}
        for c in calls
    ]


def answer(run: dict, messages: List[dict], provider: LLMProvider, store: Optional[HistoryStore] = None) -> dict:
    question = messages[-1]["conteudo"] if messages else ""
    if provider.offline:
        text, calls = offline_answer(run, question, store)
        return {"resposta": text, "ferramentas": _trace_out(calls), "provedor": provider.name, "modelo": provider.model}

    tools = build_tools(run, store, risk_priority=requested_priority(question))
    system = load("sistema_base") + "\n\n" + render(
        "assistente_chat",
        cenario=run["cenario"]["nome"],
        run_id=run["id"],
        veiculos=", ".join(r["veiculo"] for r in run["solucao"]["rotas"]),
    )
    try:
        try:
            result = provider.chat(system, _to_wire(messages), tools)
        except ToolsUnsupported:
            result = ChatResult(_context_answer(run, messages, provider, store))
        text, calls = result.text, result.tool_calls
        if not text.strip():
            raise LLMError("A LLM retornou uma resposta vazia.")
    except LLMError as exc:
        if not settings.llm_fallback_offline:
            raise
        text, calls = offline_answer(run, question, store)
        text += f"\n\n> Resposta em modo de contingência (LLM indisponível: {exc})."
        return {"resposta": text, "ferramentas": _trace_out(calls), "provedor": "offline", "modelo": "modelos determinísticos", "erro_llm": str(exc)}
    if store:
        store.save_llm_output(run["id"], "chat", f"P: {question}\nR: {text}", provider.name, provider.model)
    return {"resposta": text or "Não consegui gerar uma resposta.", "ferramentas": _trace_out(calls),
            "provedor": provider.name, "modelo": provider.model}


def _context_answer(run: dict, messages: List[dict], provider: LLMProvider, store) -> str:
    """Plano B para modelos sem function calling: contexto compacto no próprio prompt."""
    impl = RunTools(run, store)
    context = {
        "resumo": impl.resumo_execucao(),
        "rotas": [impl.detalhar_rota(r["veiculo"]) for r in run["solucao"]["rotas"]],
    }
    history = "\n".join(f"{m['papel']}: {m['conteudo']}" for m in messages[-MAX_HISTORY:])
    prompt = f"DADOS DA OPERAÇÃO (JSON):\n{json.dumps(context, ensure_ascii=False)}\n\nCONVERSA:\n{history}\n\nResponda à última pergunta do usuário."
    return provider.complete(load("sistema_base"), prompt)


# ------------------------------------------------------------------ offline
_MINUTES_RE = re.compile(r"(\d+)\s*(?:min|minutos)")


def _call(tools, name: str, calls: List[ToolCall], **args):
    """Executa a ferramenta diretamente (sem serializar) e registra o rastro."""
    try:
        result = tools[name].handler(**args)
    except KeyError:
        result = {"erro": "não encontrado"}
    calls.append(ToolCall(name, args, json.dumps(result, ensure_ascii=False, default=str)[:600]))
    return result


def _match_stop(run: dict, normalized_question: str) -> Optional[str]:
    """Acha a parada citada pelo nome completo ou pelo final do nome (o bairro)."""
    best, best_len = None, 0
    for route in run["solucao"]["rotas"]:
        for stop in route["paradas"]:
            words = _norm(stop["nome"]).split()
            for k in range(len(words)):
                suffix = " ".join(words[k:])
                if len(suffix) > 3 and suffix in normalized_question and len(suffix) > best_len:
                    best, best_len = stop["nome"], len(suffix)
                    break
    return best


def offline_answer(run: dict, question: str, store=None) -> tuple:
    """Roteador de intenções por palavras-chave sobre as mesmas ferramentas da LLM."""
    tools = {t.name: t for t in build_tools(run, store, risk_priority=requested_priority(question))}
    calls: List[ToolCall] = []
    q = _norm(question)
    vehicle_id = next(
        (r["veiculo"] for r in run["solucao"]["rotas"] if re.search(rf"\b{re.escape(_norm(r['veiculo']))}\b", q)),
        None,
    )

    if vehicle_id and ("atras" in q or "e se" in q) and _MINUTES_RE.search(q):
        minutes = float(_MINUTES_RE.search(q).group(1))
        sim = _call(tools, "simular_atraso", calls, veiculo=vehicle_id, minutos=minutes)
        if "erro" in sim:
            return f"Não encontrei o veículo {vehicle_id}.", calls
        affected = sim["paradas_que_passam_a_atrasar"]
        text = (
            f"Com {minutes:g} min de atraso na **{sim['veiculo']}**, "
            + (f"passam a atrasar: {', '.join(affected)}." if affected else "nenhuma entrega passa a ficar fora do prazo.")
            + f" Multa adicional estimada: R$ {sim['multa_adicional_estimada']:.2f}. "
            f"O veículo retorna {sim['atraso_residual_no_retorno_min']} min mais tarde."
        )
        return text, calls

    if vehicle_id:
        route = _call(tools, "detalhar_rota", calls, veiculo=vehicle_id)
        if "erro" in route:
            return f"Não encontrei o veículo {vehicle_id}.", calls
        lines = [f"**{route['veiculo']}** ({route['tipo_nome']}) sai às {route['saida_deposito']} e retorna às "
                 f"{route['retorno_deposito']}, {route['distancia_km']} km, ocupação {route['ocupacao'] * 100:.0f}%:"]
        for s in route["paradas"]:
            flag = " ⚠️ crítica" if s["prioridade"] == "critica" else ""
            late = f" (atraso {s['atraso_min']} min)" if s["atraso_min"] > 0.5 else ""
            lines.append(f"{s['ordem']}. {s['nome']} - chegada {s['chegada']}, prazo {s['prazo']}{flag}{late}")
        return "\n".join(lines), calls

    if "risco" in q or "atras" in q or "prazo" in q:
        risky = _call(tools, "entregas_em_risco", calls)
        if risky and "mensagem" in risky[0]:
            return risky[0]["mensagem"], calls
        lines = ["Entregas que exigem atenção:"]
        for s in risky:
            lines.append(f"- **{s['nome']}** ({s['veiculo']}, {s['prioridade']}): chegada {s['chegada']}, prazo {s['prazo']} - {s['situacao']}")
        return "\n".join(lines), calls

    if any(w in q for w in ("econom", "compar", "clarke", "heurist", "vizinho")):
        cmp_ = _call(tools, "comparar_abordagens", calls)
        lines = ["| Abordagem | Custo (R$) | km | Veículos |", "|---|---|---|---|"]
        for row in cmp_["tabela"]:
            lines.append(f"| {row['abordagem']} | {row['custo_total']:.2f} | {row['distancia_km']} | {row['veiculos']} |")
        c = cmp_["comparativo"]
        lines.append(f"\nEconomia de R$ {c['economia_rs']:.2f} ({c['economia_pct']}%) frente a {c['melhor_baseline']}.")
        return "\n".join(lines), calls

    if any(w in q for w in ("histor", "semana", "ontem", "periodo")):
        agg = _call(tools, "historico", calls, dias=7)
        if not agg.get("execucoes"):
            return "Não há execuções registradas nos últimos 7 dias.", calls
        return (f"Nos últimos 7 dias foram {agg['execucoes']} execuções, custo médio de R$ {agg['custo_medio']:.2f} "
                f"e {agg['taxa_no_prazo_media_pct']}% de entregas no prazo."), calls

    stop_match = _match_stop(run, q)
    if stop_match:
        h = _call(tools, "buscar_parada", calls, nome=stop_match)[0]
        return (f"**{h['nome']}** está na rota da **{h['veiculo']}** (parada {h['ordem']}), chegada prevista "
                f"{h['chegada']}, prazo {h['prazo']}, {h['demanda_kg']} kg de {h['carga']}."), calls

    summary = _call(tools, "resumo_execucao", calls)
    k = summary["kpis"]
    tips = templates.rule_based_suggestions(k, run["solucao"]["rotas"])
    if any(w in q for w in ("reduz", "melhor", "sugest", "custo", "otimiz")):
        return "Sugestões com base nos indicadores:\n" + "\n".join(f"- {t}" for t in tips), calls
    return (
        f"A operação **{summary['cenario']}** custa R$ {k['custo_total']:.2f}, usa {k['veiculos_usados']} veículos e "
        f"tem {k['taxa_no_prazo'] * 100:.1f}% das entregas no prazo.\n\n"
        "Modo offline: pergunte sobre um veículo (ex.: 'rota da MOTO #1'), entregas em risco, "
        "simulação de atraso ('VAN-REF #1 atrasar 30 min'), economia ou uma parada pelo bairro."
    ), calls
