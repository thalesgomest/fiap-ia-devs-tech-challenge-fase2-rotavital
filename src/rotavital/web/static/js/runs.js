// Execução "atual": carregar, guardar e avisar as views.
import { state, emit, KEYS } from './state.js';
import { api, storage } from './util.js';

export function setRun(run) {
  if (!run?.solucao) return;
  state.run = run;
  storage.set(KEYS.run, run.id);
  emit('run', run);
}

export async function fetchRun(id) {
  return api(`/api/execucoes/${encodeURIComponent(id)}`);
}
