# Phase C-1 — Feed + Page item + DA — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer la première version utilisable du site recentré sur les opportunités : un feed dense (`/feed`) avec filtres/tri/recherche/favoris, une page item (`/item/:id`) avec faits clés + analyse IA, et la nouvelle DA appliquée au shell — sans commentaires (C-2) ni watchlist UI (C-3).

**Architecture:** SPA Vanilla JS existante (router history-API, lazy routes, client Supabase SDK + RLS). On **construit à côté** : nouvelles routes `/feed` et `/item/:id` ajoutées, anciennes routes conservées mais retirées de la nav (nettoyage en C-5). Données lues depuis la table `opportunities` (déjà peuplée par le moteur ; RLS `opp_select_all` déjà OK). Favoris dans une nouvelle table `item_favorites`. Réutilise les patterns éprouvés : garde `navState.token`, `escapeHtml`, realtime `removeChannel`, toolbar/feed du `hub.js` actuel.

**Tech Stack:** Vanilla JS (ES6 modules), Supabase JS SDK v2 + Realtime, CSS pur (variables/DA), zéro build step. Migration SQL appliquée à la main dans Supabase.

**Vérification (convention projet) :** pas de tests frontend automatisés. Chaque tâche se valide en **E2E manuel** : lancer `python server.py`, ouvrir `http://localhost:8080/feed` connecté, vérifier rendu + console (F12) sans erreur. Backend : `python -m pytest tests/ -q` doit rester vert (116 tests) à chaque commit touchant autre chose que le frontend.

---

## Structure des fichiers

| Fichier | Responsabilité | Action |
|---|---|---|
| `supabase/migrations/2026-06-01-phase-c1-favorites.sql` | Table `item_favorites` + RLS | Créer (appliquer à la main) |
| `style.css` | Tokens DA + styles feed/item | Modifier (ajouts) |
| `js/lib/opportunities.js` | Accès données + filtre/tri pur | Créer |
| `js/lib/item-favorites.js` | Favoris item (charge set, toggle) | Créer |
| `js/components/opportunity-row.js` | HTML d'une ligne du feed | Créer |
| `js/pages/feed.js` | Page `/feed` (fetch, toolbar, rendu, realtime) | Créer |
| `js/pages/item.js` | Page `/item/:id` (faits + analyse IA) | Créer |
| `js/main.js` | Routes `/feed` + `/item/:id` | Modifier |
| `js/components/header.js` | Nav vers `/feed` (retrait Scraper du menu), logo → `/feed` | Modifier |
| `js/pages/login.js` | Redirection post-login vers `/feed` (au lieu de `/hub`) | Modifier |

---

## Task 1 : Migration `item_favorites`

**Files:**
- Create: `supabase/migrations/2026-06-01-phase-c1-favorites.sql`

- [ ] **Step 1 : Écrire la migration**

```sql
-- ============================================================================
-- 2026-06-01 — Phase C-1 / Favoris sur item (opportunité)
-- Remplace l'ancien favori-sur-recherche (table `favorites`, laissée en place).
-- Best practices Supabase : RLS (select auth.uid()) wrappé, index FK.
-- ============================================================================
create table if not exists public.item_favorites (
    user_id        uuid not null references public.profiles(id) on delete cascade,
    opportunity_id uuid not null references public.opportunities(id) on delete cascade,
    created_at     timestamptz not null default now(),
    primary key (user_id, opportunity_id)
);
create index if not exists item_favorites_user_idx on public.item_favorites (user_id);

alter table public.item_favorites enable row level security;

drop policy if exists "item_fav_select_own" on public.item_favorites;
create policy "item_fav_select_own" on public.item_favorites
    for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "item_fav_insert_own" on public.item_favorites;
create policy "item_fav_insert_own" on public.item_favorites
    for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists "item_fav_delete_own" on public.item_favorites;
create policy "item_fav_delete_own" on public.item_favorites
    for delete to authenticated using ((select auth.uid()) = user_id);
```

- [ ] **Step 2 : Appliquer à la main**

Dans Supabase → SQL Editor → coller le SQL ci-dessus → **Run**. Attendu : « Success. No rows returned ».

- [ ] **Step 3 : Vérifier**

Table Editor → la table `item_favorites` apparaît avec RLS activé (🔒). Pas de pytest (accès via SDK frontend uniquement).

