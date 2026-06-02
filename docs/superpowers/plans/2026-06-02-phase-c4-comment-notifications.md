# Phase C-4 — Badge « nouveau commentaire » sur le feed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher un indicateur « nouveau » sur les items du feed où l'utilisateur a participé (au moins un commentaire de lui) et qui ont reçu un commentaire plus récent que sa dernière visite.

**Architecture:** Frontend pur + `localStorage` (aucune table, aucune migration). Une map `localStorage` mémorise par item l'horodatage du dernier commentaire vu. Le feed étend sa requête unique de commentaires pour calculer, par item, le compte + « j'ai participé » + le dernier `created_at`, et affiche un point sur le 💬 quand c'est « non vu ». Ouvrir la page item marque l'item comme vu.

**Tech Stack:** Vanilla JS ES6 modules, Supabase JS SDK v2. PAS de Node, PAS de tests frontend automatisés (convention projet) — validation par chargement de page + console F12.

**Spec:** `docs/superpowers/specs/2026-06-02-phase-c4-comment-notifications-design.md`

**Convention :** aucun test auto frontend. Chaque tâche se vérifie par chargement de page + console F12 propre + le scénario manuel décrit. Le serveur local se lance via `python server.py` (sert `js/` en statique, donc recharger la page sert le fichier modifié).

---

## File Structure

| Fichier | Création / Modif | Responsabilité |
|---|---|---|
| `js/lib/comment-seen.js` | Create | Suivi « vu » par item dans `localStorage` (`markSeen`, `isUnseen`) |
| `js/lib/comments.js` | Modify (ajout `loadCommentMeta`, retrait `loadCommentCounts` en Task 4) | Une requête → `{count, participated, latest}` par item |
| `js/components/opportunity-row.js` | Modify (`opportunityRowHtml`, ~ligne 17 et 34) | Param `hasNewComments` → point sur le 💬 |
| `js/pages/feed.js` | Modify (imports ~ligne 10, ~ligne 66-67, `renderList` ~ligne 128) | Utiliser `loadCommentMeta` + `isUnseen`, passer `hasNewComments` |
| `js/components/comments.js` | Modify (`reload`, ~ligne 87-94) | Appeler `markSeen` au chargement/refresh du fil |
| `style.css` | Modify (append) | Style `.opp-new-dot` |

---

## Task 1 : Lib de suivi « vu » — `js/lib/comment-seen.js`

**Files:**
- Create: `js/lib/comment-seen.js`

Pas de test auto. Vérification = import sans erreur (utilisé en Task 4/5) + test console optionnel.

- [ ] **Step 1: Créer le fichier**

```javascript
// js/lib/comment-seen.js
// Suivi "vu / pas vu" des commentaires par item, dans localStorage (pas de base — voir spec C-4).
// Map { [opportunityId]: dernierISOvu }. Tout accès est best-effort (mode privé / quota).
const KEY = 'lbc-comment-seen';

function readMap() {
  try { return JSON.parse(localStorage.getItem(KEY)) || {}; }
  catch (_) { return {}; }
}
function writeMap(m) {
  try { localStorage.setItem(KEY, JSON.stringify(m)); }
  catch (_) { /* localStorage indisponible : on dégrade en "pas de suivi" */ }
}

/** Mémorise `iso` comme dernier commentaire vu pour cet item (n'avance jamais en arrière). */
export function markSeen(opportunityId, iso) {
  if (!opportunityId || !iso) return;
  const m = readMap();
  if (!m[opportunityId] || iso > m[opportunityId]) {
    m[opportunityId] = iso;
    writeMap(m);
  }
}

/** true si `latestIso` est plus récent que le "vu" stocké (ou si rien n'a été vu mais qu'il y a du contenu). */
export function isUnseen(opportunityId, latestIso) {
  if (!latestIso) return false;
  const seen = readMap()[opportunityId];
  return !seen || latestIso > seen;
}
```

> Note : `created_at` Supabase est une chaîne ISO 8601 homogène (même source partout) → la comparaison lexicographique `>` est correcte.

- [ ] **Step 2: Vérifier la validité du module (console)**

