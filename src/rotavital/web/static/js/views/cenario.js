// Passo 1 — escolha do cenário, mapa das paradas, tabela e importação de CSV.
import { state, emit, KEYS } from '../state.js';
import { $, esc, fmt, api, toast, toastError, storage, setBusy, downloadFile } from '../util.js';
import { PRIO, prioBadge, coldBadge, tipoLabel, janelaDe } from '../domain.js';
import { getMap, fitTo, refreshMap, depotMarker, stopMarker } from '../maps.js';
import { go } from '../nav.js';

let stopsLayer = null;
const sort = { key: 'id', dir: 1 };

const ICON_ROUTE = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="6" cy="18" r="2.5" fill="currentColor"/><circle cx="18" cy="6" r="2.5" fill="currentColor"/><path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
const ICON_UPLOAD = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M12 16V4m0 0l-4 4m4-4l4 4M5 20h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

export async function loadScenarioList() {
  try {
    state.cenarios = (await api('/api/cenarios')) || [];
  } catch (e) {
    toastError(e);
    state.cenarios = [];
  }
  renderList();
  renderImportBase();
}

function renderList() {
  const box = $('#scenario-list');
  if (!state.cenarios.length) {
    box.innerHTML = '<p class="placeholder">Nenhum cenário encontrado no servidor.</p>';
    return;
  }
  const sel = state.scenario?.id;
  box.innerHTML = state.cenarios.map((c) => {
    const imported = String(c.id).startsWith('importado-');
    return `<button type="button" class="scenario-card" data-id="${esc(c.id)}" aria-pressed="${sel === c.id}">
        <span class="sc-top">
          <span class="sc-icon">${imported ? ICON_UPLOAD : ICON_ROUTE}</span>
          ${sel === c.id ? '<span class="sc-check">✓ Selecionado</span>' : imported ? '<span class="badge b-soft">Importado</span>' : ''}
        </span>
        <span class="sc-name">${esc(c.nome)}</span>
        <span class="sc-desc">${esc(c.descricao)}</span>
        <span class="sc-stats">
          <span><strong>${fmt.num(c.paradas)}</strong> paradas</span>
          <span><strong>${fmt.num(c.veiculos)}</strong> veículos</span>
        </span>
      </button>`;
  }).join('');
}

function renderImportBase() {
  const sel = $('#import-base');
  const current = sel.value || state.scenario?.id;
  sel.innerHTML = state.cenarios
    .map((c) => `<option value="${esc(c.id)}">${esc(c.nome)}</option>`).join('');
  if (current && state.cenarios.some((c) => c.id === current)) sel.value = current;
}

export async function selectScenario(id, { quiet = false } = {}) {
  try {
    const sc = await api(`/api/cenarios/${encodeURIComponent(id)}`);
    setScenario(sc);
    return true;
  } catch (e) {
    if (!quiet) toastError(e);
    if (e.status === 404) storage.set(KEYS.cenario, null);
    return false;
  }
}

export function setScenario(sc) {
  state.scenario = sc;
  state.fleetEdits = {};
  storage.set(KEYS.cenario, sc.id);
  renderList();
  renderDetail();
  emit('scenario', sc);
}

function renderDetail() {
  const sc = state.scenario;
  $('#scenario-detail').hidden = !sc;
  if (!sc) return;
  $('#scenario-title').textContent = sc.nome;
  $('#scenario-desc').textContent = sc.descricao || '';
  renderChips(sc);
  drawMap(sc);
  renderStops();
}

function renderChips(sc) {
  const paradas = sc.paradas || [];
  const rules = sc.prioridades || {};
  const keys = Object.keys(rules).length ? Object.keys(rules) : Object.keys(PRIO);
  keys.sort((a, b) => (rules[a]?.ordem ?? 9) - (rules[b]?.ordem ?? 9));
  const totalKg = paradas.reduce((s, p) => s + (p.demanda_kg || 0), 0);
  const cold = paradas.filter((p) => p.refrigerado);
  const coldKg = cold.reduce((s, p) => s + (p.demanda_kg || 0), 0);
  const veic = (sc.frota || []).reduce((s, v) => s + (v.quantidade || 0), 0);

  const prioChips = keys.map((k) => {
    const n = paradas.filter((p) => p.prioridade === k).length;
    const color = PRIO[k]?.color || PRIO.rotina.color;
    return `<span class="chip"><span class="lg-dot" style="--c:${color}"></span>${esc(rules[k]?.rotulo || PRIO[k]?.label || k)} <strong>${fmt.num(n)}</strong></span>`;
  }).join('');

  $('#scenario-chips').innerHTML = `
    <span class="chip">Paradas <strong>${fmt.num(paradas.length)}</strong></span>
    ${prioChips}
    <span class="chip">Carga total <strong>${fmt.kg(totalKg)}</strong></span>
    <span class="chip">❄ Refrigerada <strong>${fmt.kg(coldKg)}</strong> <span class="muted">(${fmt.num(cold.length)} paradas)</span></span>
    <span class="chip">Veículos <strong>${fmt.num(veic)}</strong></span>
    ${sc.inicio_turno ? `<span class="chip">Início do turno <strong>${esc(sc.inicio_turno)}</strong></span>` : ''}`;
}

