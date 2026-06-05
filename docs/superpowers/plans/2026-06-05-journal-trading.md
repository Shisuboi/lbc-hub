# Journal de trading (groupe) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le dashboard privé par un Journal de trading partagé (table `trades`, Kanban Contacté→Acheté→Revendu, modal adaptatif, liaison au feed, KPIs groupe, animation d'entrée « colonnes »).

**Architecture:** Nouvelle table Supabase `trades` (RLS : lecture partagée, écriture auteur/admin). Couche d'accès `js/lib/trades.js` (CRUD + recherche feed + calculs purs). Page `/dashboard` réécrite en Journal. Bouton « Ajouter au journal » sur `/item/:id` via relais `sessionStorage`. Onglet nav renommé « Journal ».

**Tech Stack:** Vanilla JS ES6, Supabase SDK v2, Chart.js (lazy-load CDN existant). **Pas de tests frontend** (Node absent) → validation manuelle : chargement page + console F12. Serveur dev = `python server.py`.

**Spec:** `docs/superpowers/specs/2026-06-05-journal-trading-design.md`

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `supabase/migrations/2026-06-05-trades.sql` | Créer | Table `trades` + RLS + trigger updated_at |
| `js/lib/trades.js` | Créer | CRUD + `searchOpportunities` + `computeGroupKpis` + `buildMonthlySeries` |
| `js/lib/icons.js` | Modifier | Ajouter l'icône `book` |
| `js/components/header.js` | Modifier | Onglet « Journal » (icône `book`) |
| `js/pages/item.js` | Modifier | Bouton « ➕ Ajouter au journal » + relais `sessionStorage` |
| `js/pages/dashboard.js` | Réécrire | Page Journal (héro + KPIs + graphes + Kanban + modal + anim C) |
| `style.css` | Modifier | Kanban, cartes deal, recherche feed, animation d'entrée C |

---

## Task 1 : Migration SQL `trades`

**Files:**
- Create: `supabase/migrations/2026-06-05-trades.sql`

- [ ] **Step 1 : Créer le fichier de migration**

```sql
-- ============================================================================
-- 2026-06-05 — Journal de trading PARTAGÉ (remplace le dashboard privé).
-- Un deal = un cycle Contacté → Acheté → Revendu. Lecture par tout le groupe,
-- écriture réservée à l'auteur ou à un admin.
-- ============================================================================

create table if not exists public.trades (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users(id) on delete cascade,
    opportunity_id  uuid references public.opportunities(id) on delete set null,
    title           text not null check (char_length(title) between 1 and 200),
    status          text not null default 'contacted'
                       check (status in ('contacted', 'bought', 'sold')),
    buy_price       numeric(10,2) check (buy_price is null or buy_price >= 0),
    sell_price      numeric(10,2) check (sell_price is null or sell_price >= 0),
    bought_at       date,
    sold_at         date,
    notes           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists trades_user_id_idx       on public.trades (user_id);
create index if not exists trades_opportunity_id_idx on public.trades (opportunity_id);
create index if not exists trades_updated_idx        on public.trades (updated_at desc);

alter table public.trades enable row level security;

drop policy if exists "trades_select_all" on public.trades;
create policy "trades_select_all" on public.trades
    for select to authenticated using (true);

drop policy if exists "trades_insert_own" on public.trades;
create policy "trades_insert_own" on public.trades
    for insert to authenticated
    with check ((select auth.uid()) = user_id);

drop policy if exists "trades_update_own_or_admin" on public.trades;
create policy "trades_update_own_or_admin" on public.trades
    for update to authenticated
    using (
        (select auth.uid()) = user_id
        or exists (select 1 from public.profiles p
                   where p.id = (select auth.uid()) and p.role = 'admin')
    );

drop policy if exists "trades_delete_own_or_admin" on public.trades;
create policy "trades_delete_own_or_admin" on public.trades
    for delete to authenticated
    using (
        (select auth.uid()) = user_id
        or exists (select 1 from public.profiles p
                   where p.id = (select auth.uid()) and p.role = 'admin')
    );

create or replace function public.touch_trades_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists trg_trades_touch on public.trades;
create trigger trg_trades_touch before update on public.trades
    for each row execute function public.touch_trades_updated_at();
```

- [ ] **Step 2 : Appliquer la migration manuellement**

Dashboard Supabase → **SQL Editor** → coller le fichier → **Run**.
Vérifier dans **Table Editor** que `trades` existe avec ses colonnes, et dans **Database →
Policies** que les 4 policies sont présentes.

- [ ] **Step 3 : Commit**

```bash
git add supabase/migrations/2026-06-05-trades.sql
git commit -m "feat(db): table trades partagee (Journal de trading) + RLS + trigger"
```

---

## Task 2 : `js/lib/trades.js`

**Files:**
- Create: `js/lib/trades.js`

- [ ] **Step 1 : Créer le module complet**

