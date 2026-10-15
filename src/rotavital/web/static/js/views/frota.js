// Passo 2 — frota editável, regras de prioridade e parâmetros do algoritmo genético.
import { state, on } from '../state.js';
import { $, $$, esc, fmt, api, toast, toastError, setBusy } from '../util.js';
import { prioBadge, coldBadge } from '../domain.js';
import { startLive } from './otimizacao.js';
import { go } from '../nav.js';

const FLEET_FIELDS = [
  { k: 'quantidade', label: 'Quantidade', min: 0, max: 50, step: 1, int: true },
  { k: 'capacidade_kg', label: 'Capacidade (kg)', min: 0.1, step: 'any' },
  { k: 'autonomia_km', label: 'Autonomia (km)', min: 0.1, step: 'any' },
  { k: 'custo_fixo', label: 'Custo fixo (R$)', min: 0, step: 'any' },
  { k: 'custo_km', label: 'Custo por km (R$)', min: 0, step: 'any' },
  { k: 'jornada_max_min', label: 'Jornada máxima (min)', min: 1, step: 1, int: true },
];

const PRESET_INFO = {
  rapido: {
    nome: 'Rápido',
    desc: 'Resposta em segundos — ideal para testar cenários e demonstrações.',
    icon: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M13 2L4 14h7l-1 8 9-12h-7z" fill="currentColor"/></svg>',
  },
  equilibrado: {
    nome: 'Equilibrado',
    desc: 'Bom compromisso entre qualidade da rota e tempo de execução.',
    icon: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M12 3v18M5 7h14M5 7l-3 7a3.5 3.5 0 0 0 6 0zM19 7l-3 7a3.5 3.5 0 0 0 6 0z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
  },
  qualidade: {
    nome: 'Qualidade',
    desc: 'População maior e busca mais longa para extrair o menor custo.',
    icon: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/></svg>',
  },
};

const CROSSOVERS = {
  ox: 'OX — Order Crossover: copia um trecho de um pai e completa com a ordem relativa das paradas do outro.',
  pmx: 'PMX — Partially Mapped: troca um segmento entre os pais e corrige repetições por mapeamento.',
  erx: 'ERX — Edge Recombination: herda as ligações (arestas) entre paradas presentes nos pais.',
};

const CFG_FIELDS = [
  { k: 'population_size', label: 'Tamanho da população', min: 10, max: 1000, step: 1, help: 'Indivíduos avaliados por geração.' },
  { k: 'generations', label: 'Gerações (máximo)', min: 1, max: 5000, step: 1, help: 'Limite de iterações do algoritmo.' },
  { k: 'crossover', label: 'Cruzamento', type: 'select' },
  { k: 'mutation_rate', label: 'Taxa de mutação', min: 0, max: 1, step: 0.01, float: true, help: 'Probabilidade de mutar cada filho (0 a 1).' },
  { k: 'tournament_k', label: 'Torneio (k)', min: 2, max: 10, step: 1, help: 'Competidores por seleção; maior = mais pressão seletiva.' },
  { k: 'elitism', label: 'Elitismo', min: 0, max: 20, step: 1, help: 'Melhores indivíduos copiados sem alteração.' },
  { k: 'local_search_every', label: 'Busca local a cada', min: 0, max: 100, step: 1, help: 'Gerações entre buscas locais (0 desliga).' },
  { k: 'stagnation_limit', label: 'Limite de estagnação', min: 5, max: 5000, step: 1, help: 'Para após N gerações sem melhora.' },
  { k: 'time_limit_s', label: 'Tempo limite (s)', min: 1, max: 1800, step: 1, float: true, help: 'Interrompe a busca ao atingir o tempo.' },
  { k: 'seed', label: 'Semente aleatória', step: 1, optional: true, help: 'Vazio = aleatória. Fixe para reproduzir resultados.' },
];

// ------------------------------------------------------------- frota
function renderFleet() {
  const sc = state.scenario;
  const body = $('#fleet-tbody');
  if (!sc) { body.innerHTML = ''; return; }
  body.innerHTML = (sc.frota || []).map((v) => {
    const edits = state.fleetEdits[v.codigo] || {};
    const cells = FLEET_FIELDS.map((f) => {
      const val = edits[f.k] ?? v[f.k];
      const changed = f.k in edits;
      return `<td class="num${changed ? ' changed' : ''}">
          <input type="number" inputmode="decimal" data-codigo="${esc(v.codigo)}" data-field="${f.k}"
            value="${esc(val ?? '')}" min="${f.min}"${f.max != null ? ` max="${f.max}"` : ''} step="${f.step}"
            aria-label="${esc(f.label)} — ${esc(v.nome || v.codigo)}" required>
        </td>`;
    }).join('');
    return `<tr>
        <td><div class="veh-cell"><strong>${esc(v.nome || v.codigo)} ${v.refrigerado ? coldBadge(true) : ''}</strong>
          <span class="muted"><code>${esc(v.codigo)}</code>${v.velocidade_kmh ? ` · ${fmt.num(v.velocidade_kmh)} km/h` : ''}</span></div></td>
        ${cells}
      </tr>`;
  }).join('');
}

