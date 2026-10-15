// Mapas Leaflet: um mapa por contêiner, reaproveitado entre renderizações.
import { esc, fmt } from './util.js';
import { PRIO, COLD, prioBadge, tipoLabel, janelaDe } from './domain.js';

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

const registry = {};

export function getMap(id) {
  if (registry[id]) return registry[id].map;
  const map = L.map(id, { scrollWheelZoom: false, zoomSnap: 0.5 });
  L.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(map);
  map.setView([-23.55, -46.63], 11);
  // zoom pela roda só depois que o usuário interage com o mapa
  map.on('focus click', () => map.scrollWheelZoom.enable());
  map.on('blur mouseout', () => map.scrollWheelZoom.disable());
  registry[id] = { map, bounds: null };
  return map;
}

/** Guarda os limites e enquadra assim que o mapa estiver visível. */
export function fitTo(id, bounds) {
  const r = registry[id];
  if (!r || !bounds?.isValid?.()) return;
  r.bounds = bounds;
  refreshMap(id);
}

/** Chamar quando um mapa que estava oculto volta a aparecer. */
export function refreshMap(id, refit = true) {
  const r = registry[id];
  if (!r) return;
  requestAnimationFrame(() => {
    if (!r.map.getContainer().offsetWidth) return;
    r.map.invalidateSize();
    if (refit && r.bounds) r.map.fitBounds(r.bounds, { padding: [30, 30], maxZoom: 14 });
  });
}

const DEPOT_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z" fill="currentColor"/></svg>';

export function depotMarker(dep) {
  const icon = L.divIcon({
    className: 'leaflet-div-icon-reset',
    html: `<span class="mk-depot">${DEPOT_SVG}</span>`,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
  return L.marker([dep.lat, dep.lon], { icon, zIndexOffset: 1000, keyboard: false })
    .bindTooltip(`<div class="tt"><strong>${esc(dep.nome || 'Depósito')}</strong><span class="tt-sub">Depósito — início e fim das rotas</span></div>`,
      { direction: 'top', offset: [0, -14], className: 'rv-tooltip' });
}

/** Conteúdo do tooltip de uma parada (dados sempre escapados). */
export function stopTooltip(p, rules, extra = '') {
  return `<div class="tt"><strong>${esc(p.nome)}</strong>
    <span class="tt-sub">${esc(p.id)} · ${esc(tipoLabel(p.tipo))}</span>
    <dl>
      <dt>Carga</dt><dd>${esc(p.carga || '—')}${p.refrigerado ? ' ❄' : ''}</dd>
      <dt>Demanda</dt><dd>${fmt.kg(p.demanda_kg)}</dd>
      <dt>Janela</dt><dd>${esc(janelaDe(p))}</dd>
      <dt>Prioridade</dt><dd>${prioBadge(p.prioridade, rules)}</dd>
      ${extra}
    </dl></div>`;
}

/** Marcador de parada: cor pela prioridade, anel azul se refrigerada. */
export function stopMarker(p, rules) {
  const color = PRIO[p.prioridade]?.color || PRIO.rotina.color;
  const group = L.featureGroup();
  if (p.refrigerado) {
    L.circleMarker([p.lat, p.lon], {
      radius: 11, color: COLD, weight: 3, fill: false, opacity: 0.95, interactive: false,
    }).addTo(group);
  }
  L.circleMarker([p.lat, p.lon], {
    radius: 7, color: '#ffffff', weight: 2, fillColor: color, fillOpacity: 1,
  }).bindTooltip(stopTooltip(p, rules), { direction: 'top', offset: [0, -6], className: 'rv-tooltip' })
    .addTo(group);
  return group;
}

/** Marcador numerado (ordem de visita) na cor do veículo. */
export function numberedMarker(p, n, color, tooltipHtml) {
  const safeColor = /^#[0-9a-f]{3,8}$/i.test(color) ? color : '#0f766e';
  const cls = `mk-num${p.prioridade === 'critica' ? ' crit' : ''}${p.refrigerado ? ' cold' : ''}`;
  const icon = L.divIcon({
    className: 'leaflet-div-icon-reset',
    html: `<span class="${cls}" style="--c:${safeColor}">${esc(n)}</span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
  const m = L.marker([p.lat, p.lon], { icon, keyboard: false });
  if (tooltipHtml) m.bindTooltip(tooltipHtml, { direction: 'top', offset: [0, -12], className: 'rv-tooltip' });
  return m;
}

/** Linha de rota com contorno branco para destacar sobre o mapa. */
export function routeLine(latlngs, color, weight = 4) {
  return L.featureGroup([
    L.polyline(latlngs, { color: '#ffffff', weight: weight + 3, opacity: 0.85, interactive: false }),
    L.polyline(latlngs, { color, weight, opacity: 0.9, lineJoin: 'round' }),
  ]);
}
