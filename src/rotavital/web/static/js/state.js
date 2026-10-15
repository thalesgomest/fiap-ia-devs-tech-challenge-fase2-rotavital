// Estado único da aplicação + um barramento simples de eventos entre as views.

export const state = {
  status: null,        // GET /api/status
  cenarios: [],        // resumo de GET /api/cenarios
  presets: {},         // GET /api/presets
  scenario: null,      // cenário selecionado (GET /api/cenarios/{id})
  fleetEdits: {},      // {codigo: {campo: valor}} — só o que mudou
  preset: 'equilibrado',
  configOverrides: {}, // parâmetros avançados alterados em relação ao preset
  live: null,          // execução acompanhada ao vivo
  run: null,           // execução concluída aberta (GET /api/execucoes/{id})
  chats: {},           // {runId: [mensagens]}
  view: 'cenario',
};

export const KEYS = { cenario: 'rotavital.cenario', run: 'rotavital.execucao' };

const bus = new EventTarget();
export const emit = (name, detail) => bus.dispatchEvent(new CustomEvent(name, { detail }));
export const on = (name, fn) => bus.addEventListener(name, (e) => fn(e.detail));
