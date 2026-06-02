# Phase C-5 — Nettoyage du legacy + profil Phase C

> Date : 2026-06-02
> Clôt la spec Phase C (`2026-06-01-phase-c-hub-opportunites-design.md` §5 et §151-152, sous-phase C-5).
> Statut : design validé, à implémenter.

## 1. Objectif

Retirer l'ancien modèle « recherches unitaires » (scrape manuel → Claude.ai → hub des `searches`)
maintenant que le hub tourne sur le modèle Phase C (feed d'opportunités auto + commentaires +
watchlist). Et retravailler `/profile/:username`, aujourd'hui bâti sur l'ancien modèle, en une fiche
Phase C (identité + derniers commentaires).

Prérequis spec : C-1→C-3 livrés en prod (fait). Cette sous-phase est surtout de la **suppression**,
donc le risque principal est de **casser une navigation vivante** vers une route retirée — d'où la
vérification anti-régression dédiée (§5).

## 2. Inventaire (état réel au 2026-06-02)

**Grappe legacy isolée** (importée seulement par elle-même, `main.js`, ou d'autres legacy) :

| Fichier | Importé par |
|---|---|
| `js/pages/hub.js` (route `/hub`) | `main.js` (hors nav) |
| `js/pages/scraper.js` (route `/scraper`) | `main.js` |
| `js/pages/search.js` (route `/search/:id`) | `main.js` |
| `js/components/listing-card.js` | `search.js` |
| `js/lib/publish.js` | `scraper.js` |
| `js/lib/server-ping.js` | `scraper.js` |
| `js/lib/favorites.js` (ancienne, sur `search_id`) | `hub.js` + `search.js` |
| `js/components/feed-card.js` | `hub.js` **+ `profile.js`** |

**Points d'accroche non-legacy à corriger** (pointent vers une route supprimée) :
- `js/main.js` — `notFound` lie « Retour au Hub » vers `/hub`.
- `js/pages/invite.js` — 5 `navigate('/hub')` / liens (onboarding). `invite.js` **reste** (onboarding actif).
- `js/pages/profile.js` — liens `/hub` (page retravaillée de toute façon).

`js/pages/login.js` redirige déjà vers `/feed` (rien à faire). La nav du header pointe déjà vers
`/feed`, `/watchlist`, `/dashboard` (pas vers les routes retirées).

## 3. Changements

### a) Routes & nav — `js/main.js`
- Retirer les routes `/hub`, `/scraper`, `/search/:id`.
- `notFound` : remplacer le lien `/hub` par `/feed`.

### b) Onboarding — `js/pages/invite.js`
- Remplacer **toutes** les références de navigation `/hub` par `/feed` (5 occurrences :
  redirections après création de profil + liens « Retour »).

### c) Profil Phase C — `js/pages/profile.js`
- **Garder** : `avatarHtml`, pseudo, badge rôle, « Membre depuis le … ».
- **Retirer** : le fetch `searches`, les stats (recherches publiées / annonces analysées / meilleure
  note / dernière activité), le rendu `feedCardHtml`, l'import `feed-card.js`, les liens `/hub`.
- **Ajouter** : une section « 💬 Ses derniers commentaires » alimentée par une nouvelle fonction
  `listCommentsByUser(userId, limit = 20)` dans `js/lib/comments.js` :
  ```js
  supa.from('item_comments')
    .select('id, body, created_at, opportunity_id, opportunity:opportunities(title)')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(limit)
  ```
  Chaque commentaire affiche un extrait du corps + le temps relatif, et est **cliquable vers
  `/item/:opportunity_id`** (titre de l'opportunité affiché). Lien retour → `/feed`.
- État vide : « @pseudo n'a encore rien commenté. »
- RLS : `item_comments` est en `select` ouvert aux membres connectés, et `opportunities` est lisible
  (le feed le lit) → la jointure `opportunity:opportunities(title)` passe.

### d) Suppression des fichiers legacy
Une fois `profile.js` détaché de `feed-card.js`, supprimer :
`js/pages/hub.js`, `js/pages/scraper.js`, `js/pages/search.js`, `js/components/feed-card.js`,
`js/components/listing-card.js`, `js/lib/favorites.js`, `js/lib/publish.js`, `js/lib/server-ping.js`.

## 4. Hors scope (assumé)

- **DB** : `searches`, `listings`, `favorites` (ancienne, sur `search_id`), RPC d'invitation legacy →
  **laissés en place** (inutilisés = zéro risque ; un nettoyage SQL pourra venir plus tard, hors C-5).
- **`server.py`** : **gardé** intégralement (il héberge le moteur `--auto` ; les endpoints de scrape
  manuel deviennent dormants mais sont inoffensifs et hors périmètre frontend).
- **CSS mort** (`style.css` : blocs hub / search / scraper / feed-card / listing-card) : **laissé en
  place**. Le retirer risquerait des régressions visuelles sur les pages restantes pour un gain nul.

## 5. Vérification anti-régression (clé)

Après les changements :
- `grep -rn "/hub\|/scraper\|/search/" js/` ne renvoie **que des commentaires de code** (aucune route,
  aucun lien `data-link`, aucun `navigate(...)`, aucun `import` vivant).
- `grep -rn "feed-card\|listing-card\|lib/favorites\|lib/publish\|lib/server-ping" js/` ne renvoie
  **rien** (aucun import orphelin vers un fichier supprimé).
- Chargement sans erreur console (F12) des pages restantes : `/feed`, `/item/:id`, `/watchlist`,
  `/dashboard`, `/profile/:username`, `/onboarding`, `/admin`, `/install`, `/` (login).
- `/profile/:username` affiche identité + derniers commentaires, chaque commentaire mène à son item.

## 6. Tests

- **pytest** : backend non touché → 128 verts attendus (non-régression).
- **Frontend** (convention projet : pas de tests auto) : validation manuelle via la check-list §5.
