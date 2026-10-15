// Passo 4 — resultados da execução: KPIs, comparação, mapa, cards por rota e GA.
import { state, on } from '../state.js';
import { $, $$, esc, fmt, api, toastError, downloadFile, isNum } from '../util.js';
import { makeColorMap, prioBadge, coldBadge, motivoLabel } from '../domain.js';
import { getMap, fitTo, refreshMap, depotMarker, numberedMarker, routeLine, stopTooltip } from '../maps.js';
import { makeChart, cssVar, moneyTick, BASELINE_COLORS } from '../charts.js';
import { openModalLoading, fillModal, closeModal } from '../modal.js';
import { go } from '../nav.js';

let dirty = true;
let depotLayer = null;
const vehicleLayers = new Map(); // veiculo -> featureGroup
let colorOf = () => '#0f766e';

function kpi(label, value, sub = '', cls = '') {
  return `<div class="kpi ${cls}"><span class="kpi-label">${esc(label)}</span>
    <span class="kpi-value">${value}</span><span class="kpi-sub">${sub}</span></div>`;
}

function render() {
  const run = state.run;
  if (!run) return;
  dirty = false;
  const sol = run.solucao || {};
  colorOf = makeColorMap(run.cenario?.frota);
  $('#res-subtitle').textContent = `${run.cenario?.nome || 'Cenário'} · ${fmt.date(run.criado_em)} · execução ${run.id}`;
  renderHero(run, sol);
  renderBreakdown(sol);
  renderCompare(run, sol);
  renderMap(run, sol);
  renderCards(run, sol);
  renderGA(run);
}

function renderHero(run, sol) {
  const cmp = run.comparativo;
  const savingOk = cmp && isNum(cmp.economia_rs);
  const saving = savingOk
    ? kpi(cmp.economia_rs >= 0 ? 'Economia' : 'Diferença', fmt.money(cmp.economia_rs),
      `${fmt.pctRaw(cmp.economia_pct)} vs ${esc(cmp.melhor_baseline)}`, cmp.economia_rs >= 0 ? 'kpi-good' : 'kpi-bad')
    : kpi('Economia', '—', 'sem abordagem de referência');
  const critOk = sol.criticas_total ? sol.criticas_no_prazo === sol.criticas_total : true;
  $('#res-hero').innerHTML = [
    kpi('Custo total', fmt.money(sol.custo_total),
      `operacional ${fmt.money(sol.custo_operacional)} + multas ${fmt.money((sol.multa_atraso || 0) + (sol.multa_frota || 0))}`, 'kpi-hero'),
    saving,
    kpi('Entregas no prazo', fmt.pct(sol.taxa_no_prazo), `${fmt.num(sol.entregas_no_prazo)} de ${fmt.num(sol.entregas)} entregas`),
    kpi('Críticas no prazo', `${fmt.num(sol.criticas_no_prazo)}/${fmt.num(sol.criticas_total)}`,
      critOk ? 'todas as críticas atendidas' : 'há crítica fora do prazo', critOk ? 'kpi-good' : 'kpi-bad'),
    kpi('Distância total', fmt.km(sol.distancia_km), `${fmt.dur(sol.duracao_total_min)} em rota somando veículos`),
    kpi('Veículos usados', fmt.num(sol.veiculos_usados),
      sol.veiculos_excedentes ? `${fmt.num(sol.veiculos_excedentes)} excedente(s)` : 'dentro da frota'),
    kpi('Ocupação média', fmt.pct(sol.ocupacao_media), 'carga / capacidade'),
    kpi('Emissão de CO₂', fmt.kg(sol.co2_kg), 'estimativa por km rodado'),
  ].join('');
}

