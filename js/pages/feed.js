// js/pages/feed.js
// Page /feed : liste dense des opportunités du moteur + toolbar (filtres/tri/recherche/favoris).
// Realtime : nouvelle opportunité insérée apparaît en tête. Favoris : C-1 (item_favorites).
import { supa } from '../supabase-client.js';
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import { listOpportunities, filterAndSort } from '../lib/opportunities.js';
import { opportunityRowHtml } from '../components/opportunity-row.js';
import { loadFavorites, toggleFavorite, isFav } from '../lib/item-favorites.js';
import { loadCommentMeta } from '../lib/comments.js';
import { isUnseen } from '../lib/comment-seen.js';
import { getHome, setHome, getRadius, setRadius, haversineKm } from '../lib/geo-home.js';

const CATS = [
  { key: 'all', label: 'Toutes' },
  { key: 'urgent', label: '🔴 Urgent' },
  { key: 'interesting', label: '🟡 Intéressant' },
  { key: 'passable', label: '⚫ Passable' },
];

export async function render() {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;

  const root = document.getElementById('appRoot');
  root.innerHTML = `
    <section class="feed-page">
      <h2>🔥 Bonnes affaires</h2>
      <p class="muted">Trouvées en continu par le moteur — les plus récentes en haut.</p>
      <div class="feed-toolbar">
        <div class="row">
          <input class="feed-search" id="feedSearch" placeholder="🔍 Rechercher un titre…">
          <select id="feedSort">
            <option value="recent">Plus récentes</option>
            <option value="score">Meilleur score</option>
            <option value="margin">Meilleure marge €</option>
          </select>
        </div>
        <div class="row" id="feedChips">
          ${CATS.map((c, i) => `<button type="button" class="feed-chip${i === 0 ? ' on' : ''}" data-cat="${c.key}">${c.label}</button>`).join('')}
          <button type="button" class="feed-chip" id="feedFav" data-fav-filter="off">⭐ Mes favoris</button>
          <span class="feed-count" id="feedCount">…</span>
        </div>
        <div class="row" id="feedGeo">
          <input class="feed-search" id="feedSecteur" placeholder="📍 Mon secteur (code postal ou ville)">
          <select id="feedRadius">
            <option value="all">Toute la France</option>
            <option value="5">≤ 5 km</option>
            <option value="10">≤ 10 km</option>
            <option value="25">≤ 25 km</option>
            <option value="50">≤ 50 km</option>
            <option value="100">≤ 100 km</option>
          </select>
          <span class="feed-geo-msg" id="feedGeoMsg"></span>
        </div>
      </div>
      <div id="feedList"></div>
      <div id="feedEmpty" class="empty-state card hidden"><h3>Aucune opportunité pour l'instant</h3>
        <p>Le moteur n'a encore rien remonté, ou aucune recherche n'est active.</p></div>
    </section>`;

  const state = { items: [], category: 'all', sort: 'recent', text: '', favOnly: false };

  const me = await getProfile();
  if (navState.token !== myToken) return;
  await loadFavorites(me?.id);
  if (navState.token !== myToken) return;

  let items;
  try { items = await listOpportunities(); }
  catch (err) {
    if (navState.token !== myToken) return;
    document.getElementById('feedList').innerHTML = `<div class="error-panel card">❌ ${err.message}</div>`;
    return;
  }
  if (navState.token !== myToken) return;
  state.items = items;

  let commentMeta = new Map();
  try { commentMeta = await loadCommentMeta(items.map(o => o.id), me?.id); } catch (_) {}
  if (navState.token !== myToken) return;

  renderList();

  // Toolbar events
  document.getElementById('feedSearch').addEventListener('input', e => { state.text = e.target.value.trim(); renderList(); });
  document.getElementById('feedSort').addEventListener('change', e => { state.sort = e.target.value; renderList(); });
  document.getElementById('feedChips').addEventListener('click', e => {
    const cat = e.target.closest('[data-cat]');
    if (!cat) return;
    state.category = cat.dataset.cat;
    document.querySelectorAll('#feedChips [data-cat]').forEach(b => b.classList.toggle('on', b === cat));
    renderList();
  });
  const favBtn = document.getElementById('feedFav');
  favBtn.addEventListener('click', () => {
    state.favOnly = !state.favOnly;
    favBtn.classList.toggle('on', state.favOnly);
    renderList();
  });

  // Secteur + rayon (proximité). État pré-rempli depuis localStorage.
  const secteurEl = document.getElementById('feedSecteur');
  const radiusEl = document.getElementById('feedRadius');
  const geoMsg = document.getElementById('feedGeoMsg');
  const home0 = getHome();
  if (home0) { secteurEl.value = home0.label; geoMsg.textContent = `📍 ${home0.label}`; }
  radiusEl.value = getRadius();
  secteurEl.addEventListener('change', async () => {
    const q = secteurEl.value.trim();
    if (!q) return;
    geoMsg.textContent = '⏳ Localisation…';
    try {
      const home = await setHome(q);
      geoMsg.textContent = `📍 ${home.label}`;
      renderList();
    } catch (err) {
      geoMsg.textContent = '❌ ' + err.message;
    }
  });
  radiusEl.addEventListener('change', () => { setRadius(radiusEl.value); renderList(); });

  // Délégation : clic sur l'étoile favori (sans naviguer)
  document.getElementById('feedList').addEventListener('click', async e => {
    const star = e.target.closest('.opp-star');
    if (!star) return;
    e.preventDefault(); e.stopPropagation();
    if (!me?.id || star.dataset.pending) return;
    const id = star.dataset.favId;
    const willFav = !isFav(id);
    star.dataset.pending = '1';
    star.classList.toggle('on', willFav);
    star.textContent = willFav ? '⭐' : '☆';
    try {
      await toggleFavorite(me.id, id);
      if (state.favOnly && !willFav) renderList();
    } catch (_) {
      star.classList.toggle('on', !willFav);
      star.textContent = !willFav ? '⭐' : '☆';
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
    const list = filterAndSort(state.items, { category: state.category, sort: state.sort, text: state.text });
    const grid = document.getElementById('feedList');
    const count = document.getElementById('feedCount');
    const empty = document.getElementById('feedEmpty');
    if (!grid || !count || !empty) return; // navigated away
    let finalList = state.favOnly ? list.filter(o => isFav(o.id)) : list;
    // Filtre proximité : si domicile défini ET rayon ≠ "Toute la France".
    const home = getHome();
    const radius = getRadius();
    if (home && radius !== 'all') {
      const rad = Number(radius);
      finalList = finalList.filter(o =>
        o.lat != null && o.lon != null && haversineKm(home.lat, home.lon, o.lat, o.lon) <= rad);
    }
    empty.classList.toggle('hidden', state.items.length > 0);
    grid.innerHTML = finalList.map(o => {
      const meta = commentMeta.get(o.id);
      const dist = (home && o.lat != null && o.lon != null)
        ? haversineKm(home.lat, home.lon, o.lat, o.lon) : null;
      return opportunityRowHtml(o, {
        isFav: isFav(o.id),
        commentCount: meta ? meta.count : 0,
        hasNewComments: !!(meta && meta.participated && isUnseen(o.id, meta.latest)),
        distanceKm: dist,
      });
    }).join('');
    count.textContent = `${finalList.length} opportunité${finalList.length > 1 ? 's' : ''}`;
  }
}
