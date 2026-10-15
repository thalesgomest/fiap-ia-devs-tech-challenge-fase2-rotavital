"""Textos determinísticos usados no modo offline (sem LLM) e como contingência."""

from __future__ import annotations

from typing import List


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def driver_sheet(f: dict) -> str:
    lines = [
        f"# Folha de rota - {f['veiculo']}",
        f"**Saída:** {f['saida']} · **Retorno previsto:** {f['retorno']} · "
        f"**Distância:** {f['distancia_km']} km · **Carga total:** {f['carga_kg']} kg",
        "",
        "## Antes de sair",
        "- Conferir as cargas na ordem inversa de entrega (a primeira entrega fica mais acessível).",
    ]
    if f["refrigerado"] and any(p["refrigerado"] for p in f["paradas"]):
        lines.append("- Verificar temperatura do baú refrigerado e registrar no checklist.")
    lines += ["- Levar documentos de transporte e comprovantes de entrega.", "", "## Sequência de entregas"]
    for p in f["paradas"]:
        tags = []
        if p["prioridade"] == "critica":
            tags.append("⚠️ PRIORIDADE CRÍTICA")
        if p["refrigerado"]:
            tags.append("❄️ manter refrigerado")
        if p["espera_min"] > 0:
            tags.append(f"aguardar abertura ({p['espera_min']} min)")
        lines.append(
            f"{p['ordem']}. **{p['nome']}** - chegada {p['chegada']} · janela {p['janela']} · "
            f"prazo {p['prazo']} · entregar {p['demanda_kg']} kg de {p['carga']}. " + " ".join(tags)
        )
    risky = [p for p in f["paradas"] if p["atraso_min"] > 0 or p["folga_min"] < 15]
    lines += ["", "## Atenção"]
    if risky:
        for p in risky:
            status = f"atraso previsto de {p['atraso_min']} min" if p["atraso_min"] > 0 else f"folga de apenas {p['folga_min']} min"
            lines.append(f"- {p['nome']}: {status}. Avise a central ao sair da parada anterior.")
    else:
        lines.append("- Nenhuma entrega com risco de atraso no planejamento.")
    lines.append("- Em caso de imprevisto, contate a central antes de alterar a ordem das entregas críticas.")
    return "\n".join(lines)


def execution_report(f: dict) -> str:
    k = f["kpis"]
    c = f["comparativo"]
    lines = [
        f"# Relatório da operação - {f['cenario']}",
        "## 1. Resumo executivo",
        f"A operação atende {k['entregas']} entregas com {k['veiculos_usados']} veículos, ao custo total de "
        f"R$ {k['custo_total']:.2f}. {k['entregas_no_prazo']} de {k['entregas']} entregas ficam no prazo "
        f"({_pct(k['taxa_no_prazo'])}) e {k['criticas_no_prazo']} de {k['criticas_total']} críticas são atendidas a tempo. "
        f"Em relação à melhor heurística de referência ({c['melhor_baseline']}), a economia é de "
        f"R$ {c['economia_rs']:.2f} ({c['economia_pct']}%).",
        "## 2. Eficiência e economia de recursos",
        "| Abordagem | Custo (R$) | Distância (km) | Veículos | No prazo |",
        "|---|---|---|---|---|",
        f"| Algoritmo genético | {k['custo_total']:.2f} | {k['distancia_km']} | {k['veiculos_usados']} | {_pct(k['taxa_no_prazo'])} |",
    ]
    for b in f["baselines"]:
        lines.append(
            f"| {b['nome']} | {b['custo_total']:.2f} | {b['distancia_km']} | {b['veiculos_usados']} | {_pct(b['taxa_no_prazo'])} |"
        )
    lines += [
        "",
        f"Distância total de {k['distancia_km']} km, ocupação média de {_pct(k['ocupacao_media'])} "
        f"e emissão estimada de {k['co2_kg']} kg de CO2.",
        "## 3. Riscos operacionais",
    ]
    if f["em_risco"]:
        for r in f["em_risco"]:
            lines.append(f"- {r['nome']} ({r['veiculo']}): chegada {r['chegada']}, prazo {r['prazo']}, atraso {r['atraso_min']} min.")
    else:
        lines.append("- Nenhuma entrega atrasada ou com folga inferior a 15 minutos.")
    lines += ["## 4. Sugestões de melhoria do processo"] + [f"- {s}" for s in f["sugestoes"]]
    g = f["ga"]
    lines += [
        "## 5. Notas técnicas",
        f"O algoritmo genético executou {g['geracoes']} gerações em {g['tempo_s']} s "
        f"(motivo de parada: {g['motivo_parada']}).",
    ]
    return "\n".join(lines)


