# Phase C-2 — Commentaires par item — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une discussion communautaire par opportunité. Sur `/item/:id`, un fil de commentaires chronologique : tout membre poste, édite/supprime les siens (un admin peut tout supprimer), le tout **en temps réel**. Un compteur `💬 N` apparaît sur chaque ligne du feed. Remplace le placeholder « Les commentaires arrivent bientôt (C-2) » déjà en place dans `item.js`.

**Architecture:** SPA Vanilla JS (router history-API, lazy routes, Supabase SDK + RLS). On suit à la lettre les patterns C-1 : garde `navState.token` après chaque `await`, helper `esc()` local anti-XSS, realtime via un canal global `window.__commentsChannel` démonté (`removeChannel`) au montage suivant (piège connu : fuites de canaux). Données dans une nouvelle table `item_comments` (FK vers `opportunities` et `profiles`). Auteur récupéré par jointure Supabase `author:profiles(username, avatar_color)`. Sur événement realtime, on **recharge le fil** (N petit par item) plutôt que de reconstruire à partir d'un payload brut sans la jointure auteur.

**Tech Stack:** Vanilla JS (ES6 modules), Supabase JS SDK v2 + Realtime, CSS pur (tokens DA Phase C déjà en place), zéro build step. Migration SQL appliquée à la main dans Supabase.

**Vérification (convention projet) :** pas de tests frontend automatisés. Chaque tâche se valide en **E2E manuel** : `python server.py` puis `http://localhost:8080/feed` connecté → ouvrir un item, vérifier rendu + console (F12) sans erreur. Vérif syntaxe JS : `node --check <fichier>` **si Node est installé** ; sinon (cas de ce poste) charger la page et confirmer l'absence d'erreur de parse/import dans la console F12. Backend : `python -m pytest tests/ -q` doit rester vert (aucune modif moteur en C-2).

---

## Structure des fichiers

| Fichier | Responsabilité | Action |
|---|---|---|
| `supabase/migrations/2026-06-02-phase-c2-comments.sql` | Table `item_comments` + RLS + realtime | Créer (appliquer à la main) |
| `js/lib/comments.js` | Accès données commentaires : list, create, update, remove, counts, subscribe | Créer |
| `js/components/comments.js` | Fil de commentaires : rendu + saisie + édition/suppression + realtime | Créer |
| `style.css` | Styles du fil de commentaires | Modifier (ajouts) |
| `js/pages/item.js` | Monter le composant commentaires (remplace le placeholder) | Modifier |
| `js/components/opportunity-row.js` | Compteur `💬 N` sur la ligne | Modifier |
| `js/pages/feed.js` | Charger les compteurs + les passer aux lignes | Modifier |

**Prérequis DB :** la table `item_favorites` (C-1) est déjà appliquée. C-2 ajoute `item_comments`. La table `opportunities` et `profiles` existent (Phases A/B). Le rôle admin est `profiles.role = 'admin'` (cf. `currentProfile()` qui sélectionne déjà `role`).

---

## Task 1 : Migration `item_comments`

**Files:**
- Create: `supabase/migrations/2026-06-02-phase-c2-comments.sql`

- [ ] **Step 1 : Écrire la migration**

