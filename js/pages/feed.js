// js/pages/feed.js
// Page /feed — layout « streaming » : topbar (marque + recherche) → hero "À surveiller"
// → barre de pills (catégories / favoris / tri / secteur · rayon) → grille de cartes.
// Toutes les fonctions sont conservées (recherche, tri, 4 catégories, favoris, proximité,
// realtime). Cartes uniformes, pas de liste dense ni de hero par item.
import { supa } from '../supabase-client.js';
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import { listOpportunities, filterAndSort } from '../lib/opportunities.js';
import { opportunityGridCardHtml } from '../components/opportunity-row.js';
import { loadFavorites, toggleFavorite, isFav } from '../lib/item-favorites.js';
import { getHome, setHome, getRadius, setRadius, haversineKm } from '../lib/geo-home.js';
import { icon } from '../lib/icons.js';

const CATS = [
  { key: 'all', label: 'Toutes', dot: '' },
  { key: 'urgent', label: 'Urgent', dot: 'dot-red' },
  { key: 'interesting', label: 'Intéressant', dot: 'dot-yel' },
  { key: 'passable', label: 'Passable', dot: 'dot-grey' },
];

export async function render() {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;

  const root = document.getElementById('appRoot');
  root.innerHTML = `
    <section class="feed-page">
      <header class="topbar glass-panel">
        <span class="topbar-brand">LBC<span class="accent-text">Hub</span></span>
        <div class="topbar-search">
          ${icon('search', { size: 18 })}
          <input id="feedSearch" placeholder="Rechercher un titre…" aria-label="Rechercher">
        </div>
      </header>

      <div class="feed-hero">
        <h1>À surveiller</h1>
        <p class="feed-hero-sub" id="feedHeroSub">Chargement…</p>
      </div>

      <div class="pills">
        <div class="pill-group" id="feedChips">
          ${CATS.map((c, i) => `<button type="button" class="pill chip${i === 0 ? ' on' : ''}" data-cat="${c.key}">${c.dot ? `<i class="dot ${c.dot}"></i>` : ''}${c.label}</button>`).join('')}
        </div>
        <button type="button" class="pill chip pill-fav" id="feedFav">${icon('heart', { size: 15 })} Favoris</button>
        <label class="pill pill-field">Trier
          <select id="feedSort">
            <option value="recent">récentes</option>
            <option value="score">score</option>
            <option value="margin">marge €</option>
          </select>
        </label>
        <div class="pill pill-field pill-geo">
          ${icon('pin', { size: 15 })}
          <input id="feedSecteur" placeholder="Secteur (CP ou ville)">
        </div>
        <label class="pill pill-field">
          <select id="feedRadius">
            <option value="all">France</option>
            <option value="5">≤ 5 km</option>
            <option value="10">≤ 10 km</option>
            <option value="25">≤ 25 km</option>
            <option value="50">≤ 50 km</option>
            <option value="100">≤ 100 km</option>
          </select>
        </label>
        <span class="feed-geo-msg" id="feedGeoMsg"></span>
      </div>

      <div id="feedList" class="deal-grid"></div>
      <nav id="feedPagination" class="pagination hidden"></nav>
      <div id="feedEmpty" class="empty-state glass-panel hidden">
        <h3>Aucune opportunité pour l'instant</h3>
        <p>Le moteur n'a encore rien remonté, ou aucune recherche n'est active.</p>
      </div>
    </section>`;

  const PAGE_SIZE = 50;
  const state = { items: [], category: 'all', sort: 'recent', text: '', favOnly: false, page: 1 };
  let firstPaint = true;

  const me = await getProfile();
  if (navState.token !== myToken) return;
  await loadFavorites(me?.id);
  if (navState.token !== myToken) return;

  let items;
  try { items = await listOpportunities(); }
  catch (err) {
    if (navState.token !== myToken) return;
    document.getElementById('feedList').innerHTML = `<div class="error-panel glass-panel">❌ ${err.message}</div>`;
    return;
  }
  if (navState.token !== myToken) return;
  state.items = items;

  renderList();

  // Recherche / tri
  document.getElementById('feedSearch').addEventListener('input', e => { state.text = e.target.value.trim(); state.page = 1; renderList(); });
  document.getElementById('feedSort').addEventListener('change', e => { state.sort = e.target.value; state.page = 1; renderList(); });

  // Catégories (pills)
  document.getElementById('feedChips').addEventListener('click', e => {
    const cat = e.target.closest('[data-cat]');
    if (!cat) return;
    state.category = cat.dataset.cat;
    state.page = 1;
    document.querySelectorAll('#feedChips [data-cat]').forEach(b => b.classList.toggle('on', b === cat));
    renderList();
  });

  // Favoris
  const favBtn = document.getElementById('feedFav');
  favBtn.addEventListener('click', () => {
    state.favOnly = !state.favOnly;
    state.page = 1;
    favBtn.classList.toggle('on', state.favOnly);
    renderList();
  });

  // Secteur + rayon (proximité)
  const secteurEl = document.getElementById('feedSecteur');
  const radiusEl = document.getElementById('feedRadius');
  const geoMsg = document.getElementById('feedGeoMsg');
  const home0 = getHome();
  if (home0) { secteurEl.value = home0.label; geoMsg.textContent = home0.label; }
  radiusEl.value = getRadius();
  secteurEl.addEventListener('change', async () => {
    const q = secteurEl.value.trim();
    if (!q) return;
    geoMsg.textContent = 'Localisation…';
    try {
      const home = await setHome(q);
      geoMsg.textContent = home.label;
      renderList();
    } catch (err) { geoMsg.textContent = '❌ ' + err.message; }
  });
  radiusEl.addEventListener('change', () => { setRadius(radiusEl.value); state.page = 1; renderList(); });

  // Favori : toggle (délégation sur la grille) — bascule de classe, pas de texte
  document.getElementById('feedList').addEventListener('click', async e => {
    const star = e.target.closest('.opp-star');
    if (!star) return;
    e.preventDefault(); e.stopPropagation();
    if (!me?.id || star.dataset.pending) return;
    const id = star.dataset.favId;
    const willFav = !isFav(id);
    star.dataset.pending = '1';
    star.classList.toggle('on', willFav);
    star.setAttribute('aria-pressed', String(willFav));
    try {
      await toggleFavorite(me.id, id);
      if (state.favOnly) renderList();
    } catch (_) {
      star.classList.toggle('on', !willFav);
      star.setAttribute('aria-pressed', String(!willFav));
    } finally { delete star.dataset.pending; }
  });

  // Realtime : nouvelle opportunité
  if (window.__feedChannel) { try { await supa.removeChannel(window.__feedChannel); } catch (_) {} window.__feedChannel = null; }
  if (navState.token !== myToken) return;
  const channel = supa.channel('opportunities-feed')
    .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'opportunities' }, payload => {
      if (payload.new?.status === 'active') { state.items.unshift(payload.new); renderList(); }
    })
    .subscribe();
  window.__feedChannel = channel;

  function renderList() {
    const grid = document.getElementById('feedList');
    const sub = document.getElementById('feedHeroSub');
    const empty = document.getElementById('feedEmpty');
    const paginationEl = document.getElementById('feedPagination');
    if (!grid || !sub || !empty || !paginationEl) return; // navigated away

    const list = filterAndSort(state.items, { category: state.category, sort: state.sort, text: state.text });
    let finalList = state.favOnly ? list.filter(o => isFav(o.id)) : list;

    const home = getHome();
    const radius = getRadius();
    if (home && radius !== 'all') {
      const rad = Number(radius);
      finalList = finalList.filter(o =>
        o.lat != null && o.lon != null && haversineKm(home.lat, home.lon, o.lat, o.lon) <= rad);
    }

    const totalItems = finalList.length;
    const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * PAGE_SIZE;
    const pageItems = finalList.slice(start, start + PAGE_SIZE);

    grid.innerHTML = pageItems.map(o => {
      const dist = (home && o.lat != null && o.lon != null) ? haversineKm(home.lat, home.lon, o.lat, o.lon) : null;
      return opportunityGridCardHtml(o, { isFav: isFav(o.id), distanceKm: dist });
    }).join('');

    empty.classList.toggle('hidden', totalItems > 0);
    sub.textContent = totalItems > 0
      ? `${totalItems} opportunité${totalItems > 1 ? 's' : ''} — page ${state.page}/${totalPages}`
      : 'Aucune opportunité ne correspond à ces filtres.';

    // Pagination
    if (totalPages > 1) {
      paginationEl.classList.remove('hidden');
      let html = '';
      html += `<button class="pg-btn pg-prev${state.page <= 1 ? ' pg-disabled' : ''}" data-pg="prev">← Préc.</button>`;
      const range = paginationRange(state.page, totalPages);
      for (const p of range) {
        if (p === '…') {
          html += `<span class="pg-ellipsis">…</span>`;
        } else {
          html += `<button class="pg-btn pg-num${p === state.page ? ' pg-active' : ''}" data-pg="${p}">${p}</button>`;
        }
      }
      html += `<button class="pg-btn pg-next${state.page >= totalPages ? ' pg-disabled' : ''}" data-pg="next">Suiv. →</button>`;
      paginationEl.innerHTML = html;
    } else {
      paginationEl.classList.add('hidden');
      paginationEl.innerHTML = '';
    }

    if (firstPaint && totalItems) {
      firstPaint = false;
      grid.classList.add('is-entering');
      setTimeout(() => grid.classList.remove('is-entering'), 1200);
    }
  }

  // Pagination click handler
  document.getElementById('feedPagination').addEventListener('click', e => {
    const btn = e.target.closest('[data-pg]');
    if (!btn || btn.classList.contains('pg-disabled')) return;
    const val = btn.dataset.pg;
    const totalPages = Math.max(1, Math.ceil(state.items.length / PAGE_SIZE));
    if (val === 'prev') state.page = Math.max(1, state.page - 1);
    else if (val === 'next') state.page = Math.min(totalPages, state.page + 1);
    else state.page = Number(val);
    renderList();
    document.querySelector('.feed-hero')?.scrollIntoView({ behavior: 'smooth' });
  });

  /** Génère la liste de numéros de pages à afficher (avec ellipses). */
  function paginationRange(current, total) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages = [];
    pages.push(1);
    if (current > 3) pages.push('…');
    for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) pages.push(i);
    if (current < total - 2) pages.push('…');
    pages.push(total);
    return pages;
  }
}
