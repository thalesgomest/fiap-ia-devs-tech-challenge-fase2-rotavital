"""Gera as figuras e os números do relatório técnico em ``reports/figures/``.

Uso:
    python scripts/gerar_figuras.py --exp experiments/<pasta-da-bateria>

A pasta de experimentos é a criada por ``make experimentos`` (resultados.csv e
convergencia.json). A solução do GA mostrada nos mapas é a configuração E1 com
semente 1, recalculada aqui de forma determinística.

Requer matplotlib (pip install matplotlib).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from rotavital.domain.models import hhmm_to_min  # noqa: E402
from rotavital.domain.scenarios import load_scenario  # noqa: E402
from rotavital.optimization.baselines import BASELINES  # noqa: E402
from rotavital.optimization.evaluator import RouteEvaluator  # noqa: E402
from rotavital.optimization.experiments import BASE  # noqa: E402
from rotavital.optimization.ga import GeneticOptimizer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "figures"

NAVY = "#13293D"
SOFT = "#5B6B78"
GRID = "#D9DFE4"
PRIORITY_COLORS = {"critica": "#C0392B", "alta": "#D98A1E", "rotina": "#3E6E95"}
PRIORITY_LABELS = {"critica": "Crítica", "alta": "Alta", "rotina": "Rotina"}
VEHICLE_COLORS = ["#1F77B4", "#2CA02C", "#9467BD", "#E377C2", "#8C564B", "#17BECF", "#BCBD22", "#FF7F0E", "#7F7F7F", "#D62728", "#393B79"]
GA_COLOR = "#2A8C6E"
NICE = {"E1": "E1 · base", "E2": "E2 · população 40", "E3": "E3 · população 250", "E4": "E4 · mutação fixa 0,6",
        "E5": "E5 · cruzamento PMX", "E6": "E6 · cruzamento ERX", "E7": "E7 · sem busca local",
        "E8": "E8 · sem sementes"}
BASE_COLOR = "#9AA8B2"
CW_COLOR = "#3E6E95"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": NAVY,
    "axes.titlecolor": NAVY,
    "axes.titlesize": 12,
    "xtick.color": SOFT,
    "ytick.color": SOFT,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "figure.dpi": 100,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})


def _save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, facecolor="white")
    plt.close(fig)
    print("  figura:", name)


def _map_axes(ax, scenario):
    ax.set_aspect(1 / 0.917)  # correção de aspecto para latitude ~ -23,5°
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.xaxis.set_major_locator(MaxNLocator(5))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    ax.plot(scenario.depot.lon, scenario.depot.lat, marker="*", markersize=20, color=NAVY,
            markeredgecolor="white", zorder=6, linestyle="none")


def fig_cenario(scenario):
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    _map_axes(ax, scenario)
    for code, color in PRIORITY_COLORS.items():
        pts = [s for s in scenario.stops if s.priority == code]
        ax.scatter([s.lon for s in pts], [s.lat for s in pts], s=[20 + s.demand_kg * 1.2 for s in pts],
                   color=color, alpha=0.85, edgecolor="white", linewidth=0.8, zorder=4)
    cold = [s for s in scenario.stops if s.refrigerated]
    ax.scatter([s.lon for s in cold], [s.lat for s in cold], s=[60 + s.demand_kg * 1.2 for s in cold],
               facecolor="none", edgecolor="#3BA3D0", linewidth=1.4, zorder=5)
    handles = [Line2D([], [], marker="o", linestyle="none", color=c, label=PRIORITY_LABELS[k]) for k, c in PRIORITY_COLORS.items()]
    handles += [Line2D([], [], marker="o", linestyle="none", markerfacecolor="none", markeredgecolor="#3BA3D0", label="Carga refrigerada"),
                Line2D([], [], marker="*", linestyle="none", color=NAVY, markersize=12, label="Hemocentro (depósito)")]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8.5, frameon=False)
    ax.set_title(f"{scenario.name}: {len(scenario.stops)} entregas (tamanho = peso em kg)")
    _save(fig, "fig01_cenario.png")


def _plot_routes(ax, scenario, solution, title):
    _map_axes(ax, scenario)
    depot = (scenario.depot.lon, scenario.depot.lat)
    handles = []
    for i, route in enumerate(solution["rotas"]):
        color = VEHICLE_COLORS[i % len(VEHICLE_COLORS)]
        xs = [depot[0]] + [p["lon"] for p in route["paradas"]] + [depot[0]]
        ys = [depot[1]] + [p["lat"] for p in route["paradas"]] + [depot[1]]
        style = "--" if route["excedente"] else "-"
        ax.plot(xs, ys, style, color=color, linewidth=1.8, alpha=0.9, zorder=3)
        ax.scatter(xs[1:-1], ys[1:-1], color=color, s=22, edgecolor="white", linewidth=0.6, zorder=4)
        label = f"{route['veiculo']} · {len(route['paradas'])} entregas · {route['distancia_km']:.0f} km"
        if route["excedente"]:
            label += " (excedente)"
        handles.append(Line2D([], [], color=color, linestyle=style, linewidth=2, label=label))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8.5, frameon=False, title="Veículo · entregas · distância", title_fontsize=8.5)
    ax.set_title(title)


def fig_rotas(scenario, ga_solution, cw_solution):
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    _plot_routes(ax, scenario, ga_solution,
                 f"Algoritmo genético: R$ {ga_solution['custo_total']:,.2f} · {ga_solution['veiculos_usados']} veículos"
                 .replace(",", "X").replace(".", ",").replace("X", "."))
    _save(fig, "fig02_rotas_ga.png")
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    _plot_routes(ax, scenario, cw_solution,
                 f"Clarke-Wright: R$ {cw_solution['custo_total']:,.2f} · {cw_solution['veiculos_usados']} veículos"
                 .replace(",", "X").replace(".", ",").replace("X", "."))
    _save(fig, "fig03_rotas_clarke_wright.png")


def fig_timeline(scenario, solution):
    routes = solution["rotas"]
    fig, ax = plt.subplots(figsize=(10, 0.55 * len(routes) + 1.6))
    for row, route in enumerate(routes):
        y = len(routes) - 1 - row
        prev = hhmm_to_min(route["saida_deposito"])
        for p in route["paradas"]:
            arr, start, end = hhmm_to_min(p["chegada"]), hhmm_to_min(p["inicio_atendimento"]), hhmm_to_min(p["saida"])
            ax.barh(y, arr - prev, left=prev, height=0.5, color="#B8C7D3")
            if start > arr:
                ax.barh(y, start - arr, left=arr, height=0.5, color="#F2D7A6")
            ax.barh(y, end - start, left=start, height=0.5, color=PRIORITY_COLORS[p["prioridade"]])
            if p["prioridade"] == "critica":
                ax.plot(hhmm_to_min(p["prazo"]), y + 0.38, marker="v", color=PRIORITY_COLORS["critica"], markersize=6)
            prev = end
        ret = hhmm_to_min(route["retorno_deposito"])
        ax.barh(y, ret - prev, left=prev, height=0.5, color="#B8C7D3")
    ax.set_yticks(range(len(routes)))
    ax.set_yticklabels([r["veiculo"] for r in reversed(routes)])
    ticks = list(range(7 * 60, 18 * 60 + 1, 60))
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t // 60:02d}:00" for t in ticks])
    ax.set_xlim(7 * 60 - 10, max(hhmm_to_min(r["retorno_deposito"]) for r in routes) + 20)
    ax.grid(axis="y", visible=False)
    handles = [Patch(color="#B8C7D3", label="Deslocamento"), Patch(color="#F2D7A6", label="Espera pela janela")]
    handles += [Patch(color=c, label=f"Atendimento · {PRIORITY_LABELS[k]}") for k, c in PRIORITY_COLORS.items()]
    handles += [Line2D([], [], marker="v", linestyle="none", color=PRIORITY_COLORS["critica"], label="Prazo de entrega crítica")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8, frameon=False)
    ax.set_title("Linha do tempo de cada veículo na solução do GA")
    _save(fig, "fig04_linha_do_tempo.png")


def fig_custos(breakdown):
    names = [b["nome"] for b in breakdown]
    oper = [b["custo_operacional"] for b in breakdown]
    late = [b["multa_atraso"] for b in breakdown]
    fleet = [b["multa_frota"] for b in breakdown]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    y = range(len(names))
    ax.barh(y, oper, color=[GA_COLOR if "genético" in n else BASE_COLOR for n in names], label="Custo operacional")
    ax.barh(y, late, left=oper, color="#D98A1E", label="Multa por atraso")
    ax.barh(y, fleet, left=[o + atr for o, atr in zip(oper, late, strict=True)], color="#C0392B", label="Multa por frota excedente")
    for i, b in enumerate(breakdown):
        total = b["custo_total"]
        ax.text(total + 120, i, f"R$ {total:,.0f}".replace(",", "."), va="center", fontsize=9, color=NAVY)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("Custo do dia (R$)")
    ax.set_xlim(0, max(b["custo_total"] for b in breakdown) * 1.15)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8.5)
    ax.set_title("Composição do custo: algoritmo genético vs. heurísticas")
    _save(fig, "fig05_composicao_custo.png")


def fig_convergencia(curves, baselines_cost):
    e1 = next(v for k, v in curves.items() if k.startswith("E1"))
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for c in e1:
        ax.plot(range(1, len(c) + 1), c, color=GA_COLOR, alpha=0.35, linewidth=1)
    longest = max(len(c) for c in e1)
    mean = []
    for g in range(longest):
        vals = [c[min(g, len(c) - 1)] for c in e1]
        mean.append(statistics.mean(vals))
    ax.plot(range(1, longest + 1), mean, color=GA_COLOR, linewidth=2.4, label=f"GA E1: média de {len(e1)} sementes")
    cw = baselines_cost["Clarke-Wright (economias)"]
    ax.axhline(cw, color=CW_COLOR, linestyle="--", linewidth=1.4, label=f"Clarke-Wright (R$ {cw:,.0f})".replace(",", "."))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"R$ {v:,.0f}".replace(",", ".")))
    ax.set_xlabel("Geração")
    ax.set_ylabel("Melhor custo do dia")
    ax.legend(fontsize=9)
    ax.set_title("Convergência do GA (cada linha fina é uma semente)")
    _save(fig, "fig06_convergencia.png")


def fig_experimentos(rows):
    groups = {}
    for r in rows:
        if r["experimento"].startswith("Baseline"):
            continue
        groups.setdefault(r["experimento"], []).append(float(r["custo_total"]))
    labels = list(groups)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    bp = ax.boxplot([groups[k] for k in labels], orientation="horizontal", patch_artist=True, widths=0.55,
                    medianprops={"color": NAVY, "linewidth": 1.6})
    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(GA_COLOR if i == 0 else "#CFE3DC")
        patch.set_edgecolor(GA_COLOR)
    short = [NICE.get(k.split("-")[0], k) for k in labels]
    ax.set_yticks(range(1, len(labels) + 1))
    ax.set_yticklabels(short)
    ax.invert_yaxis()
    ax.set_xlabel("Custo do dia (R$)")
    ax.grid(axis="y", visible=False)
    ax.set_title("Distribuição do custo por configuração (cada caixa = 10 sementes)")
    _save(fig, "fig07_experimentos.png")


def fig_tempo(rows):
    groups = {}
    for r in rows:
        if r["experimento"].startswith("Baseline"):
            continue
        g = groups.setdefault(r["experimento"], {"custo": [], "tempo": []})
        g["custo"].append(float(r["custo_total"]))
        g["tempo"].append(float(r["tempo_s"]))
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for i, (k, g) in enumerate(groups.items()):
        x, y = statistics.mean(g["tempo"]), statistics.mean(g["custo"])
        ax.scatter(x, y, s=80, color=GA_COLOR if i == 0 else "#7FB8A6", edgecolor="white", zorder=3)
        ax.annotate(k.split("-")[0], (x, y), textcoords="offset points", xytext=(7, 4), fontsize=9, color=NAVY)
    ax.set_xlabel("Tempo médio por execução (s)")
    ax.set_ylabel("Custo médio (R$)")
    ax.set_title("Custo × tempo de processamento (médias de 10 sementes)")
    _save(fig, "fig08_custo_tempo.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp", required=True, help="pasta da bateria de experimentos")
    parser.add_argument("--cenario", default="sp-hemorrede-40")
    args = parser.parse_args()
    exp_dir = Path(args.exp)

    scenario = load_scenario(args.cenario)
    ev = RouteEvaluator(scenario)
    print("Calculando a solução do GA (E1, semente 1)...")
    result = GeneticOptimizer(ev, replace(BASE, seed=1)).run()
    ga_solution = ev.solution_from_tour(result.best_tour)

    breakdown = []
    solutions = {}
    for key, (label, fn) in BASELINES.items():
        sol = ev.build_solution(fn(ev))
        solutions[key] = sol
        breakdown.append({"nome": label, **{k: sol[k] for k in ("custo_total", "custo_operacional", "multa_atraso",
                                                                  "multa_frota", "veiculos_usados", "distancia_km",
                                                                  "taxa_no_prazo", "ocupacao_media", "co2_kg")}})
    breakdown.append({"nome": "Algoritmo genético", **{k: ga_solution[k] for k in ("custo_total", "custo_operacional",
                                                                                    "multa_atraso", "multa_frota",
                                                                                    "veiculos_usados", "distancia_km",
                                                                                    "taxa_no_prazo", "ocupacao_media",
                                                                                    "co2_kg")}})

    with open(exp_dir / "resultados.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    curves = json.loads((exp_dir / "convergencia.json").read_text(encoding="utf-8"))
    baselines_cost = {r["experimento"].replace("Baseline: ", ""): float(r["custo_total"])
                      for r in rows if r["experimento"].startswith("Baseline")}

    fig_cenario(scenario)
    fig_rotas(scenario, ga_solution, solutions["clarke_wright"])
    fig_timeline(scenario, ga_solution)
    fig_custos(breakdown)
    fig_convergencia(curves, baselines_cost)
    fig_experimentos(rows)
    fig_tempo(rows)

    summary = {
        "cenario": scenario.name,
        "ga_execucao": {"geracoes": result.generations, "motivo_parada": result.stop_reason,
                        "tempo_s": result.elapsed_s, "avaliacoes": result.evaluations},
        "composicao": breakdown,
        "rotas_ga": [{k: r[k] for k in ("veiculo", "tipo_nome", "saida_deposito", "retorno_deposito", "distancia_km",
                                       "duracao_min", "carga_kg", "capacidade_kg", "ocupacao", "uso_autonomia",
                                       "paradas_atrasadas")} | {"paradas": len(r["paradas"]),
                     "criticas": sum(1 for p in r["paradas"] if p["prioridade"] == "critica"),
                     "refrigeradas": sum(1 for p in r["paradas"] if p["refrigerado"])}
                     for r in ga_solution["rotas"]],
        "kpis_ga": {k: v for k, v in ga_solution.items() if k != "rotas"},
    }
    (OUT / "dados_relatorio.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Resumo em", OUT / "dados_relatorio.json")


if __name__ == "__main__":
    main()
