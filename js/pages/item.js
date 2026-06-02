// js/pages/item.js
// Page /item/:id : faits clés d'une opportunité + analyse IA. Commentaires = C-2.
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import { getOpportunity } from '../lib/opportunities.js';
import { mountComments } from '../components/comments.js';

const CAT = {
  urgent:      { cls: 'cat-red',  label: '🔴 URGENT' },
  interesting: { cls: 'cat-yel',  label: '🟡 INTÉRESSANT' },
  passable:    { cls: 'cat-grey', label: '⚫ PASSABLE' },
};
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const eur = n => n == null ? '' : new Intl.NumberFormat('fr-FR',
  { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);

export async function render(params) {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;

  const me = await getProfile();
  if (navState.token !== myToken) return;

  const root = document.getElementById('appRoot');
  root.innerHTML = `<div class="item-page"><a href="/feed" data-link class="item-back">← Retour au feed</a>
    <div id="itemBody"><div class="page-loading">⏳ Chargement…</div></div></div>`;

  let o;
  try { o = await getOpportunity(params.id); }
  catch (err) {
    if (navState.token !== myToken) return;
    document.getElementById('itemBody').innerHTML = `<div class="error-panel card">❌ ${err.message}</div>`;
    return;
  }
  if (navState.token !== myToken) return;

  const c = CAT[o.category] || CAT.passable;
  const score = o.resale_score != null ? Math.round(o.resale_score) : '–';
  document.getElementById('itemBody').innerHTML = `
    <div class="item-head card">
      <div class="item-photo">${o.image_url ? `<img src="${esc(o.image_url)}" alt="">` : '📷'}</div>
      <div class="item-facts">
        <div><span class="opp-badge ${c.cls}">${c.label} · ${score}</span>${o.price_dropped ? ' <span class="muted">· baisse de prix 📉</span>' : ''}</div>
        <h2>${esc(o.title || 'Sans titre')}</h2>
        <div class="item-price">${eur(o.price)}${o.price_dropped && o.previous_price ? `<span class="opp-old">${eur(o.previous_price)}</span>` : ''}</div>
        <div class="muted">${o.location_city ? `📍 ${esc(o.location_city)}${o.location_postal ? ' ' + esc(o.location_postal) : ''}` : ''}</div>
        <div class="item-stats">
          <div class="stat-box"><div class="stat-label">Prix marché</div><div class="stat-val">${o.est_market_price != null ? '~' + eur(o.est_market_price) : 'n/d'}</div></div>
          <div class="stat-box"><div class="stat-label">Marge</div><div class="stat-val item-gain">${o.est_margin_eur != null ? '+' + eur(o.est_margin_eur) : 'n/d'}</div></div>
          <div class="stat-box"><div class="stat-label">Prix max achat</div><div class="stat-val">${o.max_buy_price != null ? eur(o.max_buy_price) : 'n/d'}</div></div>
        </div>
        ${o.url ? `<a href="${esc(o.url)}" target="_blank" rel="noopener noreferrer" class="btn-lbc">Voir l'annonce sur Leboncoin ↗</a>` : ''}
      </div>
    </div>
    ${o.explanation ? `<div class="item-ai"><div class="item-ai-label">🤖 Analyse</div><div>${esc(o.explanation)}</div></div>` : ''}
    <div id="itemComments"></div>`;

  const commentsEl = document.getElementById('itemComments');
  if (commentsEl && navState.token === myToken) {
    mountComments(commentsEl, { opportunityId: o.id, me });
  }
}
