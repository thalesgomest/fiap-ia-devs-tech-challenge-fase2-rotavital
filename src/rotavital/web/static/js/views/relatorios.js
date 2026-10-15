// Passo 6 — relatórios da execução e do período, e textos gerados com avaliação.
import { state, on } from '../state.js';
import { $, $$, esc, fmt, api, toastError, setBusy, renderMarkdown, isNum } from '../util.js';
import { humanize, formatByKey } from '../domain.js';
import { evalBadge, generatedBy, llmErrorNote } from '../evaluation.js';

let dias = 1;
let textos = [];
const reportCache = {}; // runId -> resposta do relatório da execução

const KINDS = {
  instrucoes: 'Instruções do motorista',
  relatorio: 'Relatório da execução',
  relatorio_execucao: 'Relatório da execução',
  relatorio_periodo: 'Relatório do período',
  chat: 'Resposta do assistente',
};

function reportHtml(r) {
  return `<div class="report-meta">${generatedBy(r.provedor, r.modelo)}${evalBadge(r.avaliacao)}</div>
    ${llmErrorNote(r.erro_llm)}
    <div class="md">${renderMarkdown(r.markdown)}</div>`;
}

const kindLabel = (kind) => {
  if (KINDS[kind]) return KINDS[kind];
  const m = /^relatorio_periodo_(\d+)d$/.exec(kind || '');
  if (m) return m[1] === '1' ? 'Relatório diário' : m[1] === '7' ? 'Relatório semanal' : `Relatório de ${m[1]} dias`;
  return humanize(kind || '—');
};

// ------------------------------------------------------- execução
function renderRunReport() {
  const run = state.run;
  $('#btn-report-run').disabled = !run;
  $('#report-run-hint').textContent = run
    ? `${run.cenario?.nome || 'Execução'} · ${fmt.date(run.criado_em)}`
    : 'Abra ou conclua uma execução para gerar este relatório.';
  const cached = run && reportCache[run.id];
  $('#report-run-out').innerHTML = cached ? reportHtml(cached) : '';
}

async function generateRunReport() {
  const run = state.run;
  if (!run) return;
  const btn = $('#btn-report-run');
  setBusy(btn, true);
  try {
    const r = await api(`/api/execucoes/${encodeURIComponent(run.id)}/relatorio`, { method: 'POST' });
    reportCache[run.id] = r || {};
    if (state.run === run) {
      renderRunReport();
      loadTextos();
    }
  } catch (e) {
    toastError(e);
  } finally {
    setBusy(btn, false);
  }
}

// -------------------------------------------------------- período
/** Separa o agregado em valores numéricos (KPIs) e contagens aninhadas ({nome: n}). */
function splitAggregate(obj) {
  const nums = [];
  const groups = [];
  Object.entries(obj || {}).forEach(([k, v]) => {
    if (k === 'dias') return; // já aparece no rótulo do período
    if (isNum(v)) nums.push([k, v]);
    else if (v && typeof v === 'object' && !Array.isArray(v)) groups.push([k, v]);
  });
  return { nums, groups };
}

async function generatePeriodReport() {
  const btn = $('#btn-report-period');
  setBusy(btn, true);
  try {
    const r = await api(`/api/relatorios/periodo?dias=${dias}`);
    const nExec = Array.isArray(r?.execucoes) ? r.execucoes.length : r?.execucoes;
    const { nums: entries, groups } = splitAggregate(r?.agregado);
    const hasExecKey = entries.some(([k]) => k === 'execucoes');
    const tiles = [
      ...(isNum(nExec) && !hasExecKey ? [['execucoes', nExec]] : []),
      ...entries,
    ];
    $('#report-period-kpis').innerHTML = tiles.map(([k, v]) => `
      <div class="kpi"><span class="kpi-label">${esc(humanize(k))}</span><span class="kpi-value">${esc(formatByKey(k, v))}</span></div>`).join('');
    const groupsHtml = groups.map(([k, obj]) => `<p class="small" style="margin-bottom:8px"><strong>${esc(humanize(k))}:</strong> ${
      Object.entries(obj).map(([n, v]) => `${esc(n)} (${esc(isNum(v) ? fmt.num(v) : v)})`).join(' · ')}</p>`).join('');
    const label = (r?.dias ?? dias) === 1 ? 'último dia' : `últimos ${r?.dias ?? dias} dias`;
    $('#report-period-out').innerHTML = `<p class="small muted" style="margin-bottom:8px">Período: ${esc(label)}${isNum(nExec) ? ` · ${fmt.num(nExec)} execução(ões)` : ''}</p>${groupsHtml}${reportHtml(r || {})}`;
  } catch (e) {
    toastError(e);
  } finally {
    setBusy(btn, false);
  }
}

