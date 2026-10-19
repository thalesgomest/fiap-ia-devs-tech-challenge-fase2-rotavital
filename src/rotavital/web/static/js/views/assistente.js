// Passo 5 — chat com o assistente, sempre no contexto da execução atual.
import { state, on } from '../state.js';
import { $, esc, fmt, api, toastError, renderMarkdown } from '../util.js';

function sugestoes() {
  const rotas = state.run?.solucao?.rotas || [];
  const veiculo = rotas[0]?.veiculo;
  const parada = rotas.flatMap((r) => r.paradas || [])[0]?.nome;
  return [
    'Quais entregas críticas estão em risco?',
    veiculo ? `Detalhe a rota da ${veiculo}` : 'Quais rotas foram planejadas?',
    veiculo ? `Se a ${veiculo} atrasar 30 minutos, o que acontece?` : 'Qual é a duração da operação?',
    'Quanto economizamos em relação ao Clarke-Wright?',
    parada ? `Onde está a entrega de ${parada}?` : 'Qual é a distância total?',
    'Como reduzir o custo da operação?',
  ];
}

let waiting = false;

const messages = () => {
  if (!state.run) return [];
  return (state.chats[state.run.id] ??= []);
};

function formatArgs(args) {
  if (!args || typeof args !== 'object') return args ? String(args) : '';
  return Object.entries(args).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ');
}

function messageHtml(m) {
  if (m.papel === 'usuario') {
    return `<div class="msg msg-user"><span class="msg-avatar" aria-hidden="true">Você</span>
      <div class="bubble"><span class="sr-only">Você: </span>${esc(m.conteudo)}</div></div>`;
  }
  const tools = (m.ferramentas || []).map((t) => `
      <details class="tool">
        <summary title="Ferramenta consultada pelo assistente">🔧 ${esc(t.nome)}(${esc(formatArgs(t.argumentos))})</summary>
        ${t.resumo ? `<p>${esc(t.resumo)}</p>` : ''}
      </details>`).join('');
  const meta = m.provedor || m.modelo ? `<p class="msg-meta">${esc(m.provedor || '')}${m.modelo ? ` · ${esc(m.modelo)}` : ''}</p>` : '';
  return `<div class="msg msg-assistant"><span class="msg-avatar" aria-hidden="true"><img src="/static/logo.svg" alt=""></span>
    <div class="bubble"><span class="sr-only">Assistente: </span><div class="md">${renderMarkdown(m.conteudo)}</div>
      ${tools ? `<div class="msg-tools">${tools}</div>` : ''}${meta}</div></div>`;
}

function render() {
  const log = $('#chat-log');
  const msgs = messages();
  const run = state.run;
  $('#chat-context').textContent = run
    ? `Conversando sobre ${run.cenario?.nome || 'a execução'} · ${fmt.date(run.criado_em)} · custo ${fmt.money(run.solucao?.custo_total)}`
    : 'Abra uma execução para conversar.';
  if (!msgs.length) {
    log.innerHTML = `<div class="chat-welcome">
        <img src="/static/logo.svg" alt="">
        <h2>Como posso ajudar?</h2>
        <p>Pergunte sobre rotas, prazos, custos ou simule imprevistos. O assistente consulta os dados desta execução para responder.</p>
      </div>`;
    $('#chat-suggestions').innerHTML = sugestoes()
      .map((s) => `<button type="button" class="suggestion">${esc(s)}</button>`).join('');
  } else {
    log.innerHTML = msgs.map(messageHtml).join('');
    $('#chat-suggestions').innerHTML = '';
  }
  if (waiting) {
    log.insertAdjacentHTML('beforeend', `<div class="msg msg-assistant" id="chat-typing"><span class="msg-avatar" aria-hidden="true"><img src="/static/logo.svg" alt=""></span>
      <div class="bubble"><span class="typing" aria-label="O assistente está escrevendo"><span></span><span></span><span></span></span><p class="small muted">Consultando o assistente. A primeira resposta pode levar alguns minutos.</p></div></div>`);
  }
  log.scrollTop = log.scrollHeight;
  setWaiting(waiting);
}

function setWaiting(w) {
  waiting = w;
  $('#chat-input').disabled = w || !state.run;
  $('#chat-send').disabled = w || !state.run;
  $('#chat-form').setAttribute('aria-busy', w ? 'true' : 'false');
}

async function send(text) {
  const conteudo = text.trim();
  if (!conteudo || waiting || !state.run) return;
  const run = state.run;
  const msgs = messages();
  msgs.push({ papel: 'usuario', conteudo });
  $('#chat-input').value = '';
  autosize();
  waiting = true;
  render();
  try {
    const r = await api(`/api/execucoes/${encodeURIComponent(run.id)}/chat`, {
      method: 'POST',
      json: { mensagens: msgs.map(({ papel, conteudo: c }) => ({ papel, conteudo: c.slice(0, 4000) })) },
    });
    msgs.push({
      papel: 'assistente',
      conteudo: r?.resposta || '_(sem resposta)_',
      ferramentas: r?.ferramentas || [],
      provedor: r?.provedor,
      modelo: r?.modelo,
    });
  } catch (e) {
    // devolve a pergunta para o campo e remove do histórico
    msgs.pop();
    $('#chat-input').value = conteudo;
    toastError(e);
  } finally {
    waiting = false;
    if (state.run === run) render();
    $('#chat-input').focus();
  }
}

function autosize() {
  const t = $('#chat-input');
  t.style.height = 'auto';
  t.style.height = `${Math.min(t.scrollHeight, 180)}px`;
  t.style.overflowY = t.scrollHeight > 180 ? 'auto' : 'hidden';
}

export function initAssistente() {
  $('#chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    send($('#chat-input').value);
  });
  $('#chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      send($('#chat-input').value);
    }
  });
  $('#chat-input').addEventListener('input', autosize);
  $('#chat-suggestions').addEventListener('click', (e) => {
    const b = e.target.closest('.suggestion');
    if (b) send(b.textContent);
  });
  $('#btn-chat-clear').addEventListener('click', () => {
    if (!state.run || waiting) return;
    state.chats[state.run.id] = [];
    render();
  });
  on('run', () => { if (state.view === 'assistente') render(); });
}

export function onShowAssistente() {
  render();
  if (!waiting) $('#chat-input').focus({ preventScroll: true });
}