Avec le serveur lancé (`python server.py`), ouvrir une page du site, puis dans la console F12 :
```js
const m = await import('/js/lib/comment-seen.js');
m.markSeen('test-id', '2026-06-02T10:00:00+00:00');
console.log(m.isUnseen('test-id', '2026-06-02T11:00:00+00:00')); // true
console.log(m.isUnseen('test-id', '2026-06-02T09:00:00+00:00')); // false
console.log(m.isUnseen('jamais-vu', '2026-06-02T10:00:00+00:00')); // true
localStorage.removeItem('lbc-comment-seen'); // nettoyage du test
```
Expected: `true`, `false`, `true`, aucune erreur.

- [ ] **Step 3: Commit**

```bash
git add js/lib/comment-seen.js
git commit -m "feat(comments): lib suivi 'vu' par item dans localStorage (phase C-4)"
```

---

## Task 2 : `loadCommentMeta` — requête enrichie

**Files:**
- Modify: `js/lib/comments.js` (ajout d'une fonction, garder `loadCommentCounts` pour l'instant)

- [ ] **Step 1: Ajouter `loadCommentMeta` à la fin de `js/lib/comments.js`**

```javascript
/** Métadonnées commentaires pour une liste d'items, en UNE requête.
 * Renvoie Map<oppId, { count, participated, latest }> :
 *   count        = nombre de commentaires
 *   participated = true si `myUserId` a au moins un commentaire sur l'item
 *   latest       = ISO du commentaire le plus récent (ou null)
 * Best-effort : en cas d'erreur, renvoie une map vide (on ne casse pas le feed). */
export async function loadCommentMeta(oppIds = [], myUserId = null) {
  const meta = new Map();
  if (!oppIds.length) return meta;
  const { data, error } = await supa
    .from('item_comments')
    .select('opportunity_id, user_id, created_at')
    .in('opportunity_id', oppIds);
  if (error || !data) return meta;
  for (const row of data) {
    const m = meta.get(row.opportunity_id) || { count: 0, participated: false, latest: null };
    m.count += 1;
    if (myUserId && row.user_id === myUserId) m.participated = true;
    if (!m.latest || row.created_at > m.latest) m.latest = row.created_at;
    meta.set(row.opportunity_id, m);
  }
  return meta;
}
```

- [ ] **Step 2: Vérifier la syntaxe (console)**

Serveur lancé, console F12 sur une page du site :
```js
const m = await import('/js/lib/comments.js');
console.log(typeof m.loadCommentMeta); // "function"
```
Expected: `"function"`, aucune erreur de chargement de module.

- [ ] **Step 3: Commit**

```bash
git add js/lib/comments.js
git commit -m "feat(comments): loadCommentMeta (count + participated + latest en 1 requete) (phase C-4)"
```

---

## Task 3 : Point « nouveau » dans `opportunity-row.js`

**Files:**
- Modify: `js/components/opportunity-row.js` (signature ~ligne 17, rendu meta ~ligne 33-34)

- [ ] **Step 1: Ajouter le paramètre `hasNewComments` à la signature**

Remplacer la ligne 17 :

```javascript
export function opportunityRowHtml(o, { isFav = false, commentCount = 0 } = {}) {
```

par :

```javascript
export function opportunityRowHtml(o, { isFav = false, commentCount = 0, hasNewComments = false } = {}) {
```

- [ ] **Step 2: Afficher le point quand il y a du nouveau**

Remplacer le bloc de la ligne 33-34 :

```javascript
        <span class="opp-meta">${o.location_city ? `📍 ${esc(o.location_city)}` : ''}${
          commentCount > 0 ? ` <span class="opp-comments">💬 ${commentCount}</span>` : ''}</span>
```

par :

```javascript
        <span class="opp-meta">${o.location_city ? `📍 ${esc(o.location_city)}` : ''}${
          commentCount > 0
            ? ` <span class="opp-comments">💬 ${commentCount}${hasNewComments ? '<span class="opp-new-dot" title="Nouveaux commentaires"></span>' : ''}</span>`
            : ''}</span>
```

- [ ] **Step 3: Vérifier la syntaxe (console)**

Serveur lancé, console F12 :
```js
const m = await import('/js/components/opportunity-row.js');
const html = m.opportunityRowHtml({ id:'x', title:'T', price:10 }, { commentCount:2, hasNewComments:true });
console.log(html.includes('opp-new-dot')); // true
const html2 = m.opportunityRowHtml({ id:'x', title:'T', price:10 }, { commentCount:2, hasNewComments:false });
console.log(html2.includes('opp-new-dot')); // false
```
Expected: `true`, `false`, aucune erreur.

