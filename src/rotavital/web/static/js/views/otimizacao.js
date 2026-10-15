// Passo 3 — acompanhamento ao vivo da execução (polling do progresso).
import { state, emit } from '../state.js';
import { $, esc, fmt, api, toast, toastError, sleep } from '../util.js';
import { makeColorMap } from '../domain.js';
import { getMap, fitTo, refreshMap, depotMarker, stopMarker, routeLine } from '../maps.js';
import { makeChart, getChart, cssVar, generationLineOptions, BASELINE_COLORS } from '../charts.js';
import { setRun, fetchRun } from '../runs.js';
import { go } from '../nav.js';

const POLL_MS = 700;
const STATUS = {
  executando: 'Executando',
  concluido: 'Concluída',
  interrompido: 'Interrompida',
  erro: 'Erro',
};

let timer = null;
let baseLayer = null;
let routesLayer = null;
let lastRoutesKey = '';
let failures = 0;

function stopPolling() {
  clearTimeout(timer);
  timer = null;
}

export function startLive(id, scenario, totalGuess) {
  stopPolling();
  state.live = {
    id,
    scenario,
    desde: 0,
    historico: [],
    baselines: [],
    progresso: {},
    status: 'executando',
    erro: null,
    total: totalGuess || 0,
    color: makeColorMap(scenario.frota),
    stopById: new Map((scenario.paradas || []).map((p) => [p.id, p])),
    stopping: false,
  };
  failures = 0;
  lastRoutesKey = '';
  resetUI();
  emit('live', state.live);
  poll();
}

function resetUI() {
  const live = state.live;
  $('#run-error').hidden = true;
  $('#live-lead').textContent = `${live.scenario.nome} · execução ${live.id}`;
  ['#kpi-melhor', '#kpi-media', '#kpi-div', '#kpi-tempo'].forEach((s) => { $(s).textContent = '—'; });
  ['#kpi-melhor-sub', '#kpi-div-sub', '#kpi-tempo-sub'].forEach((s) => { $(s).textContent = ''; });
  createLiveChart();
  drawBaseMap();
  render();
}

function createLiveChart() {
  const primary = cssVar('--primary') || '#0f766e';
  const opts = generationLineOptions();
  if (state.live.total) opts.scales.x.max = state.live.total;
  makeChart('live', $('#chart-live'), {
    type: 'line',
    data: {
      datasets: [
        { label: 'Melhor custo', data: [], borderColor: primary, backgroundColor: primary, borderWidth: 2.5, pointRadius: 0, tension: 0.25 },
        { label: 'Média da população', data: [], borderColor: '#94a3b8', backgroundColor: '#94a3b8', borderWidth: 1.5, pointRadius: 0, tension: 0.25 },
      ],
    },
    options: opts,
  });
}

function drawBaseMap() {
  const sc = state.live.scenario;
  const map = getMap('map-live');
  baseLayer?.remove();
  routesLayer?.remove();
  baseLayer = L.featureGroup().addTo(map);
  routesLayer = L.featureGroup().addTo(map);
  (sc.paradas || []).forEach((p) => stopMarker(p, sc.prioridades).addTo(baseLayer));
  if (sc.deposito) depotMarker(sc.deposito).addTo(baseLayer);
  fitTo('map-live', baseLayer.getBounds());
  $('#live-legend').innerHTML = '';
}

async function poll() {
  const live = state.live;
  if (!live) return;
  try {
    const snap = await api(`/api/execucoes/${encodeURIComponent(live.id)}/progresso?desde=${live.desde}`);
    if (state.live !== live) return;
    failures = 0;
    applySnapshot(live, snap);
  } catch (e) {
    if (state.live !== live) return;
    failures += 1;
    if (e.status === 404 || failures >= 6) {
      live.status = 'erro';
      live.erro = e.message;
      render();
      emit('live', live);
      return;
    }
  }
  if (state.live === live && live.status === 'executando') timer = setTimeout(poll, POLL_MS);
}

function applySnapshot(live, snap) {
  const prevStatus = live.status;
  live.status = snap.status || live.status;
  live.erro = snap.erro || null;
  if (Array.isArray(snap.historico) && snap.historico.length) {
    live.historico.push(...snap.historico);
    live.desde += snap.historico.length;
  }
  if (snap.progresso && Object.keys(snap.progresso).length) {
    live.progresso = snap.progresso;
    if (snap.progresso.total) live.total = snap.progresso.total;
  }
  if (Array.isArray(snap.baselines) && snap.baselines.length) live.baselines = snap.baselines;
  render();
  if (prevStatus !== live.status) emit('live', live);
  if (live.status === 'concluido' || live.status === 'interrompido') finish(live);
}

async function finish(live) {
  stopPolling();
  // o resultado pode levar um instante para ficar disponível
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      const run = await fetchRun(live.id);
      if (state.live !== live) return;
      setRun(run);
      toast(live.status === 'interrompido'
        ? 'Otimização interrompida — exibindo a melhor solução encontrada.'
        : 'Otimização concluída!', 'success');
      go('resultados');
      return;
    } catch (e) {
      if (e.status !== 404 || attempt === 4) { toastError(e); return; }
      await sleep(600);
    }
  }
}

