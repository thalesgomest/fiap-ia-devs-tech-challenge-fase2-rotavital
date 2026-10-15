// Navegação entre as views (stepper lateral / abas no celular).
import { state, on } from './state.js';
import { $, $$, fmt, toast } from './util.js';

const views = {};
export function registerView(name, hooks) { views[name] = hooks; }

// Motivo pelo qual uma etapa está bloqueada (null = liberada).
const RULES = {
  cenario: () => null,
  frota: () => (state.scenario ? null : 'Selecione um cenário primeiro'),
  otimizacao: () => (state.live ? null : 'Inicie uma otimização em “Frota & Regras”'),
  resultados: () => (state.run ? null : 'Conclua uma otimização ou abra uma execução do histórico'),
  assistente: () => (state.run ? null : 'Disponível depois que houver uma execução concluída'),
  relatorios: () => null,
  historico: () => null,
};
export const blockedReason = (view) => RULES[view]?.() ?? null;

export function go(view, { focus = false } = {}) {
  if (!RULES[view] || blockedReason(view)) return false;
  const prev = state.view;
  state.view = view;
  $$('.view').forEach((sec) => { sec.hidden = sec.dataset.view !== view; });
  if (prev !== view) views[prev]?.onHide?.();
  updateNav();
  views[view]?.onShow?.();
  window.scrollTo({ top: 0 });
  if (focus) $(`#view-${view} h1`)?.focus({ preventScroll: true });
  try { history.replaceState(null, '', `#${view}`); } catch { /* ignora */ }
  // no celular, mantém a aba ativa visível
  $(`#nav .step[data-view="${view}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  return true;
}

export function updateNav() {
  $$('#nav .step').forEach((btn) => {
    const v = btn.dataset.view;
    const reason = blockedReason(v);
    btn.setAttribute('aria-disabled', reason ? 'true' : 'false');
    btn.title = reason || '';
    const active = v === state.view;
    btn.classList.toggle('active', active);
    if (active) btn.setAttribute('aria-current', 'step');
    else btn.removeAttribute('aria-current');
  });
  const done = {
    cenario: !!state.scenario,
    frota: !!state.live || !!state.run,
    otimizacao: !!state.live && state.live.status !== 'executando',
    resultados: !!state.run,
  };
  Object.entries(done).forEach(([v, ok]) => $(`#nav .step[data-view="${v}"]`)?.classList.toggle('done', ok));

  // subtítulos e rodapé com o contexto atual
  const sc = state.scenario;
  $('#nav-sub-cenario').textContent = sc ? sc.nome : 'Escolha a operação';
  if (state.live) {
    const lbl = { executando: 'Em execução…', concluido: 'Concluída', interrompido: 'Interrompida', erro: 'Erro' };
    $('#nav-sub-otimizacao').textContent = lbl[state.live.status] || 'Evolução ao vivo';
  }
  $('#nav-sub-resultados').textContent = state.run
    ? fmt.money(state.run.solucao?.custo_total)
    : 'Rotas e indicadores';
  $('#ctx-cenario').textContent = sc ? sc.nome : '—';
  $('#ctx-cenario').title = sc ? sc.nome : '';
  $('#ctx-run').textContent = state.run ? fmt.date(state.run.criado_em) : '—';
}

export function initNav() {
  $('#nav').addEventListener('click', (e) => {
    const btn = e.target.closest('.step');
    if (!btn) return;
    const reason = blockedReason(btn.dataset.view);
    if (reason) { toast(reason, 'info', 3000); return; }
    go(btn.dataset.view, { focus: true });
  });
  ['scenario', 'run', 'live'].forEach((evt) => on(evt, updateNav));
}