function onFleetInput(e) {
  const input = e.target.closest('input[data-field]');
  if (!input) return;
  const { codigo, field } = input.dataset;
  const spec = FLEET_FIELDS.find((f) => f.k === field);
  const original = state.scenario.frota.find((v) => v.codigo === codigo)?.[field];
  const edits = (state.fleetEdits[codigo] ??= {});
  const raw = input.value.trim();
  const val = spec.int ? parseInt(raw, 10) : parseFloat(raw);
  const valid = raw !== '' && input.checkValidity() && Number.isFinite(val);
  input.classList.toggle('invalid', !valid);
  if (!valid || val === original) delete edits[field];
  else edits[field] = val;
  if (!Object.keys(edits).length) delete state.fleetEdits[codigo];
  input.closest('td').classList.toggle('changed', field in (state.fleetEdits[codigo] || {}));
  updateSummary();
}

function renderRules() {
  const sc = state.scenario;
  if (!sc) return;
  const rules = Object.entries(sc.prioridades || {}).sort((a, b) => (a[1].ordem ?? 9) - (b[1].ordem ?? 9));
  $('#rules-tbody').innerHTML = rules.map(([k, r]) => `
    <tr>
      <td>${prioBadge(k, sc.prioridades)}</td>
      <td class="num">${r.sla_min != null ? fmt.dur(r.sla_min) : '<span class="muted">Sem SLA</span>'}</td>
      <td class="num">${fmt.money(r.multa_min)}/min</td>
    </tr>`).join('');
  const extras = [
    ['Início do turno', sc.inicio_turno ? esc(sc.inicio_turno) : '—'],
    ['Depósito', esc(sc.deposito?.nome || '—')],
    ['Multa por veículo excedente', fmt.money(sc.multa_veiculo_excedente)],
    ['Fator de sinuosidade', sc.fator_sinuosidade != null ? `${fmt.num(sc.fator_sinuosidade, 2)}×` : '—'],
  ];
  $('#rules-extra').innerHTML = extras.map(([t, d]) => `<div><dt>${t}</dt><dd>${d}</dd></div>`).join('');
}

// ----------------------------------------------------------- presets
export async function loadPresets() {
  try {
    state.presets = (await api('/api/presets')) || {};
  } catch (e) {
    toastError(e);
    state.presets = {};
  }
  if (!state.presets[state.preset]) state.preset = Object.keys(state.presets)[0] || 'equilibrado';
  renderPresets();
  renderAdvanced();
  fillAdvanced();
}

function renderPresets() {
  const order = ['rapido', 'equilibrado', 'qualidade', ...Object.keys(state.presets).filter((k) => !PRESET_INFO[k])];
  $('#preset-list').innerHTML = order.filter((k) => state.presets[k]).map((k) => {
    const cfg = state.presets[k];
    const info = PRESET_INFO[k] || { nome: k, desc: '', icon: '' };
    return `<button type="button" class="preset" role="radio" aria-checked="${state.preset === k}" data-preset="${esc(k)}">
        <span class="preset-icon">${info.icon}</span>
        <span class="preset-name">${esc(info.nome)}</span>
        <span class="preset-desc">${esc(info.desc)}</span>
        <span class="preset-specs">
          <span class="badge b-soft">${fmt.num(cfg.population_size)} indivíduos</span>
          <span class="badge b-soft">até ${fmt.num(cfg.generations)} gerações</span>
          <span class="badge b-soft">${esc(String(cfg.crossover || '').toUpperCase())}</span>
          <span class="badge b-soft">≤ ${fmt.num(cfg.time_limit_s)} s</span>
        </span>
      </button>`;
  }).join('');
}

function renderAdvanced() {
  $('#advanced-grid').innerHTML = CFG_FIELDS.map((f) => {
    const id = `cfg-${f.k}`;
    if (f.type === 'select') {
      return `<div class="field field-wide" data-cfg-field="${f.k}">
          <label for="${id}">${f.label}</label>
          <select id="${id}" data-cfg="${f.k}">
            ${Object.keys(CROSSOVERS).map((c) => `<option value="${c}">${c.toUpperCase()}</option>`).join('')}
          </select>
          <span class="help" id="crossover-help"></span>
        </div>`;
    }
    return `<div class="field" data-cfg-field="${f.k}">
        <label for="${id}">${f.label}</label>
        <input id="${id}" type="number" data-cfg="${f.k}" step="${f.step}"
          ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''}
          ${f.optional ? 'placeholder="aleatória"' : 'required'} aria-describedby="${id}-help">
        <span class="help" id="${id}-help">${esc(f.help || '')}</span>
      </div>`;
  }).join('');
}