function renderBreakdown(sol) {
  const items = [
    { label: 'Custo operacional', v: sol.custo_operacional || 0, c: cssVar('--primary') || '#0f766e' },
    { label: 'Multa por atraso', v: sol.multa_atraso || 0, c: '#e11d48' },
    { label: 'Multa de frota (excedentes)', v: sol.multa_frota || 0, c: '#f59e0b' },
  ];
  const total = items.reduce((s, i) => s + i.v, 0) || 1;
  $('#res-breakdown').innerHTML = `
    <div class="breakdown-bar" role="img" aria-label="Composição do custo total">
      ${items.filter((i) => i.v > 0).map((i) => `<span style="width:${(i.v / total) * 100}%;background:${i.c}" title="${esc(i.label)}: ${fmt.money(i.v)}"></span>`).join('')}
    </div>
    <ul class="breakdown-list">
      ${items.map((i) => `<li><span class="sw" style="--c:${i.c}"></span><span>${esc(i.label)}</span>
        <span class="val">${fmt.money(i.v)}</span><span class="pct">${fmt.pct(i.v / total)}</span></li>`).join('')}
    </ul>
    <div class="breakdown-total"><span>Custo total</span><span>${fmt.money(sol.custo_total)}</span></div>`;
}

function renderCompare(run, sol) {
  const primary = cssVar('--primary') || '#0f766e';
  const items = [
    { nome: 'Algoritmo genético', custo: sol.custo_total, ga: true },
    ...(run.baselines || []).map((b) => ({ nome: b.nome, custo: b.custo_total })),
  ].filter((i) => isNum(i.custo)).sort((a, b) => a.custo - b.custo);
  $('#chart-compare-box').style.height = `${Math.max(200, 70 + items.length * 46)}px`;
  let bi = 0;
  const colors = items.map((i) => (i.ga ? primary : BASELINE_COLORS[bi++ % BASELINE_COLORS.length]));
  makeChart('compare', $('#chart-compare'), {
    type: 'bar',
    data: {
      labels: items.map((i) => i.nome),
      datasets: [{ label: 'Custo total', data: items.map((i) => i.custo), backgroundColor: colors, borderRadius: 6, maxBarThickness: 30 }],
    },
    options: {
      indexAxis: 'y',
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => ` ${fmt.money(ctx.parsed.x)}` } },
      },
      scales: {
        x: { beginAtZero: true, ticks: { callback: moneyTick } },
        y: { grid: { display: false }, ticks: { font: (ctx) => ({ weight: items[ctx.index]?.ga ? '700' : '400' }) } },
      },
    },
  });
}

// ------------------------------------------------------------------ mapa
function renderMap(run, sol) {
  const map = getMap('map-result');
  depotLayer?.remove();
  vehicleLayers.forEach((l) => l.remove());
  vehicleLayers.clear();
  const dep = run.cenario?.deposito;
  const rules = run.cenario?.prioridades;
  const all = L.featureGroup();
  (sol.rotas || []).forEach((r) => {
    const stops = (r.paradas || []).filter((p) => isNum(p.lat) && isNum(p.lon));
    if (!stops.length) return;
    const color = colorOf(r.veiculo);
    const group = L.featureGroup();
    const pts = stops.map((p) => [p.lat, p.lon]);
    const latlngs = dep ? [[dep.lat, dep.lon], ...pts, [dep.lat, dep.lon]] : pts;
    routeLine(latlngs, color, 4).bindTooltip(`<strong>${esc(r.veiculo)}</strong> · ${fmt.km(r.distancia_km)}`, { sticky: true, className: 'rv-tooltip' }).addTo(group);
    stops.forEach((p) => {
      const late = (p.atraso_min || 0) > 0;
      const extra = `<dt>Veículo</dt><dd>${esc(r.veiculo)} · ${esc(p.ordem)}ª parada</dd>
        <dt>Chegada</dt><dd>${esc(p.chegada || '—')}</dd>
        <dt>Atraso</dt><dd class="${late ? 'late' : ''}">${fmt.min(p.atraso_min)}</dd>`;
      numberedMarker(p, p.ordem, color, stopTooltip(p, rules, extra)).addTo(group);
    });
    group.addTo(map);
    vehicleLayers.set(r.veiculo, group);
    all.addLayer(L.polyline(latlngs));
  });
  if (dep) {
    depotLayer = depotMarker(dep).addTo(map);
    all.addLayer(L.marker([dep.lat, dep.lon]));
  }
  fitTo('map-result', all.getBounds());

  $('#route-legend').innerHTML = (sol.rotas || []).filter((r) => vehicleLayers.has(r.veiculo)).map((r) => {
    const c = colorOf(r.veiculo);
    return `<label class="legend-item" style="--c:${c}">
        <input type="checkbox" checked data-veiculo="${esc(r.veiculo)}">
        <span class="lg-line"></span>
        <span>${esc(r.veiculo)}<small>${fmt.num(r.paradas?.length)} paradas · ${fmt.km(r.distancia_km)}</small></span>
      </label>`;
  }).join('');
}

