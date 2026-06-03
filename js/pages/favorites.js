// js/pages/favorites.js
// Page /favorites — vraie page (pas une redirection) : grille des opportunités mises
// en favori, même langage « streaming » que le feed. Décocher le cœur retire la carte.
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import { listOpportunities } from '../lib/opportunities.js';
import { opportunityGridCardHtml } from '../components/opportunity-row.js';
import { loadFavorites, toggleFavorite, isFav } from '../lib/item-favorites.js';
import { icon } from '../lib/icons.js';

export async function render() {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;

  const root = document.getElementById('appRoot');
  root.innerHTML = `
    <section class="feed-page">
      <header class="topbar glass-panel">
        <span class="topbar-brand">${icon('heart', { size: 18 })} Favoris</span>
        <div class="topbar-search">
          ${icon('search', { size: 18 })}
          <input id="favSearch" placeholder="Filtrer mes favoris…" aria-label="Filtrer">
        </div>
      </header>

      <div class="feed-hero">
        <h1>Mes favoris</h1>
        <p class="feed-hero-sub" id="favSub">Chargement…</p>
      </div>

      <div id="favList" class="deal-grid"></div>
      <div id="favEmpty" class="empty-state glass-panel hidden">
        <h3>Aucun favori pour l'instant</h3>
        <p>Touche le cœur sur une opportunité du feed pour la retrouver ici.</p>
        <a href="/feed" data-link class="pill pill-primary" style="margin-top:14px">Parcourir le feed</a>
      </div>
    </section>`;

  const state = { items: [], text: '' };

  const me = await getProfile();
  if (navState.token !== myToken) return;
  await loadFavorites(me?.id);
  if (navState.token !== myToken) return;

  try { state.items = await listOpportunities(); }
  catch (err) {
    if (navState.token !== myToken) return;
    document.getElementById('favList').innerHTML = `<div class="error-panel glass-panel">❌ ${err.message}</div>`;
    return;
  }
  if (navState.token !== myToken) return;

  renderList();

  document.getElementById('favSearch').addEventListener('input', e => { state.text = e.target.value.trim().toLowerCase(); renderList(); });

  // Décocher un favori → retire la carte
  document.getElementById('favList').addEventListener('click', async e => {
    const star = e.target.closest('.opp-star');
    if (!star) return;
    e.preventDefault(); e.stopPropagation();
    if (!me?.id || star.dataset.pending) return;
    const id = star.dataset.favId;
    star.dataset.pending = '1';
    try {
      await toggleFavorite(me.id, id);
      renderList();
    } catch (_) {
      delete star.dataset.pending;
    }
  });

  function renderList() {
    const grid = document.getElementById('favList');
    const sub = document.getElementById('favSub');
    const empty = document.getElementById('favEmpty');
    if (!grid || !sub || !empty) return;

    let favList = state.items.filter(o => isFav(o.id));
    if (state.text) favList = favList.filter(o => (o.title || '').toLowerCase().includes(state.text));

    grid.innerHTML = favList.map(o => opportunityGridCardHtml(o, { isFav: true })).join('');
    empty.classList.toggle('hidden', favList.length > 0);
    const n = favList.length;
    sub.textContent = n > 0
      ? `${n} opportunité${n > 1 ? 's' : ''} en favori.`
      : (state.text ? 'Aucun favori ne correspond à ce filtre.' : 'Tu n\'as pas encore de favori.');
  }
}