/** Preenche os campos avançados com os valores do preset + ajustes do usuário. */
function fillAdvanced() {
  const base = state.presets[state.preset] || {};
  CFG_FIELDS.forEach((f) => {
    const el = $(`[data-cfg="${f.k}"]`);
    if (!el) return;
    const v = f.k in state.configOverrides ? state.configOverrides[f.k] : base[f.k];
    el.value = v ?? '';
    el.classList.remove('invalid');
    el.closest('.field').classList.toggle('changed', f.k in state.configOverrides);
  });
  $('#crossover-help').textContent = CROSSOVERS[$('[data-cfg="crossover"]').value] || '';
  updateSummary();
}

function onAdvancedInput(e) {
  const el = e.target.closest('[data-cfg]');
  if (!el) return;
  const f = CFG_FIELDS.find((x) => x.k === el.dataset.cfg);
  const base = state.presets[state.preset] || {};
  let val;
  let valid = true;
  if (f.type === 'select') {
    val = el.value;
    $('#crossover-help').textContent = CROSSOVERS[val] || '';
  } else {
    const raw = el.value.trim();
    if (raw === '' && f.optional) val = null;
    else {
      val = f.float ? parseFloat(raw) : parseInt(raw, 10);
      valid = raw !== '' && el.checkValidity() && Number.isFinite(val);
    }
  }
  el.classList.toggle('invalid', !valid);
  if (!valid || val === (base[f.k] ?? null)) delete state.configOverrides[f.k];
  else state.configOverrides[f.k] = val;
  el.closest('.field').classList.toggle('changed', f.k in state.configOverrides);
  updateSummary();
}

function updateSummary() {
  const nCfg = Object.keys(state.configOverrides).length;
  const nVeh = Object.keys(state.fleetEdits).length;
  $('#advanced-count').textContent = nCfg ? `· ${nCfg} ajuste(s)` : '';
  const preset = PRESET_INFO[state.preset]?.nome || state.preset;
  const parts = [`Perfil <strong>${esc(preset)}</strong>`];
  if (nCfg) parts.push(`${nCfg} parâmetro(s) ajustado(s)`);
  if (nVeh) parts.push(`${nVeh} tipo(s) de veículo alterado(s)`);
  if (state.scenario) parts.unshift(`<strong>${esc(state.scenario.nome)}</strong>`);
  $('#run-summary').innerHTML = parts.join(' · ');
}

// -------------------------------------------------------------- run
/** Cenário com as edições de frota aplicadas (para cores e mapa ao vivo). */
function effectiveScenario() {
  const sc = state.scenario;
  return {
    ...sc,
    frota: (sc.frota || []).map((v) => ({ ...v, ...(state.fleetEdits[v.codigo] || {}) })),
  };
}

async function startRun() {
  if (!state.scenario) return;
  const invalid = $$('#view-frota input.invalid, #view-frota input:invalid');
  if (invalid.length) {
    toast('Corrija os campos destacados antes de otimizar.', 'error');
    invalid[0].focus();
    return;
  }
  const body = {
    cenario_id: state.scenario.id,
    preset: state.preset,
    config: { ...state.configOverrides },
    frota: Object.entries(state.fleetEdits)
      .filter(([, f]) => Object.keys(f).length)
      .map(([codigo, f]) => ({ codigo, ...f })),
  };
  const btn = $('#btn-run');
  setBusy(btn, true);
  try {
    const { id } = await api('/api/execucoes', { method: 'POST', json: body });
    const total = body.config.generations ?? state.presets[state.preset]?.generations;
    startLive(id, effectiveScenario(), total);
    go('otimizacao');
  } catch (e) {
    toastError(e);
  } finally {
    setBusy(btn, false);
  }
}

export function initFrota() {
  $('#fleet-tbody').addEventListener('input', onFleetInput);
  $('#btn-reset-fleet').addEventListener('click', () => {
    state.fleetEdits = {};
    renderFleet();
    updateSummary();
  });
  $('#preset-list').addEventListener('click', (e) => {
    const b = e.target.closest('.preset');
    if (!b || b.dataset.preset === state.preset) return;
    state.preset = b.dataset.preset;
    state.configOverrides = {}; // novo perfil = parte dos valores dele
    renderPresets();
    fillAdvanced();
  });
  // setas do teclado no grupo de presets (padrão radiogroup)
  $('#preset-list').addEventListener('keydown', (e) => {
    if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'].includes(e.key)) return;
    const items = $$('#preset-list .preset');
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const next = items[(i + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length];
    next.click();
    $(`#preset-list .preset[data-preset="${next.dataset.preset}"]`)?.focus();
  });
  $('#advanced-grid').addEventListener('input', onAdvancedInput);
  $('#advanced-grid').addEventListener('change', onAdvancedInput);
  $('#btn-run').addEventListener('click', startRun);
  on('scenario', () => { renderFleet(); renderRules(); updateSummary(); });
}
