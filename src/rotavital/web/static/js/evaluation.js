// Selo de qualidade dos textos gerados pela IA (avaliação automática).
import { esc, isNum } from './util.js';

const cls = (n) => (n >= 80 ? 'good' : n >= 60 ? 'mid' : 'bad');
const pct = (v) => (isNum(v) ? Math.round(v * 100) : null);

function line(label, frac) {
  const p = pct(frac);
  if (p === null) return '';
  const tone = p >= 80 ? '' : p >= 60 ? 'warn' : 'bad';
  return `<div class="eval-line"><span>${esc(label)}</span>
    <span class="meter"><span class="${tone}" style="width:${Math.max(0, Math.min(100, p))}%"></span></span>
    <span>${p}%</span></div>`;
}

const list = (items) => (Array.isArray(items) && items.length
  ? `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '');

function stars(n) {
  if (!isNum(n)) return '—';
  const v = Math.max(0, Math.min(5, Math.round(n)));
  return `<span class="stars" aria-label="${v} de 5">${'★'.repeat(v)}<span class="off">${'★'.repeat(5 - v)}</span></span>`;
}

/** HTML do selo "Qualidade NN/100" que expande para os detalhes. */
export function evalBadge(av) {
  if (!av || !isNum(av.nota_geral)) return '<span class="badge b-soft">Sem avaliação</span>';
  const n = Math.round(av.nota_geral);
  const f = av.fidelidade_numerica;
  const c = av.cobertura;
  const j = av.juiz;

  const fid = f ? `<div class="eval-sec"><h4>Fidelidade numérica</h4>
      ${line('Números conferidos com os dados', f.score)}
      <p class="muted">${isNum(f.verificados) ? `${f.verificados} valor(es) verificado(s)` : ''}</p>
      ${f.nao_suportados?.length ? `<p>Valores sem respaldo nos dados:</p>${list(f.nao_suportados)}` : ''}
    </div>` : '';

  const cob = c ? `<div class="eval-sec"><h4>Cobertura</h4>
      ${line('Paradas/itens mencionados', c.score)}
      ${line('Ordem correta', c.ordem_correta)}
      ${c.faltando?.length ? `<p>Faltando no texto:</p>${list(c.faltando)}` : ''}
    </div>` : '';

  const judge = j ? `<div class="eval-sec"><h4>Juiz (LLM)</h4>
      <div class="judge-grid">
        <div><span>Clareza</span>${stars(j.clareza)}</div>
        <div><span>Correção</span>${stars(j.correcao)}</div>
        <div><span>Acionabilidade</span>${stars(j.acionabilidade)}</div>
        <div><span>Segurança</span>${stars(j.seguranca)}</div>
      </div>
      ${j.comentario ? `<p class="eval-comment">“${esc(j.comentario)}”</p>` : ''}
    </div>` : '<div class="eval-sec"><h4>Juiz (LLM)</h4><p class="muted">Não disponível nesta geração (ex.: modo offline).</p></div>';

  return `<details class="eval eval-${cls(n)}">
      <summary>Qualidade ${n}/100</summary>
      <div class="eval-body">${fid}${cob}${judge}</div>
    </details>`;
}

export const generatedBy = (provedor, modelo) => (provedor || modelo
  ? `<span class="gen-by">gerado por <strong>${esc(provedor || '—')}</strong>${modelo ? ` · ${esc(modelo)}` : ''}</span>`
  : '');

/** Aviso quando o LLM falhou e o backend caiu para o texto determinístico. */
export const llmErrorNote = (erro) => (erro
  ? `<p class="alert alert-warn small" role="note">A IA não respondeu (${esc(erro)}). Exibindo o texto gerado pelos modelos determinísticos.</p>`
  : '');