function drawMap(sc) {
  const map = getMap('map-cenario');
  stopsLayer?.remove();
  stopsLayer = L.featureGroup().addTo(map);
  if (sc.deposito) depotMarker(sc.deposito).addTo(stopsLayer);
  (sc.paradas || []).forEach((p) => stopMarker(p, sc.prioridades).addTo(stopsLayer));
  fitTo('map-cenario', stopsLayer.getBounds());
}

function sortValue(p, rules) {
  switch (sort.key) {
    case 'prioridade': return rules?.[p.prioridade]?.ordem ?? 9;
    case 'janela': return p.janela_inicio || '';
    case 'refrigerado': return p.refrigerado ? 1 : 0;
    default: return p[sort.key];
  }
}

function renderStops() {
  const sc = state.scenario;
  if (!sc) return;
  const q = $('#stop-search').value.trim().toLowerCase();
  const fp = $('#stop-filter-prio').value;
  const fr = $('#stop-filter-ref').value;
  const all = sc.paradas || [];
  const rows = all.filter((p) => (!q || [p.id, p.nome, p.tipo, tipoLabel(p.tipo), p.carga]
    .some((v) => String(v ?? '').toLowerCase().includes(q)))
    && (!fp || p.prioridade === fp)
    && (!fr || String(!!p.refrigerado) === fr));

  rows.sort((a, b) => {
    const x = sortValue(a, sc.prioridades);
    const y = sortValue(b, sc.prioridades);
    const cmp = typeof x === 'number' && typeof y === 'number'
      ? x - y
      : String(x ?? '').localeCompare(String(y ?? ''), 'pt-BR', { numeric: true });
    return cmp * sort.dir;
  });

  $('#stops-tbody').innerHTML = rows.length ? rows.map((p) => `
    <tr>
      <td><code>${esc(p.id)}</code></td>
      <td class="wrap"><strong>${esc(p.nome)}</strong></td>
      <td>${esc(tipoLabel(p.tipo))}</td>
      <td>${esc(p.carga || '—')}</td>
      <td class="num">${fmt.kg(p.demanda_kg)}</td>
      <td>${prioBadge(p.prioridade, sc.prioridades)}</td>
      <td class="tnum">${esc(janelaDe(p))}</td>
      <td class="num">${fmt.min(p.tempo_servico_min)}</td>
      <td>${p.refrigerado ? coldBadge(true) : '<span class="muted">—</span>'}</td>
    </tr>`).join('')
    : '<tr><td colspan="9" class="empty">Nenhuma parada corresponde aos filtros.</td></tr>';

  document.querySelectorAll('#stops-table th').forEach((th) => {
    const key = th.querySelector('.th-sort')?.dataset.sort;
    if (key === sort.key) th.setAttribute('aria-sort', sort.dir === 1 ? 'ascending' : 'descending');
    else th.removeAttribute('aria-sort');
  });
  $('#stops-count').textContent = `${rows.length} de ${all.length} paradas`;
}

// ----------------------------------------------------------- importação
const CSV_TEMPLATE = [
  'id,nome,tipo,lat,lon,demanda_kg,prioridade,refrigerado,janela_inicio,janela_fim,tempo_servico_min,carga',
  'P01,Hospital Exemplo,hospital,-23.5600,-46.6500,12.5,critica,true,07:00,10:00,12,Hemocomponentes',
  'P02,UBS Exemplo,ubs,-23.5900,-46.6300,8.0,rotina,false,08:00,17:00,10,Insumos',
].join('\n');

async function onImport(e) {
  e.preventDefault();
  const file = $('#import-file').files[0];
  const nome = $('#import-name').value.trim();
  const base = $('#import-base').value;
  const errBox = $('#import-error');
  errBox.hidden = true;
  if (!file || !nome || !base) {
    errBox.textContent = 'Escolha o arquivo CSV, informe um nome e o cenário base.';
    errBox.hidden = false;
    return;
  }
  const form = new FormData();
  form.append('arquivo', file);
  form.append('nome', nome);
  form.append('base_id', base);
  const btn = $('#btn-import');
  setBusy(btn, true);
  try {
    const r = await api('/api/cenarios/importar', { method: 'POST', form });
    toast(`Cenário “${r.nome}” importado com ${r.paradas} paradas.`, 'success');
    $('#import-form').reset();
    $('#import-panel').open = false;
    await loadScenarioList();
    await selectScenario(r.id);
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
    toastError(err);
  } finally {
    setBusy(btn, false);
  }
}

export function initCenario() {
  $('#scenario-list').addEventListener('click', (e) => {
    const card = e.target.closest('.scenario-card');
    if (card && card.dataset.id !== state.scenario?.id) selectScenario(card.dataset.id);
  });
  $('#btn-go-frota').addEventListener('click', () => go('frota', { focus: true }));
  ['#stop-search', '#stop-filter-prio', '#stop-filter-ref'].forEach((s) => $(s).addEventListener('input', renderStops));
  $('#stops-table thead').addEventListener('click', (e) => {
    const b = e.target.closest('.th-sort');
    if (!b) return;
    if (sort.key === b.dataset.sort) sort.dir *= -1;
    else { sort.key = b.dataset.sort; sort.dir = 1; }
    renderStops();
  });
  $('#import-form').addEventListener('submit', onImport);
  $('#btn-csv-template').addEventListener('click', () => downloadFile('modelo-paradas.csv', CSV_TEMPLATE, 'text/csv;charset=utf-8'));
}

export const onShowCenario = () => refreshMap('map-cenario');