function setVehicleVisible(veiculo, visible) {
  const layer = vehicleLayers.get(veiculo);
  const map = getMap('map-result');
  if (!layer) return;
  if (visible) layer.addTo(map);
  else layer.remove();
}

function focusVehicle(veiculo) {
  vehicleLayers.forEach((_, v) => setVehicleVisible(v, v === veiculo));
  $$('#route-legend input').forEach((i) => { i.checked = i.dataset.veiculo === veiculo; });
  const layer = vehicleLayers.get(veiculo);
  $('#map-result').scrollIntoView({ behavior: 'smooth', block: 'center' });
  if (layer) getMap('map-result').fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 14 });
}

// ----------------------------------------------------------------- cards
function meter(label, value, frac) {
  const p = isNum(frac) ? Math.max(0, Math.min(100, frac * 100)) : 0;
  const tone = frac > 1 ? 'bad' : frac > 0.9 ? 'warn' : '';
  return `<div class="meter-row"><div class="meter-top"><span>${label}</span><strong>${value}</strong></div>
    <div class="meter" role="img" aria-label="${esc(label)}: ${fmt.pct(frac)}"><span class="${tone}" style="width:${p}%"></span></div></div>`;
}

function timelineItem(p, rules) {
  const late = (p.atraso_min || 0) > 0;
  return `<li class="tl-item${late ? ' late' : ''}">
      <span class="tl-dot">${esc(p.ordem)}</span>
      <div>
        <div class="tl-title"><strong>${esc(p.nome)}</strong> ${prioBadge(p.prioridade, rules)}${p.refrigerado ? ' <span title="Refrigerado" aria-label="Refrigerado">❄</span>' : ''}</div>
        <div class="tl-time"><strong>${esc(p.chegada || '—')} → ${esc(p.saida || '—')}</strong> · janela ${esc(p.janela || '—')} · prazo ${esc(p.prazo || '—')}</div>
        <div class="tl-meta">
          <span>espera <b>${fmt.min(p.espera_min)}</b></span>
          <span class="${late ? 'late' : ''}">atraso <b>${fmt.min(p.atraso_min)}</b></span>
          <span>folga <b>${isNum(p.folga_min) ? fmt.min(p.folga_min) : '—'}</b></span>
          <span>entrega <b>${fmt.kg(p.demanda_kg)}</b></span>
          <span>restante <b>${fmt.kg(p.carga_restante_kg)}</b></span>
        </div>
      </div>
    </li>`;
}