// ---------------------------------------------------------- renderização
function render() {
  const live = state.live;
  if (!live) return;
  const p = live.progresso || {};
  const running = live.status === 'executando';

  const pill = $('#run-status');
  pill.className = `status-pill ${live.status}`;
  pill.textContent = live.stopping && running ? 'Interrompendo…' : (STATUS[live.status] || live.status);
  $('#btn-stop').disabled = !running || live.stopping;
  $('#btn-stop').hidden = !running;

  const total = p.total || live.total || 0;
  const gen = p.geracao || 0;
  const done = !running && live.status !== 'erro';
  const pct = done ? 100 : total ? Math.min(100, (gen / total) * 100) : 0;
  $('#progress-fill').style.width = `${pct}%`;
  $('#progress').setAttribute('aria-valuenow', String(Math.round(pct)));
  $('#progress').closest('.progress-card').classList.toggle('running', running);
  $('#progress-text').textContent = gen
    ? `Geração ${fmt.num(gen)} de ${fmt.num(total)}${done && gen < total ? ' (parada antecipada)' : ''}`
    : running ? 'Calculando abordagens de referência e população inicial…' : '';
  $('#progress-pct').textContent = `${fmt.num(pct, 0)}%`;

  if (live.status === 'erro') {
    $('#run-error').textContent = `A execução falhou: ${live.erro || 'erro desconhecido'}`;
    $('#run-error').hidden = false;
  }

  // KPIs
  $('#kpi-melhor').textContent = fmt.money(p.melhor);
  $('#kpi-media').textContent = fmt.money(p.media);
  $('#kpi-div').textContent = fmt.pct(p.diversidade);
  $('#kpi-div-sub').textContent = typeof p.mutacao === 'number' ? `mutação atual ${fmt.pct(p.mutacao, 0)}` : '';
  $('#kpi-tempo').textContent = fmt.secs(p.tempo_s);
  $('#kpi-tempo-sub').textContent = live.historico.length ? `${fmt.num(live.historico.length)} pontos registrados` : '';
  const best = live.baselines.reduce((m, b) => (typeof b.custo_total === 'number' && (!m || b.custo_total < m.custo_total) ? b : m), null);
  let sub = '';
  if (best && typeof p.melhor === 'number' && best.custo_total > 0) {
    const diff = (best.custo_total - p.melhor) / best.custo_total;
    sub = `${fmt.pct(Math.abs(diff))} ${diff >= 0 ? 'abaixo' : 'acima'} de ${best.nome}`;
  }
  $('#kpi-melhor-sub').textContent = sub;

  updateChart(live, total);
  updateRoutes(live);
}

function updateChart(live, total) {
  const chart = getChart('live');
  if (!chart) return;
  const ds = chart.data.datasets;
  ds[0].data = live.historico.map((h) => ({ x: h.geracao, y: h.melhor }));
  ds[1].data = live.historico.map((h) => ({ x: h.geracao, y: h.media }));
  const lastGen = live.historico.at(-1)?.geracao || 1;
  const xMax = Math.max(total || 0, lastGen, 2);
  chart.options.scales.x.max = xMax;
  // linhas de referência das abordagens clássicas
  const baseSets = live.baselines
    .filter((b) => typeof b.custo_total === 'number')
    .map((b, i) => ({
      label: b.nome,
      data: [{ x: 1, y: b.custo_total }, { x: xMax, y: b.custo_total }],
      borderColor: BASELINE_COLORS[i % BASELINE_COLORS.length],
      backgroundColor: BASELINE_COLORS[i % BASELINE_COLORS.length],
      borderDash: [6, 4],
      borderWidth: 1.5,
      pointRadius: 0,
      isBaseline: true,
    }));
  chart.data.datasets = [ds[0], ds[1], ...baseSets];
  chart.update('none');
}

function updateRoutes(live) {
  const rotas = live.progresso?.rotas;
  if (!Array.isArray(rotas)) return;
  const key = JSON.stringify(rotas);
  if (key === lastRoutesKey) return;
  lastRoutesKey = key;
  routesLayer.clearLayers();
  const dep = live.scenario.deposito;
  const legend = [];
  rotas.forEach((r) => {
    const pts = (r.paradas || []).map((id) => live.stopById.get(id)).filter(Boolean);
    if (!pts.length || !dep) return;
    const color = live.color(r.veiculo);
    const latlngs = [[dep.lat, dep.lon], ...pts.map((s) => [s.lat, s.lon]), [dep.lat, dep.lon]];
    routeLine(latlngs, color, 3.5)
      .bindTooltip(`<strong>${esc(r.veiculo)}</strong> · ${pts.length} parada(s)`, { sticky: true, className: 'rv-tooltip' })
      .addTo(routesLayer);
    legend.push(`<li><span class="lg-line" style="--c:${color}"></span>${esc(r.veiculo)} <span class="muted">(${pts.length})</span></li>`);
  });
  baseLayer.eachLayer((l) => l.bringToFront?.());
  $('#live-legend').innerHTML = legend.join('');
}

async function stopRun() {
  const live = state.live;
  if (!live || live.status !== 'executando') return;
  live.stopping = true;
  render();
  try {
    await api(`/api/execucoes/${encodeURIComponent(live.id)}/parar`, { method: 'POST' });
    toast('Pedido de parada enviado. Aguardando a geração atual terminar…');
  } catch (e) {
    live.stopping = false;
    render();
    toastError(e);
  }
}

export function initOtimizacao() {
  $('#btn-stop').addEventListener('click', stopRun);
}

export const onShowOtimizacao = () => refreshMap('map-live');