```javascript
// js/lib/trades.js
// Couche d'accès au Journal de trading PARTAGÉ (table trades).
// Lecture : tous les membres. Écriture : auteur ou admin (garanti par la RLS).
// L'auteur est joint depuis profiles (username, avatar_color).
import { supa, getCachedSession } from '../supabase-client.js';

const SELECT =
  'id, user_id, opportunity_id, title, status, buy_price, sell_price, ' +
  'bought_at, sold_at, notes, created_at, updated_at, ' +
  'author:profiles(username, avatar_color)';

/** Tous les deals du groupe, du plus récemment modifié au plus ancien. */
export async function listTrades() {
  const { data, error } = await supa
    .from('trades')
    .select(SELECT)
    .order('updated_at', { ascending: false });
  if (error) throw new Error('Chargement du journal impossible : ' + error.message);
  return data || [];
}

// Construit la ligne à écrire à partir des champs du formulaire (normalise les null).
function buildRow(input) {
  const status = input.status || 'contacted';
  const num = v => (v === '' || v == null || isNaN(Number(v))) ? null : Number(v);
  return {
    title: String(input.title || '').trim().slice(0, 200),
    status,
    opportunity_id: input.opportunity_id || null,
    buy_price: status === 'contacted' ? null : num(input.buy_price),
    sell_price: status === 'sold' ? num(input.sell_price) : null,
    bought_at: status === 'contacted' ? null : (input.bought_at || null),
    sold_at: status === 'sold' ? (input.sold_at || null) : null,
    notes: input.notes?.trim() || null,
  };
}

/** Crée un deal (user_id = moi). Renvoie la ligne créée (avec auteur). */
export async function createTrade(input) {
  const session = await getCachedSession();
  const user = session?.user;
  if (!user) throw new Error('Non authentifié. Reconnecte-toi.');
  const row = { user_id: user.id, ...buildRow(input) };
  const { data, error } = await supa.from('trades').insert(row).select(SELECT).single();
  if (error) throw new Error('Création impossible : ' + error.message);
  return data;
}

/** Met à jour un deal (RLS : auteur ou admin). */
export async function updateTrade(id, input) {
  const { data, error } = await supa
    .from('trades').update(buildRow(input)).eq('id', id).select(SELECT).single();
  if (error) throw new Error('Mise à jour impossible : ' + error.message);
  return data;
}

/** Supprime un deal (RLS : auteur ou admin). */
export async function deleteTrade(id) {
  const { error } = await supa.from('trades').delete().eq('id', id);
  if (error) throw new Error('Suppression impossible : ' + error.message);
}

/** Recherche d'opportunités du feed pour lier un deal. Best-effort (renvoie [] si erreur). */
export async function searchOpportunities(query) {
  const q = (query || '').trim();
  if (q.length < 2) return [];
  const { data, error } = await supa
    .from('opportunities')
    .select('id, title, price, category')
    .ilike('title', `%${q}%`)
    .order('created_at', { ascending: false })
    .limit(8);
  if (error || !data) return [];
  return data;
}

/** KPIs du groupe — profit RÉALISÉ (deals revendus uniquement). */
export function computeGroupKpis(trades) {
  let invested = 0, earned = 0, contacted = 0, bought = 0, sold = 0;
  for (const t of trades) {
    if (t.status === 'contacted') contacted++;
    else if (t.status === 'bought') bought++;
    else if (t.status === 'sold') {
      sold++;
      invested += Number(t.buy_price || 0);
      earned += Number(t.sell_price || 0);
    }
  }
  const profit = earned - invested;
  const roi = invested > 0 ? (profit / invested) * 100 : null;
  return { invested, earned, profit, roi, counts: { contacted, bought, sold } };
}

const MONTH_FR = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
  'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

/** Clé 'YYYY-MM' d'une date ISO. */
function monthKey(iso) { return iso ? iso.slice(0, 7) : null; }

/** Libellé court d'une clé mensuelle 'YYYY-MM' → "janv. 25". */
export function formatMonthLabel(key) {
  const [y, m] = key.split('-');
  return `${MONTH_FR[Number(m) - 1]} ${y.slice(2)}`;
}

/** Séries mensuelles pour les graphes : cumul achats/ventes + profit mensuel réalisé. */
export function buildMonthlySeries(trades) {
  const buysByMonth = new Map(), sellsByMonth = new Map();
  for (const t of trades) {
    if (t.buy_price != null && t.bought_at) {
      const k = monthKey(t.bought_at);
      buysByMonth.set(k, (buysByMonth.get(k) || 0) + Number(t.buy_price));
    }
    if (t.status === 'sold' && t.sell_price != null && t.sold_at) {
      const k = monthKey(t.sold_at);
      sellsByMonth.set(k, (sellsByMonth.get(k) || 0) + Number(t.sell_price));
    }
  }
  const labels = [...new Set([...buysByMonth.keys(), ...sellsByMonth.keys()])].sort();
  let cb = 0, cs = 0;
  const buysCumul = [], sellsCumul = [], profitMonthly = [];
  for (const k of labels) {
    const b = buysByMonth.get(k) || 0, s = sellsByMonth.get(k) || 0;
    cb += b; cs += s;
    buysCumul.push(cb); sellsCumul.push(cs); profitMonthly.push(s - b);
  }
  return { labels, buysCumul, sellsCumul, profitMonthly };
}
```

- [ ] **Step 2 : Vérifier (console F12, serveur lancé + connecté)**

```js
const m = await import('/js/lib/trades.js?v=' + Date.now());
console.log(typeof m.listTrades, typeof m.computeGroupKpis, typeof m.searchOpportunities);
// "function function function"
console.log(m.computeGroupKpis([
  { status:'sold', buy_price:80, sell_price:150 },
  { status:'bought', buy_price:50 },
  { status:'contacted' },
]));
// { invested:80, earned:150, profit:70, roi:87.5, counts:{contacted:1,bought:1,sold:1} }
console.log(await m.listTrades()); // [] ou la liste (pas d'erreur)
```

- [ ] **Step 3 : Commit**

```bash
git add js/lib/trades.js
git commit -m "feat(journal): lib trades — CRUD partage + recherche feed + KPIs groupe"
```

---

## Task 3 : Onglet « Journal » + icône `book`

**Files:**
- Modify: `js/lib/icons.js`
- Modify: `js/components/header.js`

- [ ] **Step 1 : Ajouter l'icône `book` dans `js/lib/icons.js`**

Repère la ligne de l'icône `chart:` et ajoute juste après :

```javascript
  book:    '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M19 3v18"/>',
```

> Les icônes du projet sont des fragments de `<path>` rendus dans un `<svg>` stroke
> `currentColor` par la fonction `icon()`. Ce livre minimaliste suit ce format.

- [ ] **Step 2 : Renommer l'onglet dans `js/components/header.js`**

Remplace la ligne du dock :

```javascript
    { href: '/dashboard', ic: 'chart',   label: 'Dashboard' },
```

par :

```javascript
    { href: '/dashboard', ic: 'book',    label: 'Journal' },
```

- [ ] **Step 3 : Vérifier (page)**

Serveur lancé, connecté : l'onglet du dock affiche « Journal » avec une icône livre. Console F12 propre.

- [ ] **Step 4 : Commit**

```bash
git add js/lib/icons.js js/components/header.js
git commit -m "feat(journal): onglet nav 'Journal' + icone book"
```

---

## Task 4 : Bouton « Ajouter au journal » sur `/item/:id`

**Files:**
- Modify: `js/pages/item.js`

- [ ] **Step 1 : Ajouter le bouton sous le lien Leboncoin**

