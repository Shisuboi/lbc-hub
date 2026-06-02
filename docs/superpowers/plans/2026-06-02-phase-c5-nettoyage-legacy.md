# Phase C-5 — Nettoyage du legacy + profil Phase C — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retirer l'ancien modèle « recherches unitaires » (pages/composants/libs + routes) et retravailler `/profile/:username` en fiche Phase C (identité + derniers commentaires).

**Architecture:** Suppression de la grappe legacy isolée (hub/scraper/search + leurs deps), repointage des navigations résiduelles `/hub → /feed`, et réécriture de `profile.js` sur le nouveau modèle (commentaires via `item_comments`, plus de `searches`/`feed-card`). DB et `server.py` laissés intacts (hors scope).

**Tech Stack:** Vanilla JS ES6 modules, Supabase JS SDK v2. Pas de Node, pas de tests frontend auto (convention) → validation par chargement de page + console F12 + `grep` anti-régression. `python -m pytest` confirme la non-régression backend.

**Spec:** `docs/superpowers/specs/2026-06-02-phase-c5-nettoyage-legacy-design.md`

**Ordre imposé :** Task 2 (détacher `profile.js` de `feed-card`) AVANT Task 4 (suppression de `feed-card.js`). Task 3 (repointage nav) avant ou avec Task 4.

---

## File Structure

| Fichier | Action | Responsabilité après C-5 |
|---|---|---|
| `js/lib/comments.js` | Modify (ajout `listCommentsByUser`) | + accès aux commentaires d'un membre |
| `js/pages/profile.js` | Rewrite | Fiche Phase C : identité + derniers commentaires |
| `style.css` | Modify (append) | Style liste de commentaires du profil |
| `js/main.js` | Modify | Retrait routes legacy + `notFound` → `/feed` |
| `js/pages/invite.js` | Modify | Navigations `/hub` → `/feed` |
| `js/pages/hub.js` | Delete | — |
| `js/pages/scraper.js` | Delete | — |
| `js/pages/search.js` | Delete | — |
| `js/components/feed-card.js` | Delete | — |
| `js/components/listing-card.js` | Delete | — |
| `js/lib/favorites.js` | Delete | — |
| `js/lib/publish.js` | Delete | — |
| `js/lib/server-ping.js` | Delete | — |

---

## Task 1 : `listCommentsByUser` dans `comments.js`

