// Utilitários compartilhados: escape de HTML, formatação pt-BR, cliente da API,
// toasts, armazenamento local e renderização segura de markdown.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
/** Escapa qualquer valor vindo da API antes de ir para innerHTML. */
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ESC[c]);

export const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const brlCompact = new Intl.NumberFormat('pt-BR', {
  style: 'currency', currency: 'BRL', notation: 'compact', maximumFractionDigits: 1,
});
const nfCache = {};
const nf = (d) => (nfCache[d] ??= new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: d, maximumFractionDigits: d,
}));

export const fmt = {
  money: (v) => (isNum(v) ? brl.format(v) : '—'),
  moneyShort: (v) => (isNum(v) ? brlCompact.format(v) : '—'),
  num: (v, d = 0) => (isNum(v) ? nf(d).format(v) : '—'),
  /** fração 0..1 -> "94,4%" */
  pct: (v, d = 1) => (isNum(v) ? `${nf(d).format(v * 100)}%` : '—'),
  /** valor já em porcentagem -> "50,4%" */
  pctRaw: (v, d = 1) => (isNum(v) ? `${nf(d).format(v)}%` : '—'),
  km: (v) => (isNum(v) ? `${nf(1).format(v)} km` : '—'),
  kg: (v) => (isNum(v) ? `${nf(1).format(v)} kg` : '—'),
  min: (v) => (isNum(v) ? `${nf(0).format(v)} min` : '—'),
  secs: (v) => (isNum(v) ? `${nf(1).format(v)} s` : '—'),
  dur(v) {
    if (!isNum(v)) return '—';
    const total = Math.round(v);
    const h = Math.floor(total / 60);
    const m = total % 60;
    return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`;
  },
  date(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? String(iso)
      : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  },
};

// ------------------------------------------------------------------ API
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function detailMessage(data, status) {
  const d = data && typeof data === 'object' ? data.detail : null;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    return d.map((e) => {
      const loc = Array.isArray(e?.loc) ? e.loc.filter((p) => p !== 'body').join('.') : '';
      return loc ? `${loc}: ${e.msg}` : (e?.msg ?? String(e));
    }).join(' · ');
  }
  if (status === 404) return 'Recurso não encontrado.';
  return `Erro ${status} ao falar com o servidor.`;
}

/** fetch com JSON/multipart e erros no formato FastAPI ({detail}). */
export async function api(path, { method = 'GET', json, form } = {}) {
  const opts = { method, headers: { Accept: 'application/json' } };
  if (json !== undefined) {
    opts.body = JSON.stringify(json);
    opts.headers['Content-Type'] = 'application/json';
  } else if (form) {
    opts.body = form;
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError('Não foi possível conectar ao servidor. Ele está rodando?', 0);
  }
  const text = await res.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!res.ok) throw new ApiError(detailMessage(data, res.status), res.status);
  return data;
}

// --------------------------------------------------------------- toasts
export function toast(message, type = 'info', ms = 5000) {
  const box = document.getElementById('toasts');
  if (!box) return;
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  const p = document.createElement('p');
  p.textContent = message;
  const close = document.createElement('button');
  close.type = 'button';
  close.setAttribute('aria-label', 'Fechar aviso');
  close.textContent = '✕';
  el.append(p, close);
  const remove = () => el.remove();
  close.addEventListener('click', remove);
  box.append(el);
  setTimeout(remove, ms);
}
export const toastError = (err) => toast(err?.message || String(err), 'error', 8000);

// ------------------------------------------------------ armazenamento
export const storage = {
  get(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  },
  set(key, value) {
    try {
      if (value == null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch { /* modo privado ou armazenamento bloqueado */ }
  },
};

// ------------------------------------------------------------ markdown
/** Markdown do LLM -> HTML sempre sanitizado pelo DOMPurify. */
export function renderMarkdown(text) {
  const src = String(text ?? '');
  if (!window.DOMPurify) return `<p>${esc(src)}</p>`;
  const raw = window.marked ? window.marked.parse(src, { gfm: true, breaks: true }) : esc(src);
  return window.DOMPurify.sanitize(raw);
}

// ----------------------------------------------------------------- misc
/** Liga/desliga o estado "carregando" de um botão. */
export function setBusy(btn, busy) {
  if (!btn) return;
  btn.disabled = busy;
  btn.classList.toggle('busy', busy);
  btn.setAttribute('aria-busy', busy ? 'true' : 'false');
}

export function downloadFile(filename, content, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
