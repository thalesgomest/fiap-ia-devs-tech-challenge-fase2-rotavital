// Vocabulário do domínio: prioridades, tipos de parada, cores de veículos e rótulos.
import { esc, fmt, isNum } from './util.js';

export const PRIO = {
  critica: { label: 'Crítica', color: '#e11d48' },
  alta: { label: 'Alta', color: '#f59e0b' },
  rotina: { label: 'Rotina', color: '#64748b' },
};
export const COLD = '#0ea5e9';

export const prioLabel = (p, rules) => rules?.[p]?.rotulo || PRIO[p]?.label || p || '—';
export const prioBadge = (p, rules) =>
  `<span class="badge b-${PRIO[p] ? p : 'rotina'}">${esc(prioLabel(p, rules))}</span>`;
export const coldBadge = (short = false) =>
  `<span class="badge b-cold" title="Carga refrigerada">❄${short ? '' : ' Refrigerado'}</span>`;

const TIPOS = {
  hospital: 'Hospital', ubs: 'UBS', domiciliar: 'Domiciliar', laboratorio: 'Laboratório',
  clinica: 'Clínica', hemocentro: 'Hemocentro', upa: 'UPA', ama: 'AMA', farmacia: 'Farmácia',
};
export const tipoLabel = (t) => TIPOS[t] || (t ? t.charAt(0).toUpperCase() + t.slice(1) : '—');

export const MOTIVOS = {
  estagnacao: 'Estagnação',
  max_geracoes: 'Máximo de gerações',
  tempo_limite: 'Tempo limite',
  interrompido: 'Interrompido',
};
export const motivoLabel = (m) => MOTIVOS[m] || m || '—';

export const janelaDe = (p) =>
  p.janela || (p.janela_inicio || p.janela_fim ? `${p.janela_inicio ?? '?'}–${p.janela_fim ?? '?'}` : '—');

// Paleta categórica dos veículos — a mesma no mapa, nos cards e nos gráficos.
export const PALETTE = [
  '#2563eb', '#db2777', '#16a34a', '#9333ea', '#ea580c',
  '#0891b2', '#ca8a04', '#4f46e5', '#65a30d',
];

/** Nomes dos veículos na ordem em que o backend os numera ("MOTO #1", "MOTO #2"...). */
export function vehicleNames(frota = []) {
  const names = [];
  for (const v of frota) {
    for (let i = 1; i <= (v.quantidade || 0); i += 1) names.push(`${v.codigo} #${i}`);
  }
  return names;
}

/** Devolve uma função nome -> cor estável para a frota do cenário. */
export function makeColorMap(frota) {
  const map = new Map();
  vehicleNames(frota).forEach((n, i) => map.set(n, PALETTE[i % PALETTE.length]));
  return (name) => {
    if (!map.has(name)) map.set(name, PALETTE[map.size % PALETTE.length]);
    return map.get(name);
  };
}

// Rótulos legíveis para chaves snake_case vindas da API.
const KEY_LABELS = {
  custo_total: 'Custo total', custo_operacional: 'Custo operacional', multa_atraso: 'Multa por atraso',
  multa_frota: 'Multa de frota', distancia_km: 'Distância', duracao_total_min: 'Duração total',
  co2_kg: 'CO₂', veiculos_usados: 'Veículos usados', veiculos_excedentes: 'Veículos excedentes',
  entregas: 'Entregas', entregas_no_prazo: 'Entregas no prazo', taxa_no_prazo: 'Taxa no prazo',
  criticas_total: 'Críticas', criticas_no_prazo: 'Críticas no prazo', atraso_total_min: 'Atraso total',
  ocupacao_media: 'Ocupação média', execucoes: 'Execuções', economia_rs: 'Economia',
  economia_pct: 'Economia', economia_total: 'Economia total', custo_medio: 'Custo médio',
};
// unidades somem do rótulo porque o valor formatado já as mostra
const TOKENS = {
  kg: '', km: '', pct: '', rs: '', min: '', s: '', co2: 'CO₂', medio: 'médio', medios: 'médios', media: 'média',
  execucoes: 'execuções', cenario: 'cenário', criticas: 'críticas', distancia: 'distância', ocupacao: 'ocupação',
  veiculos: 'veículos', duracao: 'duração',
};
export function humanize(key) {
  if (KEY_LABELS[key]) return KEY_LABELS[key];
  const words = String(key).split('_').filter(Boolean).map((w) => (Object.hasOwn(TOKENS, w) ? TOKENS[w] : w)).filter(Boolean);
  const s = words.join(' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Formata um número de acordo com o que o nome da chave sugere. */
export function formatByKey(key, v) {
  if (!isNum(v)) return '—';
  const k = key.toLowerCase();
  if (/_pct$|percent/.test(k)) return fmt.pctRaw(v);
  if (/custo|multa|economia|_rs$|valor|receita/.test(k)) return fmt.money(v);
  if (/taxa|ocupacao|fracao|uso_/.test(k)) return v <= 1.0001 ? fmt.pct(v) : fmt.pctRaw(v);
  if (/co2/.test(k)) return fmt.kg(v);
  if (/_km$|distancia/.test(k)) return fmt.km(v);
  if (/_kg$/.test(k)) return fmt.kg(v);
  if (/_min$/.test(k)) return fmt.dur(v);
  if (/_s$|segundos/.test(k)) return fmt.secs(v);
  return fmt.num(v, Number.isInteger(v) ? 0 : 2);
}