Dans `js/pages/item.js`, repère la ligne du bouton LBC :

```javascript
        ${o.url ? `<a href="${esc(o.url)}" target="_blank" rel="noopener noreferrer" class="btn-lbc">Voir l'annonce sur Leboncoin ↗</a>` : ''}
```

Ajoute juste après (toujours dans le même bloc `<div class="item-hero-panel">`) :

```javascript
        <button type="button" id="itemAddJournal" class="btn-journal">＋ Ajouter au journal</button>
```

- [ ] **Step 2 : Brancher le clic → relais `sessionStorage` + navigation**

Repère, en bas de `render()`, le bloc qui monte les commentaires :

```javascript
  const commentsEl = document.getElementById('itemComments');
  if (commentsEl && navState.token === myToken) {
    mountComments(commentsEl, { opportunityId: o.id, me });
  }
}
```

Ajoute, juste avant la fermeture `}` de `render()` (après le bloc commentaires) :

```javascript
  const addBtn = document.getElementById('itemAddJournal');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      try {
        sessionStorage.setItem('journal-prefill', JSON.stringify({
          opportunity_id: o.id, title: o.title || '',
        }));
      } catch (_) {}
      location.assign('/dashboard');   // le router SPA prend le relais ; le Journal lit le prefill
    });
  }
```

> `location.assign('/dashboard')` déclenche le routing. En prod (préfixe `/lbc-hub`), le
> router strippe le préfixe ; utiliser un chemin absolu `/dashboard` est cohérent avec les
> autres `data-link` du projet. Le Journal détecte `sessionStorage 'journal-prefill'` au montage.

- [ ] **Step 3 : Vérifier (page)**

Sur `/item/:id`, le bouton « ＋ Ajouter au journal » apparaît sous le lien LBC. Le clic
navigue vers `/dashboard`. (Le pré-remplissage du modal sera vérifié après Task 5.)

- [ ] **Step 4 : Commit**

```bash
git add js/pages/item.js
git commit -m "feat(journal): bouton 'Ajouter au journal' sur /item/:id (relais sessionStorage)"
```

---

## Task 5 : Page `/dashboard` réécrite en Journal

**Files:**
- Modify: `js/pages/dashboard.js` (réécriture complète)

> Gros morceau. On remplace tout le contenu du fichier. Code complet ci-dessous.

- [ ] **Step 1 : Remplacer l'intégralité de `js/pages/dashboard.js`**

```javascript
// js/pages/dashboard.js
// Page /dashboard = JOURNAL DE TRADING PARTAGÉ.
// Héro (profit groupe) + KPIs + 2 graphiques + Kanban 3 colonnes (Contacté/Acheté/Revendu)
// + modal CRUD adaptatif au statut + recherche/liaison d'une annonce du feed.
// Données partagées (RLS) : tout le groupe voit tous les deals ; écriture auteur/admin.
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import {
  listTrades, createTrade, updateTrade, deleteTrade, searchOpportunities,
  computeGroupKpis, buildMonthlySeries, formatMonthLabel,
} from '../lib/trades.js';

// ── Lazy-load Chart.js (chargé une fois, à la demande) ───────────────────────
const CHARTJS_CDN = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js';
let chartJsPromise = null;
function loadChartJs() {
  if (window.Chart) return Promise.resolve(window.Chart);
  if (chartJsPromise) return chartJsPromise;
  chartJsPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = CHARTJS_CDN; s.async = true;
    s.onload = () => resolve(window.Chart);
    s.onerror = () => { chartJsPromise = null; reject(new Error('CDN Chart.js injoignable')); };
    document.head.appendChild(s);
  });
  return chartJsPromise;
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const eur = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
const eur2 = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', minimumFractionDigits: 0, maximumFractionDigits: 2 });
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function fmtDate(d) {
  if (!d) return '';
  return new Date(d + 'T00:00:00').toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
}
const STATUS = {
  contacted: { label: '🤝 Contacté', col: 'Contactés', icon: '🤝' },
  bought:    { label: '🛒 Acheté',   col: 'Achetés',   icon: '🛒' },
  sold:      { label: '✅ Revendu',  col: 'Revendus',  icon: '✅' },
};
const CAT_DOT = { urgent: '🔴', interesting: '🟡', passable: '⚫' };
function avatar(t) {
  const name = t.author?.username || '?';
  const color = t.author?.avatar_color || 'var(--accent)';
  return `<span class="jr-avatar" style="background:${esc(color)}">${esc(name[0].toUpperCase())}</span>`;
}