- [ ] **Step 4 : Commit**

```bash
git add supabase/migrations/2026-06-01-phase-c1-favorites.sql
git commit -m "feat(db): table item_favorites + RLS (phase C-1)"
```

---

## Task 2 : Fondation DA dans `style.css`

**Files:**
- Modify: `style.css` (ajout d'un bloc en tête de la section variables + un bloc Phase C)

- [ ] **Step 1 : Ajouter/mettre à jour les variables DA**

Repérer le bloc `:root { … }` existant. Ajouter (ou aligner) ces variables à la fin du `:root` (ne pas supprimer les existantes — on superpose) :

```css
:root {
  /* ===== DA Phase C (prototype validé) ===== */
  --c-bg:#0a0f1d;
  --c-bg-glow:#16203a;
  --c-card:rgba(255,255,255,.035);
  --c-bd:rgba(255,255,255,.08);
  --c-txt:#e7ecf3;
  --c-mut:#94a3b8;
  --c-mut2:#64748b;
  --c-acc:#6366f1;
  --c-acc2:#818cf8;
  --c-cat-red:#f43f5e;  --c-cat-red-txt:#fb7185;
  --c-cat-yel:#facc15;
  --c-cat-grey:#94a3b8;
  --c-gain:#34d399;
  --c-lbc:#ff6e14;
}
```

- [ ] **Step 2 : Appliquer la DA au shell global**

Ajouter en fin de `style.css` :

```css
/* ===== DA Phase C — shell ===== */
body {
  font-family: 'Outfit', system-ui, 'Segoe UI', sans-serif;
  color: var(--c-txt);
  background: radial-gradient(1200px 600px at 70% -10%, var(--c-bg-glow) 0, var(--c-bg) 55%) fixed;
  min-height: 100vh;
}
#appHeader {
  position: sticky; top: 0; z-index: 20;
  background: rgba(10,15,29,.85);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--c-bd);
}
```

> Note : si `body`/`#appHeader` ont déjà des règles ailleurs, ces ajouts (placés en fin de fichier) gagnent par ordre de cascade. Vérifier visuellement qu'aucune page existante ne casse.

- [ ] **Step 3 : Vérifier (E2E manuel)**

Lancer `python server.py`. Ouvrir `http://localhost:8080/hub` connecté. Attendu : fond dégradé indigo, header en verre translucide, police Outfit. Les pages existantes restent lisibles (pas de texte invisible / contraste cassé). Console F12 sans erreur.

- [ ] **Step 4 : Commit**

```bash
git add style.css
git commit -m "feat(ui): fondation DA Phase C (tokens + shell glassmorphism)"
```

---

## Task 3 : Lib `opportunities.js` + composant `opportunity-row.js` + CSS feed

**Files:**
- Create: `js/lib/opportunities.js`
- Create: `js/components/opportunity-row.js`
- Modify: `style.css` (styles du feed)

- [ ] **Step 1 : Créer `js/lib/opportunities.js`**

```js
// js/lib/opportunities.js
// Accès aux opportunités (lecture seule côté membre, RLS opp_select_all).
// + helpers purs de filtre/tri (sans réseau).
import { supa } from '../supabase-client.js';

const SELECT = [
  'id', 'ad_id', 'title', 'price', 'url', 'image_url',
  'location_city', 'location_postal', 'category', 'resale_score',
  'est_market_price', 'est_margin_eur', 'est_margin_pct', 'max_buy_price',
  'price_dropped', 'previous_price', 'explanation', 'signals',
  'source_search_id', 'scraped_at', 'created_at', 'status',
].join(', ');

/** Liste les opportunités actives, plus récentes d'abord. */
export async function listOpportunities({ limit = 100 } = {}) {
  const { data, error } = await supa
    .from('opportunities')
    .select(SELECT)
    .eq('status', 'active')
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw new Error('Chargement des opportunités impossible : ' + error.message);
  return data || [];
}

/** Récupère une opportunité par id. */
export async function getOpportunity(id) {
  const { data, error } = await supa.from('opportunities').select(SELECT).eq('id', id).single();
  if (error) throw new Error('Opportunité introuvable : ' + error.message);
  return data;
}

/** Filtre + tri purs (testable, sans réseau). favSet = Set d'ids favoris. */
export function filterAndSort(items, {
  category = 'all', favOnly = false, favSet = new Set(),
  text = '', source = 'all', sort = 'recent',
} = {}) {
  let list = items.slice();
  if (category !== 'all') list = list.filter(o => o.category === category);
  if (source !== 'all') list = list.filter(o => o.source_search_id === source);
  if (favOnly) list = list.filter(o => favSet.has(o.id));
  if (text) {
    const t = text.toLowerCase();
    list = list.filter(o => (o.title || '').toLowerCase().includes(t));
  }
  switch (sort) {
    case 'score':  list.sort((a, b) => (b.resale_score || 0) - (a.resale_score || 0)); break;
    case 'margin': list.sort((a, b) => (b.est_margin_eur || 0) - (a.est_margin_eur || 0)); break;
    default:       list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }
  return list;
}
```

- [ ] **Step 2 : Créer `js/components/opportunity-row.js`**

```js
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

export function opportunityRowHtml(o, { isFav = false } = {}) {
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
        <span class="opp-meta">${o.location_city ? `📍 ${esc(o.location_city)}` : ''}</span>
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
```

> Note : le compteur 💬 commentaires sera ajouté en C-2 (table `item_comments` absente en C-1).

- [ ] **Step 3 : Ajouter les styles feed dans `style.css`**

```css
/* ===== DA Phase C — feed ===== */
.feed-page { max-width: 920px; margin: 0 auto; padding: 22px; }
.feed-toolbar { background: var(--c-card); border: 1px solid var(--c-bd); border-radius: 14px;
  padding: 12px 14px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 10px; }
.feed-toolbar .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.feed-search { flex: 1; min-width: 160px; background: rgba(255,255,255,.05);
  border: 1px solid var(--c-bd); border-radius: 9px; padding: 9px 12px; color: var(--c-txt); }
.feed-chip { padding: 6px 12px; border-radius: 999px; border: 1px solid var(--c-bd);
  background: transparent; color: var(--c-mut); font-weight: 600; font-size: .82rem; cursor: pointer; }
.feed-chip.on { background: rgba(99,102,241,.16); color: var(--c-acc2); border-color: rgba(99,102,241,.4); }
.feed-count { color: var(--c-mut2); font-size: .8rem; margin-left: auto; }
.opp-row { display: flex; align-items: center; gap: 12px; background: var(--c-card);
  border: 1px solid var(--c-bd); border-radius: 12px; padding: 11px 13px; margin-bottom: 9px;
  cursor: pointer; transition: .12s; text-decoration: none; color: inherit; }
.opp-row:hover { background: rgba(255,255,255,.06); transform: translateY(-1px);
  border-color: rgba(99,102,241,.35); }
.opp-stripe { width: 5px; align-self: stretch; border-radius: 5px; flex-shrink: 0; }
.opp-thumb { width: 50px; height: 50px; border-radius: 9px; background: linear-gradient(135deg,#1e293b,#0f172a);
  display: flex; align-items: center; justify-content: center; color: #475569; flex-shrink: 0; overflow: hidden; }
.opp-thumb img { width: 100%; height: 100%; object-fit: cover; }
.opp-main { flex: 1; min-width: 0; }
.opp-title { font-weight: 700; color: #f1f5f9; }
.opp-badge { font-size: .7rem; font-weight: 800; padding: 2px 9px; border-radius: 999px; white-space: nowrap; }
.cat-red { background: rgba(244,63,94,.18); color: var(--c-cat-red-txt); }
.cat-yel { background: rgba(250,204,21,.15); color: var(--c-cat-yel); }
.cat-grey { background: rgba(148,163,184,.16); color: #cbd5e1; }
.opp-meta { color: var(--c-mut); font-size: .78rem; display: block; }
.opp-pricecol { text-align: right; flex-shrink: 0; }
.opp-price { font-size: 1.2rem; font-weight: 800; }
.opp-old { color: var(--c-mut2); text-decoration: line-through; font-size: .82rem; margin-left: 6px; }
.opp-margin { color: var(--c-gain); font-weight: 700; font-size: .82rem; display: block; }
.opp-star { background: none; border: none; font-size: 1.1rem; color: var(--c-mut2); cursor: pointer; flex-shrink: 0; }
.opp-star.on { color: var(--c-cat-yel); }
```

- [ ] **Step 4 : Vérifier (syntaxe)**

```bash
node --check js/lib/opportunities.js && node --check js/components/opportunity-row.js && echo OK
```
Attendu : `OK`.

- [ ] **Step 5 : Commit**

```bash
git add js/lib/opportunities.js js/components/opportunity-row.js style.css
git commit -m "feat(feed): lib opportunities + composant ligne + styles (phase C-1)"
```

---

## Task 4 : Page `/feed` + route + nav + redirection login

**Files:**
- Create: `js/pages/feed.js`
- Modify: `js/main.js` (route `/feed`)
- Modify: `js/components/header.js` (nav → `/feed`)
- Modify: `js/pages/login.js` (redirection post-login)

- [ ] **Step 1 : Créer `js/pages/feed.js`**

```js
// js/pages/feed.js
// Page /feed : liste dense des opportunités du moteur + toolbar (filtres/tri/recherche/favoris).
// Realtime : nouvelle opportunité insérée apparaît en tête. Favoris : C-1 (item_favorites).
import { supa } from '../supabase-client.js';
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import { listOpportunities, filterAndSort } from '../lib/opportunities.js';
import { opportunityRowHtml } from '../components/opportunity-row.js';
import { loadFavorites, toggleFavorite, isFav } from '../lib/item-favorites.js';

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
    const list = filterAndSort(state.items, { ...state, favSet: undefined, favOnly: state.favOnly });
    const grid = document.getElementById('feedList');
    const count = document.getElementById('feedCount');
    const empty = document.getElementById('feedEmpty');
    if (!grid || !count || !empty) return; // navigated away
    // favOnly s'appuie sur isFav() (Set chargé), donc on refiltre ici si besoin
    const finalList = state.favOnly ? list.filter(o => isFav(o.id)) : list;
    empty.classList.toggle('hidden', state.items.length > 0);
    grid.innerHTML = finalList.map(o => opportunityRowHtml(o, { isFav: isFav(o.id) })).join('');
    count.textContent = `${finalList.length} opportunité${finalList.length > 1 ? 's' : ''}`;
  }
}
```

> Note : `filterAndSort` ne connaît pas `isFav` ; on passe `favOnly:false` au helper pur et on applique le filtre favoris dans `renderList` via `isFav()`. (Le paramètre `favSet` du helper sert si on veut filtrer hors composant ; ici on garde le Set dans la lib.)

- [ ] **Step 2 : Ajouter la route dans `js/main.js`**

Après la ligne `route('/hub', …)`, ajouter :

```js
route('/feed',              () => import('./pages/feed.js').then(m => m.render()));
```

- [ ] **Step 3 : Nav vers `/feed` dans `js/components/header.js`**

Dans `renderHeader`, remplacer le bloc `<nav class="header-nav"> … </nav>` (cas connecté) par une nav pointant sur `/feed`. Remplacer la ligne du logo `<a href="/hub" data-link class="logo-link">` par `<a href="/feed" data-link class="logo-link">`. Et remplacer les `navLink` par :

```js
            ${navLink('/feed',      '🔥', 'Feed')}
            ${navLink('/dashboard', '📊', 'Dashboard')}
            ${profile?.role === 'admin' ? navLink('/admin', '🛠️', 'Admin') : ''}
```

(Retirer les liens `/hub` et `/scraper` de la nav — les routes restent dans `main.js`, seul l'accès visuel disparaît.)

- [ ] **Step 4 : Redirection post-login vers `/feed`**

Dans `js/pages/login.js`, repérer la/les redirection(s) `navigate('/hub')` (après login réussi et/ou si déjà connecté) et remplacer par `navigate('/feed')`.

- [ ] **Step 5 : Vérifier (syntaxe + E2E)**

```bash
node --check js/pages/feed.js && echo OK
```
Puis `python server.py`, ouvrir `http://localhost:8080/` → après login, atterrissage sur `/feed`. Attendu : la liste des **vraies** opportunités (issues du run Phase B) s'affiche, avec badges catégorie, prix, marge. Tester : filtre catégorie, tri, recherche texte. Console F12 sans erreur.

- [ ] **Step 6 : Commit**

```bash
git add js/pages/feed.js js/main.js js/components/header.js js/pages/login.js
git commit -m "feat(feed): page /feed (liste + filtres + tri + recherche) + nav + redirect login (phase C-1)"
```

---

## Task 5 : Lib `item-favorites.js` (favoris fonctionnels)

**Files:**
- Create: `js/lib/item-favorites.js`

> Cette lib est importée par `feed.js` (Task 4) ; on l'écrit ici comme unité isolée. Elle doit exister avant de tester le feed en entier — si exécution séquentielle stricte, écrire ce fichier AVANT le Step 5 de la Task 4.

- [ ] **Step 1 : Créer `js/lib/item-favorites.js`**

```js
// js/lib/item-favorites.js
// Favoris sur opportunité (table item_favorites). Set en mémoire, mises à jour optimistes.
import { supa } from '../supabase-client.js';

let favSet = new Set();

export function isFav(id) { return favSet.has(id); }
export function favorites() { return favSet; }

/** Charge les favoris du user courant dans le Set mémoire. */
export async function loadFavorites(userId) {
  favSet = new Set();
  if (!userId) return favSet;
  const { data, error } = await supa
    .from('item_favorites').select('opportunity_id').eq('user_id', userId);
  if (!error && data) favSet = new Set(data.map(r => r.opportunity_id));
  return favSet;
}

/** Bascule un favori (optimiste, rollback si la DB échoue). */
export async function toggleFavorite(userId, oppId) {
  if (!userId) throw new Error('Non authentifié.');
  if (favSet.has(oppId)) {
    favSet.delete(oppId);
    const { error } = await supa.from('item_favorites')
      .delete().eq('user_id', userId).eq('opportunity_id', oppId);
    if (error) { favSet.add(oppId); throw error; }
  } else {
    favSet.add(oppId);
    const { error } = await supa.from('item_favorites')
      .insert({ user_id: userId, opportunity_id: oppId });
    if (error) { favSet.delete(oppId); throw error; }
  }
}
```

- [ ] **Step 2 : Vérifier (syntaxe)**

```bash
node --check js/lib/item-favorites.js && echo OK
```

- [ ] **Step 3 : Vérifier (E2E favoris)**

Recharger `/feed` (migration Task 1 appliquée). Cliquer l'étoile ☆ d'une ligne → passe à ⭐ sans naviguer. Cliquer le chip « ⭐ Mes favoris » → ne montre que les favoris. Recharger la page (F5) → le favori persiste. Console sans erreur.

- [ ] **Step 4 : Commit**

```bash
git add js/lib/item-favorites.js
git commit -m "feat(feed): favoris item (item-favorites lib) (phase C-1)"
```

---

## Task 6 : Page `/item/:id` (détail + analyse IA)

**Files:**
- Create: `js/pages/item.js`
- Modify: `js/main.js` (route `/item/:id`)
- Modify: `style.css` (styles page item)

- [ ] **Step 1 : Créer `js/pages/item.js`**

```js
// js/pages/item.js
// Page /item/:id : faits clés d'une opportunité + analyse IA. Commentaires = C-2.
import { requireAuth } from '../auth.js';
import { navState } from '../router.js';
import { getOpportunity } from '../lib/opportunities.js';

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
    <div class="item-comments-placeholder card muted">💬 Les commentaires arrivent bientôt (sous-phase C-2).</div>`;
}
```

- [ ] **Step 2 : Ajouter la route dans `js/main.js`**

Après la route `/feed`, ajouter :

```js
route('/item/:id',          (p) => import('./pages/item.js').then(m => m.render(p)));
```

- [ ] **Step 3 : Ajouter les styles item dans `style.css`**

```css
/* ===== DA Phase C — page item ===== */
.item-page { max-width: 820px; margin: 0 auto; padding: 22px; }
.item-back { color: var(--c-mut); font-size: .9rem; display: inline-block; margin-bottom: 14px; }
.item-head { display: flex; gap: 16px; flex-wrap: wrap; padding: 16px; }
.item-photo { flex: 1; min-width: 220px; min-height: 200px; border-radius: 11px; overflow: hidden;
  background: linear-gradient(135deg,#1e293b,#0f172a); display: flex; align-items: center; justify-content: center; color: #475569; font-size: 2rem; }
.item-photo img { width: 100%; height: 100%; object-fit: cover; }
.item-facts { flex: 1.3; min-width: 240px; display: flex; flex-direction: column; gap: 9px; }
.item-price { font-size: 1.8rem; font-weight: 800; }
.item-stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 4px; }
.stat-box { background: rgba(255,255,255,.04); border-radius: 9px; padding: 9px 11px; }
.stat-label { color: var(--c-mut); font-size: .66rem; text-transform: uppercase; letter-spacing: .04em; }
.stat-val { color: #f1f5f9; font-weight: 800; font-size: 1.05rem; }
.item-gain { color: var(--c-gain); }
.btn-lbc { background: var(--c-lbc); color: #fff; font-weight: 700; padding: 10px 15px;
  border-radius: 9px; display: inline-block; width: max-content; margin-top: 6px; }
.item-ai { background: rgba(99,102,241,.08); border: 1px solid rgba(99,102,241,.22);
  border-radius: 11px; padding: 13px; margin: 14px 0; color: #cbd5e1; font-size: .9rem; }
.item-ai-label { color: var(--c-acc2); font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 4px; }
.item-comments-placeholder { padding: 14px; text-align: center; margin-top: 14px; }
```

- [ ] **Step 4 : Vérifier (syntaxe + E2E)**

```bash
node --check js/pages/item.js && echo OK
```
Puis sur `/feed`, cliquer une ligne → arrive sur `/item/:id`. Attendu : photo (ou 📷), badge catégorie, prix, prix marché/marge/prix max, bouton Leboncoin (ouvre l'annonce), analyse IA. Le bouton « ← Retour au feed » revient au feed. Console sans erreur.

- [ ] **Step 5 : Commit**

```bash
git add js/pages/item.js js/main.js style.css
git commit -m "feat(item): page /item/:id (faits + analyse IA) (phase C-1)"
```

---

## Task 7 : Vérification E2E C-1 + non-régression

**Files:** aucun (vérification)

- [ ] **Step 1 : Non-régression backend**

```bash
python -m pytest tests/ -q
```
Attendu : `116 passed` (aucune modif moteur — doit rester vert).

- [ ] **Step 2 : E2E complet (navigateur connecté)**

Lancer `python server.py`, ouvrir `http://localhost:8080/`. Dérouler :
1. Login → atterrissage `/feed`.
2. Feed : liste des opportunités réelles, badges/prix/marge corrects.
3. Filtres : catégorie (🔴/🟡/⚫/Toutes), tri (récent/score/marge), recherche texte → la liste réagit.
4. Favori ⭐ : toggle sans navigation, filtre « Mes favoris », persistance après F5.
5. Clic sur une ligne → page item : tous les champs réels, bouton Leboncoin OK, analyse IA affichée, retour feed OK.
6. Nav : header montre 🔥 Feed / 📊 Dashboard (+ 🛠️ Admin si admin), logo → feed. Dashboard s'ouvre toujours (non-régression).
7. DA : fond dégradé indigo, header glassmorphism, police Outfit, cartes arrondies — sur feed, item ET dashboard.
8. Console F12 : aucune erreur rouge sur tout le parcours.

- [ ] **Step 3 : Commit de clôture (si ajustements)**

```bash
git add -A
git commit -m "chore(phase-c1): vérification E2E feed + item + DA OK"
```

---

## Self-review (couverture spec C-1)

- Feed dense + filtres catégorie + tri (récent/score/marge) + recherche texte + favoris → Tasks 3,4,5 ✅
- Filtre par source : helper `filterAndSort` gère `source`, mais l'UI de sélection de source n'est pas branchée en C-1 (pas de page watchlist encore pour lister les sources). → **Décision : filtre source reporté en C-3** (quand la watchlist fournira la liste des recherches). Noté ici pour ne pas l'oublier.
- Page item (faits + analyse IA, sans commentaires) → Task 6 ✅
- DA site-wide (shell) → Task 2 ✅ ; re-skin fin des pages existantes (dashboard/admin/login/profil) = polish progressif, à compléter au fil des sous-phases.
- Migration item_favorites → Task 1 ✅
- Routes/nav/redirect, anciennes routes conservées hors-nav → Task 4 ✅
- Non-régression backend → Task 7 ✅