```sql
-- ============================================================================
-- 2026-06-02 — Phase C-2 / Commentaires par item (opportunité)
-- Best practices Supabase : RLS avec (select auth.uid()) wrappé, index FK,
-- realtime activé, replica identity full pour que les events UPDATE/DELETE
-- transportent l'ancien opportunity_id (nécessaire au filtrage realtime côté client).
-- ============================================================================
create table if not exists public.item_comments (
    id              uuid primary key default gen_random_uuid(),
    opportunity_id  uuid not null references public.opportunities(id) on delete cascade,
    user_id         uuid not null references public.profiles(id) on delete cascade,
    body            text not null check (char_length(body) between 1 and 2000),
    edited_at       timestamptz,
    created_at      timestamptz not null default now()
);
create index if not exists item_comments_opp_idx  on public.item_comments (opportunity_id, created_at);
create index if not exists item_comments_user_idx on public.item_comments (user_id);

alter table public.item_comments enable row level security;

-- Lecture : tous les membres connectés
drop policy if exists "item_comments_select_all" on public.item_comments;
create policy "item_comments_select_all" on public.item_comments
    for select to authenticated using (true);

-- Insertion : uniquement en son propre nom
drop policy if exists "item_comments_insert_own" on public.item_comments;
create policy "item_comments_insert_own" on public.item_comments
    for insert to authenticated with check ((select auth.uid()) = user_id);

-- Édition : uniquement son propre commentaire
drop policy if exists "item_comments_update_own" on public.item_comments;
create policy "item_comments_update_own" on public.item_comments
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

-- Suppression : le sien, OU n'importe lequel si admin
drop policy if exists "item_comments_delete_own_or_admin" on public.item_comments;
create policy "item_comments_delete_own_or_admin" on public.item_comments
    for delete to authenticated using (
        (select auth.uid()) = user_id
        or exists (
            select 1 from public.profiles p
            where p.id = (select auth.uid()) and p.role = 'admin'
        )
    );

-- Realtime : diffuser INSERT/UPDATE/DELETE de cette table
alter table public.item_comments replica identity full;
alter publication supabase_realtime add table public.item_comments;
```

> Note : si `alter publication … add table` renvoie « relation is already member of publication », l'ignorer (idempotent au sens fonctionnel). La table doit apparaître dans Database → Replication → `supabase_realtime`.

- [ ] **Step 2 : Appliquer à la main**

Supabase → SQL Editor → coller le SQL → **Run**. Attendu : « Success. No rows returned ».

- [ ] **Step 3 : Vérifier**

- Table Editor → `item_comments` présente, RLS activé (🔒).
- Database → Replication → `supabase_realtime` inclut `item_comments`.

- [ ] **Step 4 : Commit**

```bash
git add supabase/migrations/2026-06-02-phase-c2-comments.sql
git commit -m "feat(db): table item_comments + RLS + realtime (phase C-2)"
```

---

## Task 2 : Lib `comments.js` (accès données)

**Files:**
- Create: `js/lib/comments.js`

- [ ] **Step 1 : Créer `js/lib/comments.js`**

```js
// js/lib/comments.js
// Accès aux commentaires par item (table item_comments, RLS).
// L'auteur est récupéré par jointure (FK user_id -> profiles).
import { supa } from '../supabase-client.js';

const SELECT = 'id, opportunity_id, user_id, body, edited_at, created_at, author:profiles(username, avatar_color)';

/** Liste les commentaires d'une opportunité, du plus ancien au plus récent. */
export async function listComments(opportunityId) {
  const { data, error } = await supa
    .from('item_comments')
    .select(SELECT)
    .eq('opportunity_id', opportunityId)
    .order('created_at', { ascending: true });
  if (error) throw new Error('Chargement des commentaires impossible : ' + error.message);
  return data || [];
}

/** Poste un commentaire. Renvoie la ligne créée (avec auteur). */
export async function createComment(opportunityId, userId, body) {
  const text = (body || '').trim();
  if (!text) throw new Error('Commentaire vide.');
  if (text.length > 2000) throw new Error('Commentaire trop long (max 2000 caractères).');
  const { data, error } = await supa
    .from('item_comments')
    .insert({ opportunity_id: opportunityId, user_id: userId, body: text })
    .select(SELECT)
    .single();
  if (error) throw new Error('Publication impossible : ' + error.message);
  return data;
}

/** Édite son commentaire (renseigne edited_at). */
export async function updateComment(id, body) {
  const text = (body || '').trim();
  if (!text) throw new Error('Commentaire vide.');
  if (text.length > 2000) throw new Error('Commentaire trop long (max 2000 caractères).');
  const { data, error } = await supa
    .from('item_comments')
    .update({ body: text, edited_at: new Date().toISOString() })
    .eq('id', id)
    .select(SELECT)
    .single();
  if (error) throw new Error('Modification impossible : ' + error.message);
  return data;
}

/** Supprime un commentaire (RLS : le sien, ou n'importe lequel si admin). */
export async function deleteComment(id) {
  const { error } = await supa.from('item_comments').delete().eq('id', id);
  if (error) throw new Error('Suppression impossible : ' + error.message);
}

/** Compte les commentaires pour une liste d'opportunités. Renvoie Map<oppId, n>.
 * Tally côté client (une seule requête) : suffisant à l'échelle du projet, pas de vue/RPC. */
export async function loadCommentCounts(oppIds = []) {
  const counts = new Map();
  if (!oppIds.length) return counts;
  const { data, error } = await supa
    .from('item_comments')
    .select('opportunity_id')
    .in('opportunity_id', oppIds);
  if (error || !data) return counts; // compteur best-effort : on ne casse pas le feed
  for (const row of data) {
    counts.set(row.opportunity_id, (counts.get(row.opportunity_id) || 0) + 1);
  }
  return counts;
}

/** Souscrit aux changements realtime des commentaires d'un item.
 * onChange() est appelé sur tout INSERT/UPDATE/DELETE concernant cette opportunité.
 * Renvoie le canal (à passer à supa.removeChannel au démontage). */
export function subscribeComments(opportunityId, onChange) {
  return supa
    .channel('item-comments-' + opportunityId)
    .on('postgres_changes',
      { event: '*', schema: 'public', table: 'item_comments', filter: `opportunity_id=eq.${opportunityId}` },
      () => onChange())
    .subscribe();
}
```