export async function render() {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;
  const me = await getProfile();
  if (navState.token !== myToken) return;
  const isAdmin = me?.role === 'admin';

  const root = document.getElementById('appRoot');
  root.innerHTML = `
    <section class="journal-page journal-enter">
      <div class="dash-hero liquid">
        <div class="dash-hero-main">
          <p class="feed-eyebrow">Journal · revente groupe</p>
          <h2 class="dash-title">Profit net du groupe</h2>
          <div class="dash-hero-figure" id="jrHeroProfit">—</div>
          <div class="dash-hero-sub" id="jrHeroSub">Suivez vos deals de A à Z, ensemble.</div>
        </div>
        <button type="button" class="btn btn-primary dash-add-btn" id="jrAddBtn">
          <span aria-hidden="true">＋</span> Ajouter un deal
        </button>
      </div>

      <div class="dash-kpis" id="jrKpis"></div>

      <div class="dash-charts" id="jrCharts">
        <div class="card dash-chart-card">
          <div class="dash-chart-head"><h3>Achats vs ventes <span class="dash-chart-sub">cumul mensuel</span></h3></div>
          <div class="dash-chart-canvas-wrap"><canvas id="jrLineChart" role="img" aria-label="Cumul achats/ventes"></canvas></div>
        </div>
        <div class="card dash-chart-card">
          <div class="dash-chart-head"><h3>Profit net <span class="dash-chart-sub">par mois</span></h3></div>
          <div class="dash-chart-canvas-wrap"><canvas id="jrBarChart" role="img" aria-label="Profit net mensuel"></canvas></div>
        </div>
      </div>

      <div class="jr-board" id="jrBoard">
        <div class="jr-col" data-status="contacted"><div class="jr-col-head">🤝 Contactés <span class="jr-col-count" id="jrCount-contacted"></span></div><div class="jr-col-body" id="jrColBody-contacted"></div></div>
        <div class="jr-col" data-status="bought"><div class="jr-col-head">🛒 Achetés <span class="jr-col-count" id="jrCount-bought"></span></div><div class="jr-col-body" id="jrColBody-bought"></div></div>
        <div class="jr-col" data-status="sold"><div class="jr-col-head">✅ Revendus <span class="jr-col-count" id="jrCount-sold"></span></div><div class="jr-col-body" id="jrColBody-sold"></div></div>
      </div>

      <div class="dash-empty empty-state card hidden" id="jrEmpty">
        <div class="empty-icon" aria-hidden="true">📓</div>
        <h3>Le journal est vide</h3>
        <p>Ajoute ton premier deal — ou lance-toi depuis une annonce du feed avec « Ajouter au journal ».</p>
        <button type="button" class="btn btn-primary" id="jrEmptyAddBtn" style="width:auto"><span aria-hidden="true">＋</span> Ajouter un deal</button>
      </div>
    </section>

    <div class="modal-overlay hidden" id="jrModal">
      <div class="modal-card card" role="dialog" aria-modal="true" aria-labelledby="jrModalTitle">
        <div class="modal-header">
          <div class="modal-title-area"><span class="modal-icon" aria-hidden="true">📓</span><h2 id="jrModalTitle">Nouveau deal</h2></div>
          <button type="button" class="modal-close" id="jrModalClose" aria-label="Fermer">✕</button>
        </div>
        <form class="modal-body dash-form" id="jrForm">
          <input type="hidden" id="jrId">
          <input type="hidden" id="jrOppId">

          <div class="form-group">
            <label for="jrTitle">Article</label>
            <input type="text" id="jrTitle" maxlength="200" required placeholder="Ex : Vélo VTT Decathlon Rockrider">
          </div>

          <div class="form-group">
            <label>Lier une annonce du feed <span class="muted">(optionnel)</span></label>
            <div class="jr-link" id="jrLinkArea">
              <input type="text" id="jrLinkSearch" placeholder="🔎 Rechercher une opportunité…" autocomplete="off">
              <div class="jr-link-results" id="jrLinkResults"></div>
              <div class="jr-link-chosen hidden" id="jrLinkChosen"></div>
            </div>
          </div>

          <div class="form-group">
            <label>Statut</label>
            <div class="dash-type-toggle" id="jrStatus" role="radiogroup" aria-label="Statut">
              <button type="button" class="dash-type-btn is-active" data-status="contacted" role="radio" aria-checked="true">🤝 Contacté</button>
              <button type="button" class="dash-type-btn" data-status="bought" role="radio" aria-checked="false">🛒 Acheté</button>
              <button type="button" class="dash-type-btn" data-status="sold" role="radio" aria-checked="false">✅ Revendu</button>
            </div>
          </div>

          <div class="form-row dash-form-row jr-buy hidden" id="jrBuyRow">
            <div class="form-group"><label for="jrBuyPrice">Prix d'achat (€)</label><input type="number" id="jrBuyPrice" min="0" step="0.01" placeholder="0"></div>
            <div class="form-group"><label for="jrBoughtAt">Date d'achat</label><input type="date" id="jrBoughtAt"></div>
          </div>

          <div class="form-row dash-form-row jr-sell hidden" id="jrSellRow">
            <div class="form-group"><label for="jrSellPrice">Prix de vente (€)</label><input type="number" id="jrSellPrice" min="0" step="0.01" placeholder="0"></div>
            <div class="form-group"><label for="jrSoldAt">Date de vente</label><input type="date" id="jrSoldAt"></div>
          </div>

          <div class="jr-margin hidden" id="jrMargin"></div>

          <div class="form-group">
            <label for="jrNotes">Notes <span class="muted">(optionnel)</span></label>
            <textarea id="jrNotes" rows="2" maxlength="1000" placeholder="Détails, état, négociation…"></textarea>
          </div>

          <div class="dash-form-error form-error hidden" id="jrFormError"></div>
          <div class="actions-area"><button type="submit" class="btn btn-primary" id="jrSubmit">Enregistrer</button></div>
        </form>
      </div>
    </div>`;

  const state = { trades: [], lineChart: null, barChart: null };

  let trades;
  try { trades = await listTrades(); }
  catch (err) {
    if (navState.token !== myToken) return;
    document.getElementById('jrBoard').innerHTML = `<div class="error-panel">❌ ${esc(err.message)}</div>`;
    return;
  }
  if (navState.token !== myToken) return;
  state.trades = trades;

  renderAll();
  wireModal();

  // Retire la classe d'animation d'entrée après son passage
  setTimeout(() => root.querySelector('.journal-page')?.classList.remove('journal-enter'), 700);

  // Pré-remplissage venu de /item/:id (« Ajouter au journal »)
  try {
    const pre = JSON.parse(sessionStorage.getItem('journal-prefill') || 'null');
    if (pre && pre.opportunity_id) {
      sessionStorage.removeItem('journal-prefill');
      openModal(null, { opportunity_id: pre.opportunity_id, title: pre.title });
    }
  } catch (_) {}

  // ════════════════════════ Rendu ════════════════════════
  function renderAll() {
    const has = state.trades.length > 0;
    document.getElementById('jrEmpty').classList.toggle('hidden', has);
    document.getElementById('jrCharts').classList.toggle('hidden', !has);
    document.getElementById('jrBoard').classList.toggle('hidden', !has);
    renderKpis();
    if (has) { renderBoard(); renderCharts(); }
  }

  function renderKpis() {
    const k = computeGroupKpis(state.trades);
    const sign = k.profit > 0 ? '+' : '';
    const pClass = k.profit > 0 ? 'is-positive' : k.profit < 0 ? 'is-negative' : '';
    const roiTxt = k.roi == null ? 'n/d' : `${k.roi > 0 ? '+' : ''}${k.roi.toFixed(1).replace('.', ',')} %`;

    document.getElementById('jrHeroProfit').textContent = `${sign}${eur.format(k.profit)}`;
    document.getElementById('jrHeroProfit').className = `dash-hero-figure ${pClass}`;
    document.getElementById('jrHeroSub').textContent =
      `ROI ${roiTxt} · ${k.counts.sold} revendu${k.counts.sold > 1 ? 's' : ''} / ${k.counts.bought} acheté${k.counts.bought > 1 ? 's' : ''} / ${k.counts.contacted} contacté${k.counts.contacted > 1 ? 's' : ''}`;

    document.getElementById('jrKpis').innerHTML = `
      ${kpi('💰', 'accent-blue', 'Total investi', eur.format(k.invested), 'achats des deals revendus')}
      ${kpi('💵', 'accent-green', 'Total encaissé', eur.format(k.earned), 'ventes réalisées')}
      ${kpi('📈', 'accent-purple', 'Profit net', `${sign}${eur.format(k.profit)}`, 'marge réalisée', pClass)}
      ${kpi('🎯', 'accent-amber', 'ROI', roiTxt, 'retour sur investissement')}`;
  }

  function cardHtml(t) {
    const canEdit = t.user_id === me?.id || isAdmin;
    const margin = (t.status === 'sold' && t.buy_price != null && t.sell_price != null)
      ? Number(t.sell_price) - Number(t.buy_price) : null;
    const priceLine =
      t.status === 'sold'
        ? `<span class="jr-card-price">Achat ${t.buy_price != null ? eur2.format(t.buy_price) : '—'} → Vente ${t.sell_price != null ? eur2.format(t.sell_price) : '—'}</span>`
        : t.status === 'bought'
          ? `<span class="jr-card-price">Payé ${t.buy_price != null ? eur2.format(t.buy_price) : '—'}</span>`
          : '';
    const marginBadge = margin != null
      ? `<span class="jr-card-margin ${margin >= 0 ? 'is-positive' : 'is-negative'}">${margin >= 0 ? '+' : ''}${eur2.format(margin)}</span>` : '';
    const actions = canEdit
      ? `<div class="jr-card-actions">
           <button type="button" class="jr-icon-btn" data-action="edit" data-id="${t.id}" title="Modifier" aria-label="Modifier">✏️</button>
           <button type="button" class="jr-icon-btn jr-icon-danger" data-action="delete" data-id="${t.id}" title="Supprimer" aria-label="Supprimer">🗑️</button>
         </div>` : '';
    return `
      <div class="jr-card" data-id="${t.id}">
        <div class="jr-card-top">
          <span class="jr-card-title">${esc(t.title)}</span>
          ${marginBadge}
        </div>
        <div class="jr-card-meta">${avatar(t)} <span class="jr-card-author">${esc(t.author?.username || 'Anonyme')}</span></div>
        ${priceLine ? `<div class="jr-card-prices">${priceLine}</div>` : ''}
        ${actions}
      </div>`;
  }

  function renderBoard() {
    for (const st of ['contacted', 'bought', 'sold']) {
      const list = state.trades.filter(t => t.status === st);
      const body = document.getElementById('jrColBody-' + st);
      const count = document.getElementById('jrCount-' + st);
      count.textContent = list.length ? `(${list.length})` : '';
      body.innerHTML = list.length
        ? list.map(cardHtml).join('')
        : `<div class="jr-col-empty muted">Aucun deal.</div>`;
    }
    // Délégation : édition / suppression / clic carte
    document.getElementById('jrBoard').onclick = onBoardClick;
  }

  async function onBoardClick(e) {
    const btn = e.target.closest('button[data-action]');
    const card = e.target.closest('.jr-card');
    if (btn) {
      const t = state.trades.find(x => x.id === btn.dataset.id);
      if (!t) return;
      if (btn.dataset.action === 'edit') { openModal(t); return; }
      if (btn.dataset.action === 'delete') {
        if (!confirm(`Supprimer « ${t.title} » ?`)) return;
        try { await deleteTrade(t.id); state.trades = state.trades.filter(x => x.id !== t.id); renderAll(); }
        catch (err) { alert(err.message); }
      }
      return;
    }
    if (card) {  // clic sur la carte (hors boutons) → édition (permet d'avancer le statut)
      const t = state.trades.find(x => x.id === card.dataset.id);
      if (t) openModal(t);
    }
  }

  async function renderCharts() {
    const { labels, buysCumul, sellsCumul, profitMonthly } = buildMonthlySeries(state.trades);
    const lineCanvas = document.getElementById('jrLineChart');
    const barCanvas = document.getElementById('jrBarChart');
    if (!lineCanvas || !barCanvas) return;
    if (!labels.length) { document.getElementById('jrCharts').classList.add('hidden'); return; }

    let Chart;
    try { Chart = await loadChartJs(); }
    catch (_) {
      document.getElementById('jrCharts').innerHTML =
        `<div class="card dash-chart-fallback">📉 Graphiques indisponibles (Chart.js injoignable). Les KPIs et le tableau restent à jour.</div>`;
      return;
    }
    if (navState.token !== myToken) return;
    state.lineChart?.destroy(); state.barChart?.destroy();

    const css = getComputedStyle(document.documentElement);
    const COL = (n, f) => (css.getPropertyValue(n).trim() || f);
    const blue = COL('--accent-blue', '#f5963c'), green = COL('--accent-green', '#34d399'),
      rose = COL('--accent-rose', '#fb5b76'), textSec = COL('--text-secondary', '#78716c'),
      grid = COL('--chart-grid', 'rgba(0,0,0,0.06)');
    const monthLabels = labels.map(formatMonthLabel);
    Chart.defaults.font.family = "'Outfit', system-ui, sans-serif";
    Chart.defaults.color = textSec;
    const scales = { x: { grid: { color: grid }, ticks: { color: textSec } },
      y: { grid: { color: grid }, ticks: { color: textSec, callback: v => eur.format(v) }, beginAtZero: true } };
    const tooltip = { callbacks: { label: ctx => `${ctx.dataset.label} : ${eur2.format(ctx.parsed.y)}` } };

    state.lineChart = new Chart(lineCanvas, {
      type: 'line',
      data: { labels: monthLabels, datasets: [
        { label: 'Achats (cumul)', data: buysCumul, borderColor: blue, backgroundColor: hexA(blue, .12), fill: true, tension: .3 },
        { label: 'Ventes (cumul)', data: sellsCumul, borderColor: green, backgroundColor: hexA(green, .12), fill: true, tension: .3 },
      ] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: textSec, usePointStyle: true, boxWidth: 8 } }, tooltip }, scales },
    });
    state.barChart = new Chart(barCanvas, {
      type: 'bar',
      data: { labels: monthLabels, datasets: [{ label: 'Profit net', data: profitMonthly,
        backgroundColor: profitMonthly.map(v => v >= 0 ? hexA(green, .6) : hexA(rose, .6)),
        borderColor: profitMonthly.map(v => v >= 0 ? green : rose), borderWidth: 1, borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip }, scales },
    });
  }

  // ════════════════════════ Modal ════════════════════════
  function wireModal() {
    document.getElementById('jrAddBtn').addEventListener('click', () => openModal(null));
    document.getElementById('jrEmptyAddBtn').addEventListener('click', () => openModal(null));
    document.getElementById('jrModalClose').addEventListener('click', closeModal);
    document.getElementById('jrModal').addEventListener('click', e => { if (e.target.id === 'jrModal') closeModal(); });
    document.addEventListener('keydown', onEsc);

    document.getElementById('jrStatus').addEventListener('click', e => {
      const b = e.target.closest('.dash-type-btn'); if (!b) return;
      document.querySelectorAll('#jrStatus .dash-type-btn').forEach(x => {
        const on = x === b; x.classList.toggle('is-active', on); x.setAttribute('aria-checked', on ? 'true' : 'false');
      });
      syncStatusFields();
    });
    document.getElementById('jrBuyPrice').addEventListener('input', syncMargin);
    document.getElementById('jrSellPrice').addEventListener('input', syncMargin);

    wireLinkSearch();
    document.getElementById('jrForm').addEventListener('submit', onSubmit);
  }

  function onEsc(e) { if (e.key === 'Escape') closeModal(); }
  function currentStatus() { return document.querySelector('#jrStatus .dash-type-btn.is-active')?.dataset.status || 'contacted'; }

  function syncStatusFields() {
    const st = currentStatus();
    document.getElementById('jrBuyRow').classList.toggle('hidden', st === 'contacted');
    document.getElementById('jrSellRow').classList.toggle('hidden', st !== 'sold');
    syncMargin();
  }
  function syncMargin() {
    const st = currentStatus();
    const b = parseFloat(document.getElementById('jrBuyPrice').value);
    const s = parseFloat(document.getElementById('jrSellPrice').value);
    const box = document.getElementById('jrMargin');
    if (st === 'sold' && b >= 0 && s >= 0 && !isNaN(b) && !isNaN(s)) {
      const m = s - b;
      box.className = `jr-margin ${m >= 0 ? 'is-positive' : 'is-negative'}`;
      box.textContent = `Marge : ${m >= 0 ? '+' : ''}${eur2.format(m)}`;
      box.classList.remove('hidden');
    } else { box.classList.add('hidden'); }
  }

  function setStatusUI(status) {
    document.querySelectorAll('#jrStatus .dash-type-btn').forEach(x => {
      const on = x.dataset.status === status;
      x.classList.toggle('is-active', on); x.setAttribute('aria-checked', on ? 'true' : 'false');
    });
    syncStatusFields();
  }
  function setLinkedOpp(opp) {
    const chosen = document.getElementById('jrLinkChosen');
    const search = document.getElementById('jrLinkSearch');
    document.getElementById('jrLinkResults').innerHTML = '';
    if (opp && opp.opportunity_id) {
      document.getElementById('jrOppId').value = opp.opportunity_id;
      chosen.innerHTML = `🔗 ${esc(opp.title || 'Annonce liée')} <button type="button" class="jr-link-clear" id="jrLinkClear">✕ délier</button>`;
      chosen.classList.remove('hidden'); search.classList.add('hidden');
      document.getElementById('jrLinkClear').addEventListener('click', () => setLinkedOpp(null));
    } else {
      document.getElementById('jrOppId').value = '';
      chosen.classList.add('hidden'); chosen.innerHTML = '';
      search.classList.remove('hidden'); search.value = '';
    }
  }

  function wireLinkSearch() {
    const search = document.getElementById('jrLinkSearch');
    const results = document.getElementById('jrLinkResults');
    let timer = null;
    search.addEventListener('input', () => {
      clearTimeout(timer);
      const q = search.value.trim();
      if (q.length < 2) { results.innerHTML = ''; return; }
      timer = setTimeout(async () => {
        const opps = await searchOpportunities(q);
        results.innerHTML = opps.length
          ? opps.map(o => `<button type="button" class="jr-link-item" data-id="${o.id}" data-title="${esc(o.title)}">
               ${CAT_DOT[o.category] || '⚫'} ${esc(o.title)} <span class="muted">${o.price != null ? eur.format(o.price) : ''}</span></button>`).join('')
          : `<div class="jr-link-empty muted">Aucune annonce trouvée.</div>`;
      }, 250);
    });
    results.addEventListener('click', e => {
      const it = e.target.closest('.jr-link-item'); if (!it) return;
      setLinkedOpp({ opportunity_id: it.dataset.id, title: it.dataset.title });
      // pré-remplit le titre si vide
      const titleEl = document.getElementById('jrTitle');
      if (!titleEl.value.trim()) titleEl.value = it.dataset.title;
    });
  }

  function openModal(trade, prefill) {
    document.getElementById('jrFormError').classList.add('hidden');
    document.getElementById('jrId').value = trade?.id || '';
    document.getElementById('jrModalTitle').textContent = trade ? 'Modifier le deal' : 'Nouveau deal';
    document.getElementById('jrTitle').value = trade?.title || prefill?.title || '';
    document.getElementById('jrBuyPrice').value = trade?.buy_price ?? '';
    document.getElementById('jrSellPrice').value = trade?.sell_price ?? '';
    document.getElementById('jrBoughtAt').value = trade?.bought_at || '';
    document.getElementById('jrSoldAt').value = trade?.sold_at || '';
    document.getElementById('jrNotes').value = trade?.notes || '';
    setStatusUI(trade?.status || 'contacted');
    if (trade?.opportunity_id) setLinkedOpp({ opportunity_id: trade.opportunity_id, title: trade.title });
    else if (prefill?.opportunity_id) setLinkedOpp({ opportunity_id: prefill.opportunity_id, title: prefill.title });
    else setLinkedOpp(null);
    document.getElementById('jrModal').classList.remove('hidden');
    setTimeout(() => document.getElementById('jrTitle')?.focus(), 50);
  }
  function closeModal() { document.getElementById('jrModal').classList.add('hidden'); }

  async function onSubmit(e) {
    e.preventDefault();
    const err = document.getElementById('jrFormError');
    const submit = document.getElementById('jrSubmit');
    err.classList.add('hidden');

    const id = document.getElementById('jrId').value;
    const status = currentStatus();
    const title = document.getElementById('jrTitle').value.trim();
    const buy = document.getElementById('jrBuyPrice').value;
    const sell = document.getElementById('jrSellPrice').value;

    if (!title) return showErr('Indique le nom de l\'article.');
    if ((status === 'bought' || status === 'sold') && !(parseFloat(buy) >= 0)) return showErr('Indique le prix d\'achat.');
    if (status === 'sold' && !(parseFloat(sell) >= 0)) return showErr('Indique le prix de vente.');

    const todayISO = new Date().toISOString().slice(0, 10);
    const payload = {
      title, status,
      opportunity_id: document.getElementById('jrOppId').value || null,
      buy_price: buy, sell_price: sell,
      bought_at: document.getElementById('jrBoughtAt').value || (status !== 'contacted' ? todayISO : null),
      sold_at: document.getElementById('jrSoldAt').value || (status === 'sold' ? todayISO : null),
      notes: document.getElementById('jrNotes').value,
    };

    submit.disabled = true; submit.textContent = 'Enregistrement…';
    try {
      if (id) {
        const up = await updateTrade(id, payload);
        const i = state.trades.findIndex(t => t.id === id);
        if (i >= 0) state.trades[i] = up;
      } else {
        const created = await createTrade(payload);
        state.trades.unshift(created);
      }
      state.trades.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
      closeModal(); renderAll();
    } catch (e2) { showErr(e2.message); }
    finally { submit.disabled = false; submit.textContent = 'Enregistrer'; }
  }
  function showErr(msg) { const e = document.getElementById('jrFormError'); e.textContent = msg; e.classList.remove('hidden'); }
}

