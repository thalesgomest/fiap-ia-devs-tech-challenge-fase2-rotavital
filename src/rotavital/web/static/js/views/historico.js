// Passo 7 — histórico de execuções; abrir uma linha carrega os resultados.
import { state } from '../state.js';
import { $, esc, fmt, api, toastError } from '../util.js';
import { motivoLabel } from '../domain.js';
import { setRun, fetchRun } from '../runs.js';
import { setScenario } from './cenario.js';
import { go } from '../nav.js';

let runs = [];
let loading = false;

async function load() {
  if (loading) return;
  loading = true;
  $('#history-tbody').innerHTML = '<tr><td colspan="9" class="empty">Carregando…</td></tr>';
  try {
    runs = (await api('/api/execucoes?limite=30')) || [];
  } catch (e) {
    toastError(e);
    runs = [];
  } finally {
    loading = false;
  }
  render();
}

function render() {
  $('#history-empty').hidden = runs.length > 0;
  $('#history-tbody').innerHTML = runs.map((r) => {
    const k = r.kpis || {};
    const g = r.ga || {};
    const current = state.run?.id === r.id;
    return `<tr data-id="${esc(r.id)}"${current ? ' class="current" aria-current="true"' : ''}>
        <td class="tnum"><button type="button" class="row-link" data-open="${esc(r.id)}">${esc(fmt.date(r.criado_em))}</button></td>
        <td class="wrap">${esc(r.cenario || r.cenario_id || '—')}</td>
        <td class="num"><strong>${fmt.money(k.custo_total)}</strong></td>
        <td class="num">${fmt.pct(k.taxa_no_prazo)}</td>
        <td class="num">${fmt.num(k.veiculos_usados)}</td>
        <td class="num">${fmt.km(k.distancia_km)}</td>
        <td class="num">${fmt.num(g.geracoes)}</td>
        <td>${esc(motivoLabel(g.motivo_parada))}</td>
        <td class="num">${fmt.secs(g.tempo_s)}</td>
      </tr>`;
  }).join('');
}

async function openRun(id) {
  try {
    const run = await fetchRun(id);
    setRun(run);
    const sid = run.cenario?.id;
    if (sid && state.scenario?.id !== sid) {
      try {
        setScenario(await api(`/api/cenarios/${encodeURIComponent(sid)}`));
      } catch { /* cenário pode ter sido removido; os resultados usam os dados da execução */ }
    }
    go('resultados', { focus: true });
  } catch (e) {
    toastError(e);
  }
}

export function initHistorico() {
  $('#btn-refresh-history').addEventListener('click', load);
  $('#history-tbody').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-id]');
    if (tr) openRun(tr.dataset.id);
  });
}

export const onShowHistorico = () => load();