> Note realtime : on déclenche un simple `onChange()` (sans le payload) car le payload brut n'inclut pas la jointure `author`. Le composant rechargera le fil via `listComments` (N petit par item) → noms d'auteurs toujours corrects, code simple.

- [ ] **Step 2 : Vérifier (syntaxe)**

```bash
node --check js/lib/comments.js && echo OK   # si Node absent : vérifier au chargement page (Task 4)
```

- [ ] **Step 3 : Commit**

```bash
git add js/lib/comments.js
git commit -m "feat(comments): lib accès commentaires (list/create/update/delete/counts/realtime) (phase C-2)"
```

---

## Task 3 : Composant `comments.js` + styles

**Files:**
- Create: `js/components/comments.js`
- Modify: `style.css` (bloc commentaires)

- [ ] **Step 1 : Créer `js/components/comments.js`**

```js
// js/components/comments.js
// Fil de commentaires d'un item : rendu, saisie, édition, suppression, temps réel.
// Monté par js/pages/item.js dans un conteneur fourni. Gère son propre canal realtime
// via window.__commentsChannel (démonté au montage suivant — pattern feed/hub).
import { supa } from '../supabase-client.js';
import { listComments, createComment, updateComment, deleteComment, subscribeComments } from '../lib/comments.js';

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function timeAgo(iso) {
  const d = new Date(iso), s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}
function avatar(c) {
  const name = c.author?.username || '?';
  const color = c.author?.avatar_color || 'var(--c-acc)';
  return `<span class="cm-avatar" style="background:${esc(color)}">${esc(name[0].toUpperCase())}</span>`;
}

/**
 * Monte le fil de commentaires.
 * @param {HTMLElement} container  conteneur cible (vidé puis rempli)
 * @param {object} opts  { opportunityId, me }  me = profil courant { id, username, role }
 */
export async function mountComments(container, { opportunityId, me }) {
  // Démonte un éventuel canal d'un item précédent
  if (window.__commentsChannel) {
    try { await supa.removeChannel(window.__commentsChannel); } catch (_) {}
    window.__commentsChannel = null;
  }

  let comments = [];
  const isAdmin = me?.role === 'admin';

  container.innerHTML = `
    <section class="cm-section">
      <h3 class="cm-title">💬 Commentaires <span id="cmCount" class="cm-count"></span></h3>
      <div id="cmList" class="cm-list"><div class="muted">Chargement…</div></div>
      <form id="cmForm" class="cm-form">
        <textarea id="cmInput" class="cm-input" rows="2" maxlength="2000"
          placeholder="Ajouter un commentaire…"></textarea>
        <button type="submit" class="btn-acc">Publier</button>
      </form>
    </section>`;

  const listEl = container.querySelector('#cmList');
  const countEl = container.querySelector('#cmCount');
  const form = container.querySelector('#cmForm');
  const input = container.querySelector('#cmInput');

  function canDelete(c) { return c.user_id === me?.id || isAdmin; }
  function canEdit(c)   { return c.user_id === me?.id; }

  function rowHtml(c) {
    const edited = c.edited_at ? ' <span class="cm-edited">(modifié)</span>' : '';
    const actions = `
      ${canEdit(c)   ? `<button class="cm-link" data-edit="${c.id}">Modifier</button>` : ''}
      ${canDelete(c) ? `<button class="cm-link cm-danger" data-del="${c.id}">Supprimer</button>` : ''}`;
    return `
      <div class="cm-item" data-id="${c.id}">
        ${avatar(c)}
        <div class="cm-body">
          <div class="cm-head">
            <span class="cm-author">${esc(c.author?.username || 'Anonyme')}</span>
            <span class="cm-time">${timeAgo(c.created_at)}${edited}</span>
          </div>
          <div class="cm-text" data-text="${c.id}">${esc(c.body)}</div>
          <div class="cm-actions">${actions}</div>
        </div>
      </div>`;
  }

  function renderList() {
    if (!comments.length) {
      listEl.innerHTML = `<div class="cm-empty muted">Aucun commentaire. Soyez le premier !</div>`;
    } else {
      listEl.innerHTML = comments.map(rowHtml).join('');
    }
    countEl.textContent = comments.length ? `(${comments.length})` : '';
  }

  async function reload() {
    try {
      comments = await listComments(opportunityId);
      renderList();
    } catch (err) {
      listEl.innerHTML = `<div class="error-panel card">❌ ${esc(err.message)}</div>`;
    }
  }

  await reload();

  // Poster
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || !me?.id || form.dataset.pending) return;
    form.dataset.pending = '1';
    try {
      await createComment(opportunityId, me.id, text);
      input.value = '';
      await reload();                 // le realtime rafraîchira aussi les autres clients
    } catch (err) {
      alert(err.message);
    } finally { delete form.dataset.pending; }
  });

  // Édition / suppression (délégation)
  listEl.addEventListener('click', async e => {
    const delBtn = e.target.closest('[data-del]');
    const editBtn = e.target.closest('[data-edit]');

    if (delBtn) {
      const id = delBtn.dataset.del;
      if (!confirm('Supprimer ce commentaire ?')) return;
      try { await deleteComment(id); await reload(); }
      catch (err) { alert(err.message); }
      return;
    }

    if (editBtn) {
      const id = editBtn.dataset.edit;
      const c = comments.find(x => x.id === id);
      if (!c) return;
      const textEl = listEl.querySelector(`[data-text="${id}"]`);
      // Transforme la ligne en mini-éditeur inline
      textEl.innerHTML = `
        <textarea class="cm-input cm-edit-input" rows="2" maxlength="2000">${esc(c.body)}</textarea>
        <div class="cm-edit-actions">
          <button class="btn-acc cm-save" data-save="${id}">Enregistrer</button>
          <button class="cm-link cm-cancel">Annuler</button>
        </div>`;
      const ta = textEl.querySelector('textarea');
      ta.focus();
      textEl.querySelector('.cm-cancel').addEventListener('click', renderList);
      textEl.querySelector('.cm-save').addEventListener('click', async () => {
        const nv = ta.value.trim();
        if (!nv) return;
        try { await updateComment(id, nv); await reload(); }
        catch (err) { alert(err.message); }
      });
    }
  });

  // Realtime : tout changement sur cet item recharge le fil
  window.__commentsChannel = subscribeComments(opportunityId, () => reload());
}
```

