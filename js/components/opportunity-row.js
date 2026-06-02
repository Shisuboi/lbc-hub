// js/components/opportunity-row.js
// HTML d'une ligne du feed dense. La ligne entière est un lien SPA vers /item/:id.
// L'étoile favori est un bouton à part (le feed intercepte son clic).

const CAT = {
  urgent:      { cls: 'cat-red',  label: '🔴', color: 'var(--c-cat-red)' },
  interesting: { cls: 'cat-yel',  label: '🟡', color: 'var(--c-cat-yel)' },
  passable:    { cls: 'cat-grey', label: '⚫', color: 'var(--c-cat-grey)' },
};
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const eur = n => n == null ? '' : new Intl.NumberFormat('fr-FR',
  { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);

export function opportunityRowHtml(o, { isFav = false, commentCount = 0, hasNewComments = false, distanceKm = null } = {}) {
  const c = CAT[o.category] || CAT.passable;
  const score = o.resale_score != null ? Math.round(o.resale_score) : '–';
  const margin = o.est_margin_eur != null
    ? `+${eur(o.est_margin_eur)}${o.est_margin_pct != null ? ` / +${Math.round(o.est_margin_pct)}%` : ''}`
    : '';
  const thumb = o.image_url
    ? `<img src="${esc(o.image_url)}" alt="" loading="lazy">`
    : '📷';
  return `
    <a href="/item/${o.id}" data-link class="opp-row" data-opp-id="${o.id}">
      <span class="opp-stripe" style="background:${c.color}"></span>
      <span class="opp-thumb">${thumb}</span>
      <span class="opp-main">
        <span class="opp-title">${esc(o.title || 'Sans titre')}
          <span class="opp-badge ${c.cls}">${c.label} ${score}</span></span>
        <span class="opp-meta">${o.location_city ? `📍 ${esc(o.location_city)}` : ''}${
          distanceKm != null ? ` <span class="opp-dist">· à ~${Math.round(distanceKm)} km</span>` : ''}${
          commentCount > 0
            ? ` <span class="opp-comments">💬 ${commentCount}${hasNewComments ? '<span class="opp-new-dot" title="Nouveaux commentaires"></span>' : ''}</span>`
            : ''}</span>
      </span>
      <span class="opp-pricecol">
        <span class="opp-price">${eur(o.price)}${o.price_dropped && o.previous_price
          ? `<span class="opp-old">${eur(o.previous_price)}</span>` : ''}</span>
        ${margin ? `<span class="opp-margin">${margin}</span>` : ''}
      </span>
      <button type="button" class="opp-star${isFav ? ' on' : ''}" data-fav-id="${o.id}"
        title="Favori" aria-label="Favori">${isFav ? '⭐' : '☆'}</button>
    </a>`;
}