def rule_based_suggestions(kpis: dict, routes: List[dict]) -> List[str]:
    """Sugestões derivadas de regras simples sobre os indicadores (usadas também como
    dica para a LLM e no modo offline)."""
    tips = []
    if kpis.get("veiculos_excedentes", 0) > 0:
        tips.append("A frota disponível é insuficiente: avalie contratar veículos extras ou dividir a operação em dois turnos.")
    if kpis["criticas_total"] and kpis["criticas_no_prazo"] < kpis["criticas_total"]:
        tips.append("Há entregas críticas fora do SLA: reserve motos com baú térmico exclusivamente para hemocomponentes urgentes.")
    if kpis["ocupacao_media"] < 0.4:
        tips.append("Ocupação média baixa: consolide cargas de rotina em menos viagens ou negocie janelas de recebimento mais amplas.")
    long_routes = [r["veiculo"] for r in routes if r.get("uso_autonomia", 0) > 0.85]
    if long_routes:
        tips.append(f"Rotas próximas do limite de autonomia ({', '.join(long_routes)}): planeje ponto de abastecimento/recarga.")
    waits = sum(p["espera_min"] for r in routes for p in r["paradas"])
    if waits > 30:
        tips.append(f"Os veículos aguardam {waits:.0f} min no total por abertura de janelas: negociar recebimento a partir das 07:00 reduziria a jornada.")
    if not tips:
        tips.append("Operação equilibrada: mantenha o monitoramento diário dos prazos das entregas críticas.")
    return tips


def period_report(agg: dict, label: str) -> str:
    if not agg.get("execucoes"):
        return f"# Relatório {label} de rotas\nNenhuma execução registrada no período."
    lines = [
        f"# Relatório {label} de rotas",
        "## Panorama",
        f"{agg['execucoes']} operações planejadas, custo total de R$ {agg['custo_total_soma']:.2f} "
        f"(média de R$ {agg['custo_medio']:.2f}). Entregas no prazo: {agg['taxa_no_prazo_media_pct']}% em média; "
        f"entregas críticas atrasadas: {agg['criticas_atrasadas']}.",
        "## Economia de tempo e recursos",
        f"Economia acumulada de R$ {agg['economia_total_rs']:.2f} frente às heurísticas de referência "
        f"({agg['economia_media_pct']}% em média). Distância total de {agg['distancia_total_km']} km, "
        f"{agg['co2_total_kg']} kg de CO2 e ocupação média de {agg['ocupacao_media_pct']}%.",
        "## Padrões identificados",
    ]
    if agg["execucoes_com_frota_insuficiente"]:
        lines.append(f"- {agg['execucoes_com_frota_insuficiente']} execução(ões) exigiram mais veículos do que a frota disponível.")
    if agg["ocupacao_media_pct"] < 40:
        lines.append("- A ocupação média da frota está abaixo de 40%.")
    if agg["criticas_atrasadas"]:
        lines.append("- Há atrasos recorrentes em entregas críticas.")
    if len(lines) and lines[-1] == "## Padrões identificados":
        lines.append("- Nenhuma anomalia relevante nos indicadores.")
    lines += [
        "## Recomendações",
        "- Revisar o dimensionamento da frota refrigerada com base nos dias de maior demanda.",
        "- Acompanhar semanalmente a taxa de entregas críticas no prazo como indicador principal.",
    ]
    if agg["execucoes"] < 3:
        lines.append("\n*Poucas execuções no período: conclusões com baixa confiança.*")
    return "\n".join(lines)
