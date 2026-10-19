// RotaVital — ponto de entrada da interface web.
import { state, KEYS } from './js/state.js';
import { $, esc, api, storage } from './js/util.js';
import { initNav, registerView, go, blockedReason, updateNav } from './js/nav.js';
import { setupChartDefaults } from './js/charts.js';
import { initModal } from './js/modal.js';
import { setRun, fetchRun } from './js/runs.js';
import { initCenario, loadScenarioList, selectScenario, onShowCenario } from './js/views/cenario.js';
import { initFrota, loadPresets } from './js/views/frota.js';
import { initOtimizacao, onShowOtimizacao } from './js/views/otimizacao.js';
import { initResultados, onShowResultados } from './js/views/resultados.js';
import { initAssistente, onShowAssistente } from './js/views/assistente.js';
import { initRelatorios, onShowRelatorios } from './js/views/relatorios.js';
import { initHistorico, onShowHistorico } from './js/views/historico.js';

// ------------------------------------------------------- status do LLM
async function loadStatus() {
  const chip = $('#llm-chip');
  const tip = $('#llm-tip');
  try {
    state.status = await api('/api/status');
  } catch {
    chip.classList.remove('online');
    $('#llm-chip-text').textContent = 'Servidor indisponível';
    tip.textContent = 'Não foi possível consultar /api/status.';
    return;
  }
  const llm = state.status?.llm || {};
  const online = llm.modo === 'llm' && llm.disponivel;
  chip.classList.toggle('online', !!online);
  if (online) {
    chip.innerHTML = `<span>LLM: ${esc(llm.provedor)} · ${esc(llm.modelo)}</span><span class="dot" aria-hidden="true"></span><span>online</span>`;
    tip.innerHTML = `Instruções, relatórios e o assistente usam <strong>${esc(llm.provedor)}</strong> (${esc(llm.modelo)}).${llm.detalhe ? `<br>${esc(llm.detalhe)}` : ''}`;
  } else {
    chip.innerHTML = '<span class="dot" aria-hidden="true"></span><span>Modo offline (sem LLM)</span>';
    const modelo = esc(llm.modelo || 'qwen3:4b');
    tip.innerHTML = `${llm.detalhe ? `${esc(llm.detalhe)}<br><br>` : ''}`
      + 'Sem LLM, os textos são montados por modelos determinísticos a partir dos dados da otimização. '
      + `Para ativar a IA: instale o Ollama (ollama.com), rode <code>ollama pull ${modelo}</code>, `
      + 'mantenha o Ollama em execução e reinicie o servidor do RotaVital.';
  }
  chip.setAttribute('aria-label', `${chip.textContent}. ${tip.textContent}`);
}

// -------------------------------------------------------------- início
async function init() {
  setupChartDefaults();
  initNav();
  initModal();
  initCenario();
  initFrota();
  initOtimizacao();
  initResultados();
  initAssistente();
  initRelatorios();
  initHistorico();

  registerView('cenario', { onShow: onShowCenario });
  registerView('otimizacao', { onShow: onShowOtimizacao });
  registerView('resultados', { onShow: onShowResultados });
  registerView('assistente', { onShow: onShowAssistente });
  registerView('relatorios', { onShow: onShowRelatorios });
  registerView('historico', { onShow: onShowHistorico });

  updateNav();
  loadStatus();
  setInterval(loadStatus, 60000);

  await Promise.all([loadScenarioList(), loadPresets()]);

  // restaura o último cenário e a última execução (se ainda existirem)
  const sid = storage.get(KEYS.cenario);
  if (sid && state.cenarios.some((c) => c.id === sid)) await selectScenario(sid, { quiet: true });
  const rid = storage.get(KEYS.run);
  if (rid) {
    try {
      setRun(await fetchRun(rid));
    } catch {
      storage.set(KEYS.run, null);
    }
  }

  const fromHash = location.hash.replace('#', '');
  go(fromHash && !blockedReason(fromHash) ? fromHash : 'cenario');
}

init();