function renderCards(run, sol) {
  const rules = run.cenario?.prioridades;
  const depName = esc(run.cenario?.deposito?.nome || 'Depósito');
  const rotas = sol.rotas || [];
  if (!rotas.length) {
    $('#route-cards').innerHTML = '<p class="placeholder">Nenhuma rota nesta solução.</p>';
    return;
  }
  $('#route-cards').innerHTML = rotas.map((r) => {
    const c = colorOf(r.veiculo);
    const nAtr = r.paradas_atrasadas || 0;
    return `<article class="card route-card" style="--vc:${c}">
      <header class="route-head">
        <span class="vdot" aria-hidden="true"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M3 7h11v8H3zM14 10h4l3 3v2h-7zM7 18a1.6 1.6 0 1 0 0-.1M17 18a1.6 1.6 0 1 0 0-.1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg></span>
        <div>
          <h3>${esc(r.veiculo)}</h3>
          <p class="muted small">${esc(r.tipo_nome || r.tipo || '')}</p>
          <div class="badges">
            ${r.refrigerado ? coldBadge() : ''}
            ${r.excedente ? '<span class="badge b-warn" title="Veículo além da frota disponível — gera multa">⚠ Excedente</span>' : ''}
            ${nAtr ? `<span class="badge b-bad">${nAtr} parada(s) atrasada(s)</span>` : '<span class="badge b-ok">Tudo no prazo</span>'}
          </div>
        </div>
      </header>
      <dl class="route-stats">
        <div><dt>Saída → retorno</dt><dd>${esc(r.saida_deposito || '—')} → ${esc(r.retorno_deposito || '—')}</dd></div>
        <div><dt>Distância</dt><dd>${fmt.km(r.distancia_km)}</dd></div>
        <div><dt>Duração</dt><dd>${fmt.dur(r.duracao_min)}</dd></div>
        <div><dt>Paradas</dt><dd>${fmt.num(r.paradas?.length)}</dd></div>
        <div><dt>Custo operacional</dt><dd>${fmt.money(r.custo_operacional)}</dd></div>
        <div><dt>Multa por atraso</dt><dd>${fmt.money(r.multa_atraso)}</dd></div>
      </dl>
      <div class="route-body">
        ${meter('Carga', `${fmt.kg(r.carga_kg)} / ${fmt.kg(r.capacidade_kg)}`, r.ocupacao ?? (r.capacidade_kg ? r.carga_kg / r.capacidade_kg : null))}
        ${meter('Uso da autonomia', fmt.pct(r.uso_autonomia), r.uso_autonomia)}
        <ol class="timeline">
          <li class="tl-item depot"><span class="tl-dot" aria-hidden="true">▶</span><div><div class="tl-title"><strong>${depName}</strong></div><div class="tl-time">Saída <strong>${esc(r.saida_deposito || '—')}</strong> · carga ${fmt.kg(r.carga_kg)}</div></div></li>
          ${(r.paradas || []).map((p) => timelineItem(p, rules)).join('')}
          <li class="tl-item depot"><span class="tl-dot" aria-hidden="true">■</span><div><div class="tl-title"><strong>${depName}</strong></div><div class="tl-time">Retorno <strong>${esc(r.retorno_deposito || '—')}</strong></div></div></li>
        </ol>
      </div>
      <footer class="route-foot">
        <button type="button" class="btn btn-primary btn-sm" data-instr="${esc(r.veiculo)}">Instruções do motorista (IA)</button>
        <button type="button" class="btn btn-ghost btn-sm" data-focus="${esc(r.veiculo)}">Ver no mapa</button>
      </footer>
    </article>`;
  }).join('');
}

async function openInstructions(veiculo) {
  const run = state.run;
  if (!run) return;
  openModalLoading('Instruções do motorista', veiculo);
  try {
    const r = await api(`/api/execucoes/${encodeURIComponent(run.id)}/instrucoes`, { method: 'POST', json: { veiculo } });
    fillModal(r || {});
  } catch (e) {
    closeModal();
    toastError(e);
  }
}