> Note : `mountComments` est asynchrone et tolérante à la navigation — `item.js` vérifie `navState.token` avant de l'appeler. Le démontage du canal se fait au montage suivant (un seul item ouvert à la fois). Pour être complet, on ajoute aussi un démontage au changement de page si besoin futur ; le pattern `window.__commentsChannel` suffit ici (identique à `__feedChannel`).

- [ ] **Step 2 : Ajouter les styles dans `style.css`**

```css
/* ===== DA Phase C — commentaires ===== */
.cm-section { margin-top: 18px; }
.cm-title { font-size: 1.05rem; margin-bottom: 12px; }
.cm-count { color: var(--c-mut2); font-weight: 600; }
.cm-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.cm-empty { padding: 14px 0; }
.cm-item { display: flex; gap: 11px; }
.cm-avatar { flex-shrink: 0; width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 800; font-size: .9rem; }
.cm-body { flex: 1; min-width: 0; background: var(--c-card); border: 1px solid var(--c-bd);
  border-radius: 12px; padding: 10px 13px; }
.cm-head { display: flex; gap: 9px; align-items: baseline; margin-bottom: 4px; }
.cm-author { font-weight: 700; color: #f1f5f9; }
.cm-time { color: var(--c-mut2); font-size: .76rem; }
.cm-edited { color: var(--c-mut2); font-style: italic; }
.cm-text { color: #cbd5e1; white-space: pre-wrap; word-break: break-word; line-height: 1.45; }
.cm-actions { margin-top: 6px; display: flex; gap: 12px; }
.cm-link { background: none; border: none; color: var(--c-mut); font-size: .78rem; cursor: pointer; padding: 0; }
.cm-link:hover { color: var(--c-acc2); }
.cm-danger:hover { color: var(--c-cat-red-txt); }
.cm-form { display: flex; flex-direction: column; gap: 8px; }
.cm-input { width: 100%; background: rgba(255,255,255,.05); border: 1px solid var(--c-bd);
  border-radius: 10px; padding: 10px 12px; color: var(--c-txt); font: inherit; resize: vertical; }
.cm-input:focus { outline: none; border-color: rgba(99,102,241,.5); }
.cm-edit-actions { display: flex; gap: 10px; margin-top: 8px; align-items: center; }
.btn-acc { background: var(--c-acc); color: #fff; font-weight: 700; border: none;
  border-radius: 9px; padding: 9px 16px; cursor: pointer; width: max-content; align-self: flex-end; }
.btn-acc:hover { background: var(--c-acc2); }
```