- [ ] **Step 4: Commit**

```bash
git add js/components/opportunity-row.js
git commit -m "feat(feed): point 'nouveau' sur le compteur de commentaires (phase C-4)"
```

---

## Task 4 : Brancher le feed (`loadCommentMeta` + `isUnseen`)

**Files:**
- Modify: `js/pages/feed.js` (import ~ligne 10, chargement ~ligne 66-67, `renderList` ~ligne 128)
- Modify: `js/lib/comments.js` (retrait de `loadCommentCounts` devenu inutilisé)

> Pré-vérif : `loadCommentCounts` n'est importé que par `js/pages/feed.js`. Confirmer avant retrait :
> `grep -rn "loadCommentCounts" js/` → seules les lignes de `feed.js` (import + usage) et la définition dans `comments.js` doivent apparaître.

- [ ] **Step 1: Mettre à jour les imports de `feed.js`**

Remplacer la ligne 10 :

```javascript
import { loadCommentCounts } from '../lib/comments.js';
```

par :

```javascript
import { loadCommentMeta } from '../lib/comments.js';
import { isUnseen } from '../lib/comment-seen.js';
```

- [ ] **Step 2: Charger les métadonnées au lieu des comptes**

Remplacer les lignes 66-67 :

```javascript
  let commentCounts = new Map();
  try { commentCounts = await loadCommentCounts(items.map(o => o.id)); } catch (_) {}
```

par :

```javascript
  let commentMeta = new Map();
  try { commentMeta = await loadCommentMeta(items.map(o => o.id), me?.id); } catch (_) {}
```

- [ ] **Step 3: Calculer `hasNewComments` dans `renderList`**

Remplacer la ligne 127-129 (le `grid.innerHTML = ...`) :

```javascript
    grid.innerHTML = finalList.map(o =>
      opportunityRowHtml(o, { isFav: isFav(o.id), commentCount: commentCounts.get(o.id) || 0 })
    ).join('');
```

par :

```javascript
    grid.innerHTML = finalList.map(o => {
      const meta = commentMeta.get(o.id);
      return opportunityRowHtml(o, {
        isFav: isFav(o.id),
        commentCount: meta ? meta.count : 0,
        hasNewComments: !!(meta && meta.participated && isUnseen(o.id, meta.latest)),
      });
    }).join('');
```

- [ ] **Step 4: Retirer `loadCommentCounts` (devenu mort) de `js/lib/comments.js`**

Supprimer entièrement la fonction `loadCommentCounts` (le bloc `/** Compte les commentaires … */ export async function loadCommentCounts(...) { … }`) de `js/lib/comments.js`, puisque plus aucun fichier ne l'importe.

- [ ] **Step 5: Vérifier (chargement de page + scénario)**

Serveur lancé, login, ouvrir `/feed` :
- La page se charge, le compteur `💬 N` reste correct sur les items commentés (non-régression C-2). **Console F12 propre.**
- `grep -rn "loadCommentCounts" js/` ne renvoie plus rien (aucune référence orpheline).

- [ ] **Step 6: Commit**

```bash
git add js/pages/feed.js js/lib/comments.js
git commit -m "feat(feed): badge 'nouveau' via loadCommentMeta + isUnseen, retrait loadCommentCounts (phase C-4)"
```

---

## Task 5 : Marquer « vu » depuis la page item

**Files:**
- Modify: `js/components/comments.js` (import ~ligne 6, fonction `reload` ~ligne 87-94)

- [ ] **Step 1: Importer `markSeen`**

Remplacer la ligne 6 :

```javascript
import { listComments, createComment, updateComment, deleteComment, subscribeComments } from '../lib/comments.js';
```

par :

```javascript
import { listComments, createComment, updateComment, deleteComment, subscribeComments } from '../lib/comments.js';
import { markSeen } from '../lib/comment-seen.js';
```

- [ ] **Step 2: Marquer « vu » dans `reload`**

Remplacer la fonction `reload` (lignes 87-94) :

```javascript
  async function reload() {
    try {
      comments = await listComments(opportunityId);
      renderList();
    } catch (err) {
      listEl.innerHTML = `<div class="error-panel card">❌ ${esc(err.message)}</div>`;
    }
  }
```

par :