**Files:**
- Modify: `js/lib/comments.js` (ajout d'une fonction)

Pas de test auto. Vérification = import + appel console.

- [ ] **Step 1: Ajouter la fonction à la fin de `js/lib/comments.js`** (avant `subscribeComments` ou en fin de fichier)

```javascript
/** Derniers commentaires postés par un membre, joints au titre de l'opportunité.
 * Renvoie un tableau [{ id, body, created_at, opportunity_id, opportunity: { title } }].
 * Best-effort : en cas d'erreur, renvoie []. */
export async function listCommentsByUser(userId, limit = 20) {
  if (!userId) return [];
  const { data, error } = await supa
    .from('item_comments')
    .select('id, body, created_at, opportunity_id, opportunity:opportunities(title)')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error || !data) return [];
  return data;
}
```

- [ ] **Step 2: Vérifier (console)**

Serveur lancé (`python server.py`), connecté, console F12 sur le site :
```js
const m = await import('/js/lib/comments.js?v=' + Date.now());
console.log(typeof m.listCommentsByUser); // "function"
```
Expected: `"function"`, aucune erreur de chargement de module.

- [ ] **Step 3: Commit**

```bash
git add js/lib/comments.js
git commit -m "feat(profile): listCommentsByUser (commentaires d'un membre + titre item) (phase C-5)"
```

---

## Task 2 : Réécrire `profile.js` (identité + commentaires)

**Files:**
- Rewrite: `js/pages/profile.js`
- Modify: `style.css` (append d'un petit bloc)

- [ ] **Step 1: Remplacer tout le contenu de `js/pages/profile.js`**

```javascript
// js/pages/profile.js
// Page /profile/:username — fiche publique Phase C : identité + derniers commentaires.
// (L'ancien modèle "recherches publiées" a été retiré en C-5.)

import { supa } from '../supabase-client.js';
import { requireAuth } from '../auth.js';
import { avatarHtml } from '../lib/colors.js';
import { listCommentsByUser } from '../lib/comments.js';
import { navState } from '../router.js';

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function dateFr(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
}

export async function render({ username }) {
    const myToken = navState.token;
    await requireAuth();
    if (navState.token !== myToken) return;

    const root = document.getElementById('appRoot');
    const cleanUsername = (username || '').trim().toLowerCase();

    if (!cleanUsername) {
        root.innerHTML = `
            <section class="profile-page">
                <div class="error-panel card">
                    <h2>Pseudo manquant</h2>
                    <a href="/feed" data-link class="btn btn-primary">Retour au feed</a>
                </div>
            </section>`;
        return;
    }

    root.innerHTML = `<div class="page-loading">⏳ Chargement du profil…</div>`;

    // === Fetch profil ===
    const { data: profile, error: pErr } = await supa
        .from('profiles')
        .select('id, username, avatar_color, role, created_at')
        .eq('username', cleanUsername)
        .single();

    if (navState.token !== myToken) return;
    if (pErr || !profile) {
        root.innerHTML = `
            <section class="profile-page">
                <div class="error-panel card">
                    <h2>Profil introuvable</h2>
                    <p class="muted">Aucun membre nommé <code>@${escapeHtml(cleanUsername)}</code> sur ce hub.</p>
                    <a href="/feed" data-link class="btn btn-primary">Retour au feed</a>
                </div>
            </section>`;
        return;
    }

    // === Fetch ses derniers commentaires ===
    let comments = [];
    try { comments = await listCommentsByUser(profile.id, 20); } catch (_) {}
    if (navState.token !== myToken) return;

    const roleBadge = profile.role === 'admin'
        ? `<span class="badge badge-gold">🛠️ Admin</span>`
        : '';

    const commentsHtml = comments.length === 0
        ? `<div class="empty-state card">
               <p class="muted">@${escapeHtml(profile.username)} n'a encore rien commenté.</p>
           </div>`
        : `<div class="profile-comments">${comments.map(c => `
            <a href="/item/${c.opportunity_id}" data-link class="profile-comment card">
                <div class="pc-on muted">Sur « ${escapeHtml(c.opportunity?.title || 'une opportunité')} »</div>
                <div class="pc-body">${escapeHtml(c.body)}</div>
                <div class="pc-date muted">${dateFr(c.created_at)}</div>
            </a>`).join('')}</div>`;

    root.innerHTML = `
        <section class="profile-page">
            <a href="/feed" data-link class="back-link">← Retour au feed</a>

            <header class="profile-header card">
                <div class="profile-identity">
                    ${avatarHtml(profile, 72)}
                    <div class="profile-name-block">
                        <h1>@${escapeHtml(profile.username)} ${roleBadge}</h1>
                        <p class="muted">Membre depuis le ${dateFr(profile.created_at)}</p>
                    </div>
                </div>
            </header>

            <h2 class="profile-section-title">💬 Ses derniers commentaires</h2>
            ${commentsHtml}
        </section>
    `;
}
```

- [ ] **Step 2: Ajouter le style des commentaires du profil — append à la fin de `style.css`**

```css
/* ===== Phase C-5 : commentaires sur la fiche profil ===== */
.profile-comments { display: flex; flex-direction: column; gap: 10px; }
.profile-comment { display: block; padding: 12px 16px; text-decoration: none; color: inherit; }
.profile-comment:hover { background: rgba(255,255,255,.05); }
.pc-on { font-size: .8rem; margin-bottom: 4px; }
.pc-body { font-size: .95rem; white-space: pre-wrap; word-break: break-word; }
.pc-date { font-size: .75rem; margin-top: 6px; }
```

- [ ] **Step 3: Vérifier (chargement de page)**

Serveur lancé, connecté. Aller sur `/profile/<ton_pseudo>` (ex. via « Mon profil » dans la nav) :
- la fiche affiche avatar + pseudo + rôle + « Membre depuis … » ;
- la section « 💬 Ses derniers commentaires » liste tes commentaires (ou l'état vide), chacun cliquable vers son item ;
- **console F12 propre** ; aucun import de `feed-card.js`.

- [ ] **Step 4: Commit**

```bash
git add js/pages/profile.js style.css
git commit -m "feat(profile): fiche Phase C (identite + derniers commentaires), retrait modele searches (phase C-5)"
```

---

## Task 3 : Repointer les navigations `/hub` → `/feed`

**Files:**
- Modify: `js/main.js` (`notFound`, ~ligne 24-29)
- Modify: `js/pages/invite.js` (occurrences `/hub`)

- [ ] **Step 1: `notFound` de `main.js` → `/feed`**

Remplacer dans `js/main.js` :

```javascript
            <a href="/hub" data-link class="btn btn-primary">Retour au Hub</a>
```

par :

```javascript
            <a href="/feed" data-link class="btn btn-primary">Retour au feed</a>
```

- [ ] **Step 2: Remplacer toutes les occurrences `/hub` de `invite.js` par `/feed`**

Dans `js/pages/invite.js`, remplacer **chaque** `/hub` par `/feed` (5 navigations vivantes lignes 44, 52, 87, 107, 138 + les commentaires lignes 8, 50, 103). Concrètement :
- ligne 44 : `<a href="/feed" data-link class="btn">Retour</a>`
- ligne 52 : `if (profile) { navigate('/feed', true); return; }`
- ligne 87 : `navigate('/feed');`
- ligne 107 : `if (existing) { navigate('/feed', true); return; }`
- ligne 138 : `navigate('/feed');`
- commentaires lignes 8, 50, 103 : remplacer « /hub » par « /feed » dans le texte.

- [ ] **Step 3: Vérifier (chargement)**

Serveur lancé. Forcer la page introuvable (URL bidon, ex. `/zzz`) → le bouton mène à `/feed`. Console F12 propre.

- [ ] **Step 4: Commit**

```bash
git add js/main.js js/pages/invite.js
git commit -m "fix(nav): repointe les navigations /hub vers /feed (notFound + onboarding) (phase C-5)"
```

---

## Task 4 : Retirer les routes legacy + supprimer les fichiers

**Files:**
- Modify: `js/main.js` (retrait de 3 routes)
- Delete: `js/pages/hub.js`, `js/pages/scraper.js`, `js/pages/search.js`, `js/components/feed-card.js`, `js/components/listing-card.js`, `js/lib/favorites.js`, `js/lib/publish.js`, `js/lib/server-ping.js`

- [ ] **Step 1: Retirer les 3 routes legacy de `js/main.js`**

Supprimer ces 3 lignes :

```javascript
route('/hub',               () => import('./pages/hub.js').then(m => m.render()));
route('/scraper',           () => import('./pages/scraper.js').then(m => m.render()));
route('/search/:id',        (p) => import('./pages/search.js').then(m => m.render(p)));
```

(Garder toutes les autres routes : `/`, `/install`, `/invite/:token`, `/onboarding`, `/feed`, `/item/:id`, `/watchlist`, `/dashboard`, `/profile/:username`, `/admin`.)

- [ ] **Step 2: Supprimer les 8 fichiers legacy**

```bash
git rm js/pages/hub.js js/pages/scraper.js js/pages/search.js \
       js/components/feed-card.js js/components/listing-card.js \
       js/lib/favorites.js js/lib/publish.js js/lib/server-ping.js
```

- [ ] **Step 3: Vérification anti-régression (grep)**

```bash
grep -rn "/hub\|/scraper\|/search/" js/
grep -rn "feed-card\|listing-card\|lib/favorites\|lib/publish\|lib/server-ping" js/
```
Expected :
- Le 1er `grep` ne renvoie **que des commentaires** (ex. `router.js` « pattern: '/hub' ou '/search/:id' », `comments.js` « pattern feed/hub ») — **aucune** ligne `route(`, `href=`, `navigate(`, `import`.
- Le 2ᵉ `grep` ne renvoie **rien** (aucun import orphelin).

Si une référence vivante subsiste, la corriger avant de continuer.

- [ ] **Step 4: Vérifier le chargement des pages restantes (console F12 propre)**

Serveur lancé, connecté. Charger successivement : `/feed`, un `/item/:id`, `/watchlist`, `/dashboard`, `/profile/<pseudo>`, `/admin`, `/install`, et une URL bidon (notFound). Aucune erreur console, aucune route morte.

- [ ] **Step 5: Non-régression backend**

```bash
python -m pytest tests/ -q
```
Expected: `128 passed` (le backend n'est pas touché).

- [ ] **Step 6: Commit**

```bash
git add js/main.js
git commit -m "chore(legacy): retire routes /hub /scraper /search + 8 fichiers de l'ancien modele (phase C-5)"
```

---

## Validation finale (E2E manuel)

Serveur lancé, connecté :
1. Nav header (Feed / Watchlist / Dashboard) + logo → toutes OK.
2. « Mon profil » → fiche identité + derniers commentaires ; cliquer un commentaire → ouvre l'item.
3. Page introuvable (URL bidon) → bouton « Retour au feed » fonctionne.
4. Onboarding (`/onboarding`) : si testable, après création de profil → atterrit sur `/feed`.
5. Console F12 propre partout ; `git status` ne montre plus les 8 fichiers legacy.

---

## Self-Review (rempli par l'auteur du plan)

**Couverture spec :**
- §3a Routes & nav (`main.js`) : retrait routes → Task 4 ; `notFound` → `/feed` → Task 3 ✅
- §3b Onboarding (`invite.js`) `/hub`→`/feed` → Task 3 ✅
- §3c Profil Phase C (identité + commentaires, retrait searches/feed-card, `listCommentsByUser`) → Task 1 + Task 2 ✅
- §3d Suppression des 8 fichiers legacy → Task 4 ✅
- §4 Hors scope (DB, server.py, CSS mort) : aucune tâche n'y touche ✅
- §5 Vérif anti-régression (2 grep + chargement pages) → Task 4 Step 3-4 ✅
- §6 Tests (pytest 128) → Task 4 Step 5 ✅

**Cohérence des types/signatures :** `listCommentsByUser(userId, limit=20)` défini Task 1, appelé `listCommentsByUser(profile.id, 20)` Task 2, renvoie des lignes `{ id, body, created_at, opportunity_id, opportunity:{title} }` consommées telles quelles dans le rendu Task 2 (`c.opportunity?.title`, `c.opportunity_id`, `c.body`, `c.created_at`). Cohérent.

**Placeholders :** aucun ; tout le code (profil complet, fonction lib, CSS) est fourni.

**Ordre de suppression :** Task 2 détache `profile.js` de `feed-card.js` avant que Task 4 ne supprime `feed-card.js` → pas d'import cassé entre les tâches. Task 3 repointe `/hub` avant le retrait des routes en Task 4.
