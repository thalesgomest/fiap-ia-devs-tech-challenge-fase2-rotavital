// Modal de texto em markdown (instruções do motorista) com impressão.
import { $, renderMarkdown } from './util.js';
import { evalBadge, generatedBy, llmErrorNote } from './evaluation.js';

const dlg = () => $('#md-modal');

export function openModalLoading(eyebrow, title) {
  $('#md-modal-eyebrow').textContent = eyebrow;
  $('#md-modal-title').textContent = title;
  $('#md-modal-meta').innerHTML = '';
  $('#md-modal-body').innerHTML = '<div class="modal-loading"><span class="spinner" aria-hidden="true"></span>Gerando texto com a IA…</div>';
  $('#md-modal-print').disabled = true;
  if (!dlg().open) dlg().showModal();
}

export function fillModal({ markdown, provedor, modelo, avaliacao, erro_llm: erroLlm }) {
  $('#md-modal-meta').innerHTML = `${generatedBy(provedor, modelo)}${evalBadge(avaliacao)}${llmErrorNote(erroLlm)}`;
  $('#md-modal-body').innerHTML = renderMarkdown(markdown);
  $('#md-modal-print').disabled = false;
}

export const closeModal = () => dlg().open && dlg().close();

export function initModal() {
  const d = dlg();
  $('#md-modal-close').addEventListener('click', closeModal);
  // clique no fundo escurecido fecha
  d.addEventListener('click', (e) => { if (e.target === d) closeModal(); });
  $('#md-modal-print').addEventListener('click', () => {
    document.body.classList.add('printing-sheet');
    window.print();
  });
  window.addEventListener('afterprint', () => document.body.classList.remove('printing-sheet'));
}