- [ ] **Step 3 : Vérifier (syntaxe)**

```bash
node --check js/components/comments.js && echo OK   # ou vérif console au chargement (Task 4)
```

- [ ] **Step 4 : Commit**

```bash
git add js/components/comments.js style.css
git commit -m "feat(comments): composant fil + saisie + édition/suppression + styles (phase C-2)"
```

---

## Task 4 : Brancher les commentaires dans `/item/:id`

**Files:**
- Modify: `js/pages/item.js`

- [ ] **Step 1 : Importer le composant + le profil courant**

En tête de `js/pages/item.js`, ajouter aux imports :

```js
import { requireAuth, getProfile } from '../auth.js';
import { mountComments } from '../components/comments.js';
```

(La ligne `import { requireAuth } from '../auth.js';` devient l'import groupé ci-dessus.)

- [ ] **Step 2 : Récupérer le profil dans `render()`**

Juste après `await requireAuth();` et sa garde de token, ajouter la récupération du profil (servira pour les permissions d'édition/suppression) :

```js
  const me = await getProfile();
  if (navState.token !== myToken) return;
```

- [ ] **Step 3 : Remplacer le placeholder par un conteneur monté**

Dans le `innerHTML` final, remplacer la ligne :

```js
    <div class="item-comments-placeholder card muted">💬 Les commentaires arrivent bientôt (sous-phase C-2).</div>`;
```

par :

```js
    <div id="itemComments"></div>`;

  const commentsEl = document.getElementById('itemComments');
  if (commentsEl && navState.token === myToken) {
    mountComments(commentsEl, { opportunityId: o.id, me });
  }
}
```

> Attention : `mountComments` est appelée **après** l'écriture du `innerHTML` (le conteneur `#itemComments` doit exister). Ne pas l'`await` n'est pas grave (elle gère ses propres erreurs), mais on peut l'`await` pour cohérence. Garder la garde `navState.token === myToken` pour ne pas monter sur une page qu'on a quittée.

- [ ] **Step 4 : Vérifier (E2E)**

`python server.py` → `http://localhost:8080/feed` connecté → ouvrir un item. Attendu :
- Section « 💬 Commentaires » sous l'analyse IA, avec « Aucun commentaire. Soyez le premier ! ».
- Poster un commentaire → apparaît immédiatement, avec avatar + pseudo + « à l'instant ».
- Recharger (F5) → le commentaire persiste.
- Console F12 sans erreur (vérifie aussi le parse/import des nouveaux modules).

- [ ] **Step 5 : Commit**

```bash
git add js/pages/item.js
git commit -m "feat(item): fil de commentaires sur /item/:id (phase C-2)"
```

---

## Task 5 : Compteur `💬 N` sur le feed

**Files:**
- Modify: `js/components/opportunity-row.js`
- Modify: `js/pages/feed.js`

- [ ] **Step 1 : Accepter `commentCount` dans `opportunityRowHtml`**

Dans `js/components/opportunity-row.js`, modifier la signature et ajouter un badge dans `.opp-meta` :

```js
export function opportunityRowHtml(o, { isFav = false, commentCount = 0 } = {}) {
```

Puis, dans le bloc `.opp-meta`, ajouter le compteur après la localisation :

```js
        <span class="opp-meta">${o.location_city ? `📍 ${esc(o.location_city)}` : ''}${
          commentCount > 0 ? ` <span class="opp-comments">💬 ${commentCount}</span>` : ''}</span>
```

- [ ] **Step 2 : Style du compteur (dans `style.css`)**

```css
.opp-comments { color: var(--c-mut2); margin-left: 8px; }
```

- [ ] **Step 3 : Charger et passer les compteurs dans `feed.js`**

Import en tête :

```js
import { loadCommentCounts } from '../lib/comments.js';
```

Ajouter un compteur au state et le charger après `listOpportunities()` :

```js
  // (après state.items = items;)
  let commentCounts = new Map();
  try { commentCounts = await loadCommentCounts(items.map(o => o.id)); } catch (_) {}
  if (navState.token !== myToken) return;
```

Dans `renderList()`, passer le compteur à chaque ligne :

```js
    grid.innerHTML = finalList.map(o =>
      opportunityRowHtml(o, { isFav: isFav(o.id), commentCount: commentCounts.get(o.id) || 0 })
    ).join('');
```

> Note : `commentCounts` est figé au chargement du feed (pas de refresh temps réel du compteur sur la liste — choix volontaire, simple). Une nouvelle opportunité reçue en realtime a 0 commentaire, ce qui est correct. Le compteur exact se recharge au prochain affichage du feed.

- [ ] **Step 4 : Vérifier (E2E)**

Sur un item ayant ≥ 1 commentaire (créé en Task 4), revenir au feed → la ligne affiche `💬 N`. Les lignes sans commentaire n'affichent rien. Console sans erreur.

- [ ] **Step 5 : Commit**

```bash
git add js/components/opportunity-row.js js/pages/feed.js style.css
git commit -m "feat(feed): compteur de commentaires sur les lignes (phase C-2)"
```

---

## Task 6 : Vérification E2E C-2 + permissions + realtime

**Files:** aucun (vérification)

- [ ] **Step 1 : Non-régression backend**

```bash
python -m pytest tests/ -q
```
Attendu : tous verts (aucune modif moteur en C-2).

- [ ] **Step 2 : E2E complet (navigateur connecté)**

`python server.py`, ouvrir `http://localhost:8080/`. Dérouler :
1. Ouvrir un item → section commentaires visible, vide au départ.
2. **Poster** un commentaire → apparaît avec avatar + pseudo + horodatage ; le champ se vide.
3. **Éditer** son commentaire → mini-éditeur inline → Enregistrer → texte mis à jour + mention « (modifié) ».
4. **Supprimer** son commentaire → confirmation → disparaît.
5. Retour feed → la ligne de l'item affiche `💬 N` cohérent.
6. **Persistance** : F5 sur l'item → les commentaires sont rechargés.
7. Console F12 : aucune erreur rouge.

- [ ] **Step 3 : Realtime (2 onglets / 2 comptes)**

Ouvrir le **même item** dans deux onglets (idéalement deux comptes différents). Poster depuis l'onglet A → le commentaire apparaît dans l'onglet B **sans rafraîchir**. Éditer/supprimer depuis A → reflété dans B. Vérifier qu'en quittant l'item (retour feed) le canal est libéré (pas d'empilement : ouvrir/fermer plusieurs items ne doit pas multiplier les abonnements — `window.__commentsChannel` est démonté au montage suivant).

- [ ] **Step 4 : Permissions (RLS)**

- Avec un **compte non-admin** : tenter de supprimer le commentaire d'un autre → les boutons Modifier/Supprimer ne s'affichent pas pour les commentaires d'autrui ; et même forcé via la console (`deleteComment(idAutrui)`), la RLS doit refuser (erreur, rien supprimé).
- Avec un **compte admin** : le bouton Supprimer apparaît sur **tous** les commentaires et fonctionne.
- Vérifier qu'on ne peut pas poster au nom d'un autre (insert avec `user_id` ≠ soi refusé par la policy `insert_own`).

- [ ] **Step 5 : Merge + déploiement (sur validation utilisateur)**

> ⚠️ Même protocole que C-1 : avant de merger sur `master`, **confirmer que la migration Task 1 est appliquée en prod** (sinon les commentaires échouent silencieusement). Demander confirmation explicite, puis :

```bash
git checkout master && git pull origin master
git merge --no-ff feat/phase-c2 -m "merge: Phase C-2 (commentaires par item + temps réel)"
git push origin master
```
Puis vérifier le workflow GitHub Pages au vert et confirmer la prod à jour.

> Travail sur une branche `feat/phase-c2` créée depuis `master` à jour : `git checkout master && git pull && git checkout -b feat/phase-c2`.

---

## Self-review (couverture spec C-2, design §5/§7)

- Table `item_comments` + RLS (select all, insert own, update own, delete own/admin) → Task 1 ✅
- Realtime activé (publication + replica identity full) → Task 1 ✅
- Fil chronologique (ancien → récent) sous l'item → Tasks 3,4 ✅
- Poster (tout membre), éditer le sien (« modifié »), supprimer le sien ou tout si admin → Task 3 ✅
- Temps réel (insert/update/delete reflétés) avec `removeChannel` au démontage → Tasks 2,3 ✅
- Compteur `💬 N` sur la ligne du feed + en tête de section → Task 5 (feed) + Task 3 (`#cmCount`) ✅
- Notif sur réponse → **hors scope C-2** (sous-phase C-4, optionnelle) — non traité ici, conforme au découpage.
- Non-régression backend (aucune modif moteur) → Task 6 ✅

## Points d'attention

- **Auteur en realtime** : les payloads `postgres_changes` ne portent pas la jointure `author` → on recharge le fil sur événement (`listComments`). Acceptable à l'échelle d'un item ; si un item devenait très commenté, envisager un cache auteur ou un append ciblé.
- **Compteur feed figé** : non rafraîchi en temps réel sur la liste (choix de simplicité). Documenté en Task 5.
- **`alter publication` non idempotent** : peut renvoyer une erreur « already member » si rejoué — sans gravité.
- **XSS** : tout texte utilisateur passe par `esc()` ; `body` est rendu en `white-space: pre-wrap` (pas d'HTML interprété).
- **Node absent sur ce poste** : les `node --check` du plan sont optionnels — la validation de référence est le chargement page + console F12 (le projet se sert via `python server.py`).