// ── Helpers hors closure ─────────────────────────────────────────────────────
function kpi(emoji, accent, label, value, sub, valueClass = '') {
  return `<div class="card dash-kpi dash-kpi--${accent}">
      <div class="dash-kpi-icon" aria-hidden="true">${emoji}</div>
      <div class="dash-kpi-body">
        <span class="dash-kpi-label">${label}</span>
        <span class="dash-kpi-value ${valueClass}">${value}</span>
        <span class="dash-kpi-sub">${sub}</span>
      </div></div>`;
}
function hexA(hex, alpha) {
  const h = String(hex).replace('#', '').trim();
  if (h.length !== 6) return hex;
  return `rgba(${parseInt(h.slice(0,2),16)}, ${parseInt(h.slice(2,4),16)}, ${parseInt(h.slice(4,6),16)}, ${alpha})`;
}
```

- [ ] **Step 2 : Vérifier (page + console)**

Serveur lancé, connecté, sur `/dashboard` :
- La page « Journal » s'affiche (héro, KPIs, Kanban 3 colonnes, état vide si aucun deal).
- **➕ Ajouter un deal** ouvre le modal. Le toggle de statut affiche/masque les champs prix.
- Créer un deal « Contacté » → carte dans la 1ʳᵉ colonne. L'éditer en « Revendu » avec prix
  achat+vente → la carte passe en colonne Revendus avec la marge, les KPIs se mettent à jour.
- La recherche « Lier une annonce » renvoie des résultats (si des opportunités existent).
- Console F12 propre.

- [ ] **Step 3 : Commit**

```bash
git add js/pages/dashboard.js
git commit -m "feat(journal): page /dashboard reecrite en Journal (KPIs groupe + Kanban + modal)"
```

---

## Task 6 : Styles `style.css`

**Files:**
- Modify: `style.css` (append)

- [ ] **Step 1 : Ajouter le bloc de styles à la fin de `style.css`**

```css
/* ===================== Journal de trading ===================== */
/* Animation d'entrée (option C) : KPIs en fondu haut, colonnes depuis les côtés. */
.journal-enter .dash-hero,
.journal-enter .dash-kpis { animation: jrFadeDown .5s ease both; }
.journal-enter .jr-col[data-status="contacted"] { animation: jrSlideL .55s ease both; }
.journal-enter .jr-col[data-status="bought"]    { animation: jrFadeUp .55s ease .08s both; }
.journal-enter .jr-col[data-status="sold"]      { animation: jrSlideR .55s ease both; }
@keyframes jrFadeDown { from { opacity:0; transform:translateY(-12px); } to { opacity:1; transform:none; } }
@keyframes jrFadeUp   { from { opacity:0; transform:translateY(14px); }  to { opacity:1; transform:none; } }
@keyframes jrSlideL   { from { opacity:0; transform:translateX(-26px); } to { opacity:1; transform:none; } }
@keyframes jrSlideR   { from { opacity:0; transform:translateX(26px); }  to { opacity:1; transform:none; } }
@media (prefers-reduced-motion: reduce) {
  .journal-enter .dash-hero, .journal-enter .dash-kpis, .journal-enter .jr-col { animation: none; }
}