// --------------------------------------------------------- textos
async function loadTextos() {
  const run = state.run;
  const wrap = $('#textos-wrap');
  $('#btn-refresh-textos').disabled = !run;
  if (!run) {
    wrap.innerHTML = '<p class="placeholder">Abra uma execução para ver os textos gerados para ela.</p>';
    return;
  }
  try {
    textos = (await api(`/api/execucoes/${encodeURIComponent(run.id)}/textos`)) || [];
  } catch (e) {
    toastError(e);
    textos = [];
  }
  if (state.run !== run) return;
  renderTextos();
}

function renderTextos() {
  const wrap = $('#textos-wrap');
  if (!textos.length) {
    wrap.innerHTML = '<p class="placeholder">Nenhum texto gerado ainda. Gere instruções, relatórios ou converse com o assistente.</p>';
    return;
  }
  wrap.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th scope="col">Tipo</th><th scope="col">Alvo</th><th scope="col">Modelo</th><th scope="col">Data</th><th scope="col">Avaliação</th><th scope="col"><span class="sr-only">Ações</span></th></tr></thead>
      <tbody>${textos.map((t, i) => `
        <tr>
          <td><strong>${esc(kindLabel(t.kind))}</strong></td>
          <td>${esc(t.target || '—')}</td>
          <td>${esc(t.provider || '—')}${t.model ? ` · <span class="muted">${esc(t.model)}</span>` : ''}</td>
          <td class="tnum">${esc(fmt.date(t.created_at))}</td>
          <td style="white-space:normal">${evalBadge(t.evaluation)}</td>
          <td><button type="button" class="btn btn-ghost btn-sm" data-texto="${i}" aria-expanded="false" aria-controls="texto-${i}">Ver texto</button></td>
        </tr>
        <tr class="textos-content" id="texto-${i}" hidden><td colspan="6"><div class="md"></div></td></tr>`).join('')}
      </tbody></table></div>`;
}

function toggleTexto(btn) {
  const i = Number(btn.dataset.texto);
  const row = document.getElementById(`texto-${i}`);
  if (!row) return;
  const open = row.hidden;
  row.hidden = !open;
  btn.setAttribute('aria-expanded', String(open));
  btn.textContent = open ? 'Ocultar' : 'Ver texto';
  const box = row.querySelector('.md');
  if (open && !box.dataset.ready) {
    box.innerHTML = renderMarkdown(textos[i]?.content);
    box.dataset.ready = '1';
  }
}

export function initRelatorios() {
  $('#btn-report-run').addEventListener('click', generateRunReport);
  $('#btn-report-period').addEventListener('click', generatePeriodReport);
  $('#period-toggle').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-dias]');
    if (!b) return;
    dias = Number(b.dataset.dias);
    $$('#period-toggle button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  });
  $('#btn-refresh-textos').addEventListener('click', loadTextos);
  $('#textos-wrap').addEventListener('click', (e) => {
    const b = e.target.closest('[data-texto]');
    if (b) toggleTexto(b);
  });
  on('run', () => { if (state.view === 'relatorios') onShowRelatorios(); });
}

export function onShowRelatorios() {
  renderRunReport();
  loadTextos();
}
