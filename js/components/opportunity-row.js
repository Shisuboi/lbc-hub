// js/components/opportunity-row.js
// Carte « streaming » d'une opportunité (grille uniforme du feed).
// Toute la carte est un lien SPA vers /item/:id. L'étoile favori (cœur SVG) est un
// bouton à part que le feed intercepte (toggle de classe .on, jamais de texte/emoji).
import { icon } from '../lib/icons.js';

const CAT = {
  urgent:      { cls: 'cat-red',  word: 'Urgent',      color: 'var(--cat-urgent)' },
  interesting: { cls: 'cat-yel',  word: 'Intéressant', color: 'var(--cat-interesting)' },
  passable:    { cls: 'cat-grey', word: 'Passable',    color: 'var(--cat-passable)' },
};
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const eur = n => n == null ? '' : new Intl.NumberFormat('fr-FR',
  { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);

function timeAgo(iso) {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `il y a ${Math.max(1, Math.floor(s / 60))} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return `il y a ${Math.floor(s / 86400)} j`;
}

const thumb = o => o.image_url
  ? `<img src="${esc(o.image_url)}" alt="" loading="lazy">`
  : `<span class="ph-glyph">${icon('image', { size: 30 })}</span>`;

export function starBtn(o, isFav, big = false) {
  return `<button type="button" class="opp-star${isFav ? ' on' : ''}${big ? ' opp-star-lg' : ''}"`
    + ` data-fav-id="${o.id}" title="Favori" aria-label="Favori" aria-pressed="${isFav}">${icon('heart', { size: big ? 22 : 18 })}</button>`;
}

// ===== Carte de grille (streaming) =====
export function opportunityGridCardHtml(o, { isFav = false, distanceKm = null } = {}) {
  const c = CAT[o.category] || CAT.passable;
  const hasMargin = o.est_margin_eur != null && o.est_margin_eur > 0;
  const recent = o.created_at && (Date.now() - new Date(o.created_at).getTime() < 12 * 3600 * 1000);
  const badge = hasMargin
    ? `<span class="deal-badge deal-badge-margin">Marge +${eur(o.est_margin_eur)}</span>`
    : recent
      ? `<span class="deal-badge deal-badge-new">Nouveau</span>`
      : `<span class="deal-badge deal-badge-cat ${c.cls}">${c.word}</span>`;
  const place = o.location_city ? esc(o.location_city) : '—';
  const when = timeAgo(o.created_at);
  const dist = distanceKm != null ? ` · ~${Math.round(distanceKm)} km` : '';

  return `
    <a href="/item/${o.id}" data-link class="deal-card" data-opp-id="${o.id}">
      <div class="deal-thumb">
        ${thumb(o)}
        ${badge}
        ${starBtn(o, isFav)}
      </div>
      <div class="deal-body">
        <div class="deal-titlerow">
          <span class="deal-title">${esc(o.title || 'Sans titre')}</span>
          <span class="deal-price">${eur(o.price)}</span>
        </div>
        <div class="deal-meta">
          <span class="deal-place">${icon('pin', { size: 14 })} ${place}</span>
          <span class="deal-when">${icon('clock', { size: 14 })} ${when}${dist}</span>
        </div>
        <div class="deal-foot">
          <span class="deal-resale">${o.est_market_price != null ? `Revente ~${eur(o.est_market_price)}` : 'Revente n/d'}</span>
          ${hasMargin ? `<span class="deal-gain">+${eur(o.est_margin_eur)}</span>` : ''}
        </div>
      </div>
    </a>`;
}