/* Kanban */
.jr-board { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-top:18px; }
@media (max-width:780px){ .jr-board { grid-template-columns:1fr; } }
.jr-col { background:var(--glass-1, rgba(255,255,255,.55)); border:1px solid rgba(0,0,0,.06);
  border-radius:16px; padding:12px; min-height:120px; }
.jr-col-head { font-weight:700; font-size:.92rem; margin-bottom:10px; display:flex; gap:6px; align-items:center; }
.jr-col-count { color:var(--text-secondary,#78716c); font-weight:600; font-size:.82rem; }
.jr-col-empty { font-size:.82rem; padding:8px 4px; }

/* Carte deal */
.jr-card { position:relative; background:#fff; border:1px solid rgba(0,0,0,.06); border-radius:12px;
  padding:10px 12px; margin-bottom:9px; cursor:pointer; transition:transform .12s, box-shadow .12s; }
.jr-card:hover { transform:translateY(-2px); box-shadow:0 8px 20px rgba(0,0,0,.07); }
.jr-card-top { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
.jr-card-title { font-weight:600; font-size:.9rem; line-height:1.25; }
.jr-card-margin { font-weight:700; font-size:.82rem; white-space:nowrap; }
.jr-card-margin.is-positive { color:var(--accent-green,#34d399); }
.jr-card-margin.is-negative { color:var(--accent-rose,#fb5b76); }
.jr-card-meta { display:flex; align-items:center; gap:6px; margin-top:6px; font-size:.78rem; color:var(--text-secondary,#78716c); }
.jr-card-prices { margin-top:5px; font-size:.8rem; }
.jr-avatar { display:inline-grid; place-items:center; width:20px; height:20px; border-radius:50%;
  color:#fff; font-size:.7rem; font-weight:700; }
.jr-card-actions { position:absolute; top:8px; right:8px; display:none; gap:2px; }
.jr-card:hover .jr-card-actions { display:flex; }
.jr-icon-btn { background:none; border:none; cursor:pointer; font-size:.85rem; padding:2px 4px; border-radius:6px; }
.jr-icon-btn:hover { background:rgba(0,0,0,.06); }

/* Modal : marge live + recherche feed */
.jr-margin { padding:8px 12px; border-radius:10px; font-weight:700; font-size:.9rem; background:rgba(0,0,0,.04); }
.jr-margin.is-positive { color:var(--accent-green,#34d399); }
.jr-margin.is-negative { color:var(--accent-rose,#fb5b76); }
.jr-link { position:relative; }
.jr-link-results { display:flex; flex-direction:column; gap:2px; margin-top:6px; max-height:180px; overflow:auto; }
.jr-link-item { text-align:left; background:rgba(0,0,0,.03); border:1px solid rgba(0,0,0,.05); border-radius:8px;
  padding:7px 10px; cursor:pointer; font-size:.84rem; }
.jr-link-item:hover { background:var(--accent-soft, rgba(245,150,60,.16)); }
.jr-link-empty { padding:8px 4px; font-size:.82rem; }
.jr-link-chosen { margin-top:6px; padding:8px 10px; border-radius:8px; background:var(--accent-soft, rgba(245,150,60,.16));
  font-size:.84rem; display:flex; justify-content:space-between; align-items:center; gap:8px; }
.jr-link-clear { background:none; border:none; color:var(--accent,#f5963c); cursor:pointer; font-size:.78rem; font-weight:600; white-space:nowrap; }

/* Bouton "Ajouter au journal" sur /item/:id */
.btn-journal { margin-top:10px; width:100%; padding:10px; border-radius:10px; cursor:pointer; font-weight:600;
  background:var(--accent-soft, rgba(245,150,60,.16)); border:1px solid var(--glass-border-accent, rgba(245,150,60,.45));
  color:var(--accent-light, #c2410c); transition:background .15s; }
.btn-journal:hover { background:var(--accent-soft, rgba(245,150,60,.28)); }
```

- [ ] **Step 2 : Vérifier le rendu**

Recharger `/dashboard` : Kanban aligné en 3 colonnes (1 sur mobile), cartes propres avec hover
+ actions, animation d'entrée (colonnes qui glissent) au chargement. Le modal montre la marge
live et la recherche feed. `/item/:id` montre un bouton « Ajouter au journal » cohérent avec la DA.

- [ ] **Step 3 : Commit**

```bash
git add style.css
git commit -m "feat(journal): styles Kanban + cartes + recherche feed + animation d'entree C"
```

---

## Validation finale E2E (manuel)

Serveur lancé, connecté, sur `/dashboard` :
1. Page Journal vide → ➕ Ajouter un deal → créer « Contacté » → carte colonne 1.
2. Éditer le deal → passer « Revendu » + prix achat 80 / vente 150 → marge +70 € affichée, carte
   en colonne Revendus, KPIs (profit +70 €, ROI) et graphiques mis à jour.
3. Lier une annonce du feed via la recherche du modal → puce « 🔗 … ✕ délier ».
4. Depuis `/item/:id` : « ➕ Ajouter au journal » → arrive sur le Journal avec le modal
   pré-rempli (annonce liée, statut Contacté).
5. Depuis un **2ᵉ compte** : les deals du groupe sont visibles ; l'édition/suppression n'est
   permise que sur ses propres deals (ou tout si admin).
6. Transition d'ouverture : le picto **livre** s'anime (déjà livré). Console F12 propre partout.

---

## Self-Review

**Couverture spec :**
- Table `trades` + RLS partagée + trigger updated_at → Task 1 ✅
- `js/lib/trades.js` (CRUD, searchOpportunities, computeGroupKpis profit réalisé, buildMonthlySeries) → Task 2 ✅
- Onglet « Journal » + icône → Task 3 ✅
- Bouton « Ajouter au journal » + relais sessionStorage → Task 4 ✅
- Page Journal : héro + KPIs + 2 graphes + Kanban 3 colonnes + modal adaptatif + recherche feed + pré-remplissage + anim C → Task 5 ✅
- Styles Kanban/cartes/recherche/anim C/bouton item → Task 6 ✅
- Cycle flexible (démarrage direct Acheté/Revendu) → Task 5 (`setStatusUI` + validation conditionnelle) ✅
- Écriture auteur/admin (affichage actions) → Task 5 (`canEdit`) ✅

**Cohérence types/signatures :**
- `listTrades/createTrade/updateTrade/deleteTrade/searchOpportunities/computeGroupKpis/buildMonthlySeries/formatMonthLabel` définis Task 2, importés/appelés Task 5 ✅
- `computeGroupKpis(trades) -> { invested, earned, profit, roi, counts:{contacted,bought,sold} }` → consommé dans `renderKpis` (Task 5) ✅
- `buildMonthlySeries(trades) -> { labels, buysCumul, sellsCumul, profitMonthly }` → consommé dans `renderCharts` (Task 5) ✅
- `sessionStorage 'journal-prefill' = { opportunity_id, title }` écrit Task 4, lu Task 5 ✅
- Statuts `'contacted'|'bought'|'sold'` cohérents entre la migration (CHECK), `buildRow` (Task 2) et l'UI (Task 5) ✅

**Placeholders :** aucun ; code complet partout.
