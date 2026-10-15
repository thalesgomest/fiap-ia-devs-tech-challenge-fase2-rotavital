// Gráficos Chart.js: registro central para destruir/reaproveitar instâncias.
import { fmt } from './util.js';

const registry = {};

export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function setupChartDefaults() {
  if (!window.Chart) return;
  Chart.defaults.font.family = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = cssVar('--muted') || '#5a6b6a';
  Chart.defaults.borderColor = cssVar('--border') || '#e1e8e8';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.boxHeight = 8;
}

/** Cria (ou recria) o gráfico identificado por `key`. */
export function makeChart(key, canvas, config) {
  registry[key]?.destroy();
  if (!window.Chart || !canvas) return null;
  registry[key] = new Chart(canvas, config);
  return registry[key];
}
export const getChart = (key) => registry[key] || null;
export function destroyChart(key) {
  registry[key]?.destroy();
  delete registry[key];
}

// Cores das abordagens de referência (linhas tracejadas / barras)
export const BASELINE_COLORS = ['#94a3b8', '#a78bfa', '#f472b6', '#fb923c', '#38bdf8', '#a3a3a3'];

export const moneyTick = (v) => fmt.moneyShort(v);
export const moneyTooltip = (ctx) => `${ctx.dataset.label}: ${fmt.money(ctx.parsed.y)}`;

/** Opções comuns de um gráfico de linhas por geração. */
export function generationLineOptions(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'nearest', axis: 'x', intersect: false },
    plugins: {
      legend: { position: 'bottom' },
      tooltip: {
        callbacks: {
          title: (items) => (items.length ? `Geração ${items[0].parsed.x}` : ''),
          label: moneyTooltip,
        },
      },
    },
    scales: {
      x: { type: 'linear', min: 1, title: { display: true, text: 'Geração' }, grid: { display: false }, ticks: { precision: 0 } },
      y: { ticks: { callback: moneyTick }, title: { display: true, text: 'Custo' } },
    },
    ...extra,
  };
}