// -------------------------------------------------------------------- GA
function renderGA(run) {
  const ga = run.ga || {};
  const cfg = ga.config || {};
  const rows = [
    ['Gerações', fmt.num(ga.geracoes)],
    ['Motivo de parada', esc(motivoLabel(ga.motivo_parada))],
    ['Tempo', fmt.secs(ga.tempo_s)],
    ['Avaliações', fmt.num(ga.avaliacoes)],
    ['População', fmt.num(cfg.population_size)],
    ['Cruzamento', esc(String(cfg.crossover || '—').toUpperCase())],
    ['Mutação', fmt.pct(cfg.mutation_rate, 0)],
    ['Elitismo', fmt.num(cfg.elitism)],
  ];
  $('#ga-info').innerHTML = rows.map(([t, d]) => `<div><dt>${t}</dt><dd>${d}</dd></div>`).join('');

  const hist = ga.historico || [];
  const primary = cssVar('--primary') || '#0f766e';
  makeChart('convergence', $('#chart-convergence'), {
    type: 'line',
    data: {
      datasets: [
        { label: 'Melhor custo', data: hist.map((h) => ({ x: h.geracao, y: h.melhor })), borderColor: primary, backgroundColor: primary, borderWidth: 2.5, pointRadius: 0, tension: 0.2, yAxisID: 'y' },
        { label: 'Média da população', data: hist.map((h) => ({ x: h.geracao, y: h.media })), borderColor: '#94a3b8', backgroundColor: '#94a3b8', borderWidth: 1.5, pointRadius: 0, tension: 0.2, yAxisID: 'y' },
        { label: 'Diversidade', data: hist.map((h) => ({ x: h.geracao, y: isNum(h.diversidade) ? h.diversidade * 100 : null })), borderColor: '#f59e0b', backgroundColor: '#f59e0b', borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0, tension: 0.2, yAxisID: 'y1' },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: {
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: {
            title: (items) => (items.length ? `Geração ${items[0].parsed.x}` : ''),
            label: (ctx) => (ctx.dataset.yAxisID === 'y1'
              ? `${ctx.dataset.label}: ${fmt.pctRaw(ctx.parsed.y)}`
              : `${ctx.dataset.label}: ${fmt.money(ctx.parsed.y)}`),
          },
        },
      },
      scales: {
        x: { type: 'linear', min: 1, title: { display: true, text: 'Geração' }, grid: { display: false }, ticks: { precision: 0 } },
        y: { position: 'left', ticks: { callback: moneyTick }, title: { display: true, text: 'Custo' } },
        y1: { position: 'right', min: 0, max: 100, grid: { drawOnChartArea: false }, ticks: { callback: (v) => `${v}%` }, title: { display: true, text: 'Diversidade' } },
      },
    },
  });
}

export function initResultados() {
  on('run', () => {
    dirty = true;
    if (state.view === 'resultados') render();
  });
  $('#route-legend').addEventListener('change', (e) => {
    const i = e.target.closest('input[data-veiculo]');
    if (i) setVehicleVisible(i.dataset.veiculo, i.checked);
  });
  $('#btn-routes-all').addEventListener('click', () => {
    $$('#route-legend input').forEach((i) => { i.checked = true; setVehicleVisible(i.dataset.veiculo, true); });
    refreshMap('map-result');
  });
  $('#btn-routes-none').addEventListener('click', () => {
    $$('#route-legend input').forEach((i) => { i.checked = false; setVehicleVisible(i.dataset.veiculo, false); });
  });
  $('#route-cards').addEventListener('click', (e) => {
    const instr = e.target.closest('[data-instr]');
    if (instr) { openInstructions(instr.dataset.instr); return; }
    const foc = e.target.closest('[data-focus]');
    if (foc) focusVehicle(foc.dataset.focus);
  });
  $('#btn-download').addEventListener('click', () => {
    if (state.run) downloadFile(`rotavital-${state.run.id}.json`, JSON.stringify(state.run, null, 2));
  });
  $('#btn-go-chat').addEventListener('click', () => go('assistente', { focus: true }));
}

export function onShowResultados() {
  if (dirty) render();
  refreshMap('map-result');
}