```javascript
  async function reload() {
    try {
      comments = await listComments(opportunityId);
      renderList();
      // Marque l'item comme "vu" jusqu'au dernier commentaire (éteint le badge du feed).
      // reload() tourne au montage, après post/édit/suppr, et à chaque update temps réel.
      if (comments.length) markSeen(opportunityId, comments[comments.length - 1].created_at);
    } catch (err) {
      listEl.innerHTML = `<div class="error-panel card">❌ ${esc(err.message)}</div>`;
    }
  }
```

> `listComments` ordonne par `created_at` ascendant (cf. `js/lib/comments.js`), donc le dernier élément est le commentaire le plus récent.

- [ ] **Step 3: Vérifier (scénario)**

Serveur lancé, login. Sur un item qui a des commentaires, ouvrir `/item/:id` → revenir sur `/feed` : si l'item portait un point « nouveau », il doit avoir disparu. **Console F12 propre.**

- [ ] **Step 4: Commit**

```bash
git add js/components/comments.js
git commit -m "feat(item): marque les commentaires 'vus' a l'ouverture/refresh du fil (phase C-4)"
```

---

## Task 6 : Style du point « nouveau »

**Files:**
- Modify: `style.css` (append)

- [ ] **Step 1: Ajouter le style**

Append à la fin de `style.css` :

```css
/* ===== Phase C-4 : point "nouveau commentaire" sur le feed ===== */
.opp-new-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-left: 5px;
  border-radius: 50%;
  background: var(--c-cat-red, #f87171);
  vertical-align: middle;
  box-shadow: 0 0 6px var(--c-cat-red, #f87171);
}
```

> Note : `--c-cat-red` est la variable déjà utilisée par `opportunity-row.js` (catégorie urgente) ; le fallback `#f87171` couvre le cas où le nom diffère.

- [ ] **Step 2: Vérifier le rendu**

Recharger `/feed` (avec un item portant le badge « nouveau »). Le point rouge apparaît à droite du `💬 N`. **Console F12 propre.**

- [ ] **Step 3: Commit**

```bash
git add style.css
git commit -m "feat(feed): style du point 'nouveau commentaire' (phase C-4)"
```

---

## Validation finale (E2E manuel)

Avec 2 comptes (A et B), serveur lancé, login :
1. A commente l'item X. B commente aussi X (depuis un autre navigateur/onglet).
2. Côté A : aller sur `/feed` → X affiche `💬 2 ●` (point rouge). ✅
3. A ouvre X (`/item/:id`) → fil affiché → retour `/feed` → le point a disparu. ✅
4. A poste un nouveau commentaire sur X → pas de point pour A (il vient de voir). ✅
5. Un item où A n'a jamais commenté ne montre jamais de point, même avec des commentaires. ✅
6. Compteur `💬 N` toujours juste (non-régression C-2), console F12 propre.

---

## Self-Review (rempli par l'auteur du plan)

**Couverture spec :**
- `localStorage` (pas de table) → tout le plan, aucune migration ✅
- `comment-seen.js` (`markSeen`/`isUnseen`, best-effort) → Task 1 ✅
- Feed : 1 requête → `count`/`participated`/`latest` → Task 2 (`loadCommentMeta`) + Task 4 (branchement) ✅
- Badge `participated && isUnseen` → Task 4 (`hasNewComments`) ✅
- Rendu point sur le 💬 → Task 3 + Task 6 (style) ✅
- Clear sur page item (chargement + realtime) → Task 5 (`markSeen` dans `reload`) ✅
- Cas limites (mon commentaire ne me notifie pas ; items visibles seulement ; localStorage indispo) → couverts par `markSeen` dans `reload` (post = reload), le périmètre `oppIds` du feed, et les try/catch de `comment-seen.js` ✅

**Cohérence des types/signatures :** `loadCommentMeta(oppIds, myUserId)` renvoie `Map<oppId,{count,participated,latest}>` (Task 2), consommé tel quel en Task 4. `opportunityRowHtml(o, {isFav, commentCount, hasNewComments})` défini Task 3, appelé avec ces clés Task 4. `markSeen(oppId, iso)` / `isUnseen(oppId, latestIso)` définis Task 1, utilisés Task 4 (`isUnseen`) et Task 5 (`markSeen`). Cohérent.

**Placeholders :** aucun ; tout le code est fourni.

**Point d'attention :** Task 4 retire `loadCommentCounts` — un `grep -rn "loadCommentCounts" js/` (Step préliminaire + Step 5) garantit qu'aucune référence orpheline ne subsiste avant/après le retrait.
