# Phase C — « LBC Deals » : site recentré sur le flux d'opportunités

**Date** : 2026-06-01
**Statut** : Design validé (brainstorming) — prêt pour planification
**Remplace** : le modèle « recherche unitaire » (searches/listings publiés manuellement)

---

## 1. Contexte & motivation

Le projet a changé de centre de gravité. À l'origine, chaque membre lançait un **scrape unitaire** et publiait une « recherche » (avec ses listings) sur le hub. Tout le frontend (`/hub`, `/search/:id`, `/scraper`, tables `searches` + `listings`) est bâti là-dessus.

Depuis les Phases A/B, le vrai cœur est le **PC qui scrape en continu** (moteur autonome `server.py --auto`) et produit des **opportunités** (table `opportunities`) — chaque ligne = **un article individuel** noté par la cascade IA (catégorie 🔴/🟡/⚫, score, marge €/%, prix max d'achat, baisse de prix, explication).

**Problème** : ce flux d'opportunités n'a **aucune interface**. Le moteur déverse tout dans Supabase, mais personne ne le voit sur le site — qui montre encore l'ancien modèle « recherches ».

**Objectif Phase C** : recentrer **tout le site** sur le flux d'items auto-scrapés, avec **commentaires par item** (discussion communautaire sur chaque deal), et une nouvelle direction artistique validée par prototype.

---

## 2. Décisions actées

| # | Décision |
|---|---|
| D-C-01 | **Remplacement total** de l'ancien modèle. Le site devient 100 % centré sur les opportunités. |
| D-C-02 | **Feed d'accueil = liste dense** d'opportunités (pas grille de cartes). |
| D-C-03 | Contrôles du feed : **filtre par catégorie** (🔴/🟡/⚫), **tri** (récent / score / marge €), **favoris** ⭐ sur item, **recherche texte** + filtre par recherche source. |
| D-C-04 | **Page item** : photo + faits clés + analyse IA + **commentaires** en bas. |
| D-C-05 | **Commentaires** : fil chrono, tous les membres postent ; suppression (soi + admin), édition, **temps réel**, **notif sur réponse** (livrée en dernière sous-phase). |
| D-C-06 | **Watchlist communautaire** : tous les membres ajoutent des recherches, mais **une seule active à la fois** (activer une met les autres en pause). Garantie par une RPC atomique. |
| D-C-07 | **Stratégie** : construire les nouvelles pages à côté, repointer nav + accueil, retirer l'ancien code une fois validé. Tables anciennes laissées en place (suppression DB plus tard). |
| D-C-08 | **Direction artistique** validée par prototype, appliquée **à tout le site** (cf. §3). |

---

## 3. Direction artistique (charte graphique, site-wide)

Tokens issus du prototype validé. À centraliser dans les variables CSS de `style.css` et appliquer à **toutes** les pages (feed, item, watchlist, dashboard, admin, login, profil).

```css
--bg:#0a0f1d;            /* fond de base */
--bg-glow:#16203a;       /* halo radial haut-droite : radial-gradient(1200px 600px at 70% -10%, var(--bg-glow), var(--bg) 55%) */
--card:rgba(255,255,255,.035);
--bd:rgba(255,255,255,.08);
--txt:#e7ecf3; --mut:#94a3b8; --mut2:#64748b;
--acc:#6366f1; --acc2:#818cf8;        /* indigo : accent principal, boutons d'action, liens actifs */
/* Système de couleurs par catégorie d'opportunité */
--cat-red:#f43f5e;  --cat-red-txt:#fb7185;   /* 🔴 urgent */
--cat-yel:#facc15;                            /* 🟡 intéressant */
--cat-grey:#94a3b8;                           /* ⚫ passable */
--gain:#34d399;                               /* marge positive */
--lbc:#ff6e14;                                /* bouton "Voir sur Leboncoin" */
```

Principes : police **Outfit** (system-ui en fallback) ; header sticky **glassmorphism** (`backdrop-filter: blur(10px)`, fond translucide) ; cartes/lignes à coins arrondis (**12–14px**), bordure subtile, hover qui surélève légèrement (`translateY(-1px)`) ; bande de couleur (`stripe`, 5px) à gauche pour la catégorie ; densité élevée mais aérée.

> Implémentation visuelle : utiliser le skill `design-taste-frontend` (cf. préférence projet) pour exécuter la re-skin à un niveau de finition élevé, en élevant cette DA sans la trahir.

---

## 4. Plan du site (routes)

| Route | Rôle | Statut |
|---|---|---|
| `/` | Login (déconnecté) ; si connecté → redirige vers `/feed` | adapté |
| `/feed` | **Accueil** : liste dense des opportunités + toolbar (filtres/tri/recherche/favoris) | 🆕 |
| `/item/:id` | Détail d'une opportunité + analyse IA + commentaires (`:id` = `opportunities.id`) | 🆕 |
| `/watchlist` | Gérer les recherches surveillées (ajout par tous, une seule active) | 🆕 |
| `/dashboard` | Tableau de bord financier | inchangé (re-skin DA) |
| `/profile/:username` | Profil allégé : pseudo, avatar, ses derniers commentaires | allégé |
| `/admin` | Admin | inchangé (re-skin DA) |
| ~~`/hub`~~, ~~`/scraper`~~, ~~`/search/:id`~~ | ancien modèle | **retirés en fin de bascule** |

Header (nav) : **🔥 Feed · 📡 Watchlist · 📊 Dashboard** (+ 🛠️ Admin si admin) + menu utilisateur. Le logo pointe vers `/feed`.

---

## 5. Données (Supabase)

### Réutilisé tel quel
- **`opportunities`** — source du feed. Champs déjà présents : `id, ad_id, title, price, url, image_url, location_city, location_postal, category, resale_score, est_market_price, est_margin_eur, est_margin_pct, max_buy_price, is_lot, signals, explanation, photo_verdict, price_dropped, previous_price, status, first_seen_at, scraped_at, created_at, source_search_id`.
- **`watchlist_searches`** — déjà complet (`owner_id, title, source_url, active, min_margin_*`, etc.).

### Nouvelles tables (migration `supabase/migrations/2026-06-01-phase-c.sql`)

```sql
-- Commentaires par item
create table public.item_comments (
  id              uuid primary key default gen_random_uuid(),
  opportunity_id  uuid not null references public.opportunities(id) on delete cascade,
  user_id         uuid not null references public.profiles(id) on delete cascade,
  body            text not null check (char_length(body) between 1 and 2000),
  edited_at       timestamptz,
  created_at      timestamptz not null default now()
);
create index item_comments_opp_idx on public.item_comments (opportunity_id, created_at);
create index item_comments_user_idx on public.item_comments (user_id);

-- Favoris sur item
create table public.item_favorites (
  user_id        uuid not null references public.profiles(id) on delete cascade,
  opportunity_id uuid not null references public.opportunities(id) on delete cascade,
  created_at     timestamptz not null default now(),
  primary key (user_id, opportunity_id)
);
create index item_favorites_user_idx on public.item_favorites (user_id);
```

### RLS (best practices : `(select auth.uid())` wrappé)
- **`opportunities`** : ✅ **déjà OK** — policy `opp_select_all` (lecture pour tout `authenticated`) présente depuis la Phase A. Écriture réservée au moteur (service_role, hors RLS). Rien à ajouter.
- **`item_comments`** (🆕) : `select` tous authenticated ; `insert` avec `user_id = (select auth.uid())` ; `update` du sien ; `delete` du sien **OU** si `profiles.role = 'admin'`.
- **`item_favorites`** (🆕) : `select`/`insert`/`delete` uniquement les siens.
- **`watchlist_searches`** : policies de base **déjà présentes** (Phase A) — `select` toutes (authenticated), `insert` own, `update`/`delete` own (`auth.uid() = owner_id`). **À ajouter** : override admin sur `update`/`delete` (un admin peut éditer/supprimer n'importe quelle recherche). La bascule « active » passe par la RPC ci-dessous (et non par la policy update-own).

### RPC — règle « une seule active »
```sql
create or replace function public.set_active_watchlist(p_search_id uuid)
returns void language plpgsql security definer set search_path = public as $$
begin
  update public.watchlist_searches set active = false where active;
  update public.watchlist_searches set active = true where id = p_search_id;
end; $$;
```
`SECURITY DEFINER` → n'importe quel membre peut basculer la recherche active (contrôle collaboratif du PC partagé), de façon **atomique** (invariant « ≤ 1 active » garanti). Mettre en pause = simple `update active=false` sur sa propre ligne (RLS).

### Laissées en place mais inutilisées (suppression DB plus tard, zéro risque)
`searches`, `listings`, `favorites` (ancienne, sur `search_id`), et les RPC d'invitation déjà legacy.

---

## 6. Fichiers

### Créés
| Fichier | Rôle |
|---|---|
| `js/pages/feed.js` | Feed : fetch opportunités, toolbar (filtres/tri/recherche/favoris), rendu liste, realtime nouvelle opportunité |
| `js/pages/item.js` | Détail item : faits clés + analyse IA + monte le composant commentaires |
| `js/pages/watchlist.js` | Liste des recherches surveillées + ajout + activer/pause |
| `js/components/opportunity-row.js` | Ligne dense d'une opportunité (réutilisée feed + favoris) |
| `js/components/comments.js` | Fil de commentaires + input + édition/suppression + realtime |
| `js/lib/opportunities.js` | Accès données : `list(filtres)`, `get(id)` |
| `js/lib/comments.js` | CRUD commentaires + souscription realtime |
| `js/lib/item-favorites.js` | Favoris item (charge set, toggle) |
| `js/lib/watchlist.js` | Watchlist : list, create, update, `setActive` (RPC), pause |
| `style.css` (bloc) | Variables DA + styles feed/item/watchlist/comments |
| `supabase/migrations/2026-06-01-phase-c.sql` | Tables + RLS + RPC ci-dessus (à appliquer à la main) |

### Modifiés
`js/main.js` (nouvelles routes, retrait anciennes), `js/components/header.js` (nav DA), `index.html` (police/DA si besoin).

### Retirés en fin de bascule (sous-phase finale)
`js/pages/hub.js`, `js/pages/scraper.js`, `js/pages/search.js`, `js/components/feed-card.js`, `js/components/listing-card.js`, `js/lib/favorites.js` (ancienne), `js/lib/publish.js`, `js/lib/server-ping.js` (si plus utilisé).

---

## 7. Commentaires — comportement détaillé

- **Fil chronologique** (plus ancien → plus récent), sous l'item.
- **Poster** : tout membre connecté ; insert avec `user_id = soi`.
- **Éditer** : son propre commentaire ; affiche « (modifié) » via `edited_at`.
- **Supprimer** : le sien, ou n'importe lequel si admin.
- **Temps réel** : souscription Supabase Realtime sur `item_comments` filtrée `opportunity_id = :id` → insert/update/delete reflétés en direct (pattern identique au feed `/hub` actuel ; bien `removeChannel` au démontage de la page).
- **Compteur** affiché sur la ligne du feed (`💬 N`) et en tête de section.
- **Notif sur réponse** (sous-phase C-4, optionnelle) : approche légère sans nouvelle table — `localStorage` mémorise, par item commenté, le `created_at` du dernier commentaire vu ; au chargement du feed, on signale les items où l'utilisateur a commenté ET qui ont des commentaires plus récents (badge + option Notification API, comme le toggle notif actuel du hub). Pas de sur-ingénierie.

---

## 8. Watchlist — comportement détaillé

- Page `/watchlist` : liste de **toutes** les recherches surveillées (titre, source, auteur, état actif/pause), un formulaire d'ajout (titre + URL LBC ; plateforme déduite ; seuils de marge par défaut), et par ligne : **Activer** (→ RPC `set_active_watchlist`, met les autres en pause) ou **Mettre en pause** (son active=false), **Éditer/Supprimer** (sien ou admin).
- Invariant **≤ 1 active** garanti côté DB par la RPC. L'UI reflète clairement laquelle tourne (« ✅ en cours » vs « ⏸️ en pause »).
- Le moteur (`run_engine`) lit déjà `fetch_active_searches()` → avec une seule active, il ne scrape que celle-là. **Aucune modification moteur nécessaire.**

---

## 9. Sous-phases (ordre de construction)

- **C-1 — Lecture & DA** : migration ; `/feed` (liste + filtres + tri + recherche + favoris) ; `/item/:id` (faits + analyse IA, sans commentaires) ; charte DA appliquée site-wide ; repointage nav/accueil ; **conserver** l'ancien code en place mais hors-nav. → *site nouveau utilisable.*
- **C-2 — Commentaires** : composant + lib + realtime + édition/suppression sur `/item/:id`.
- **C-3 — Watchlist** : page `/watchlist` + RPC `set_active_watchlist` + RLS membres.
- **C-4 — Notif sur réponse** (optionnel) : badge/localStorage + Notification API.
- **C-5 — Nettoyage** : retrait des fichiers/pages/legacy de l'ancien modèle, une fois C-1→C-3 validés en prod.

Chaque sous-phase aura son propre plan d'implémentation.

---

## 10. Tests

- **Backend** : la suite pytest existante (moteur) doit rester verte — aucune modification moteur attendue. Si la RPC/SQL est testable via un script, l'ajouter.
- **Frontend** : pas de tests automatisés (convention projet). Check-list E2E manuelle par sous-phase : feed (filtres/tri/recherche/favoris/realtime), item (affichage champs réels, lien LBC), commentaires (post/édit/suppr/realtime/permissions), watchlist (ajout, bascule active atomique, RLS membre vs admin), non-régression dashboard.
- **RLS** : vérifier qu'un membre ne supprime pas le commentaire d'un autre (sauf admin), ne voit/écrit que ses favoris, et que l'activation watchlist met bien les autres en pause.

---

## 11. Risques & points d'attention

- **Re-skin site-wide** : appliquer la nouvelle DA aux pages existantes (dashboard, admin, login, profil) peut introduire des régressions visuelles → procéder page par page, vérifier en preview.
- **Volumétrie feed** : `opportunities` peut grossir → paginer/limiter (ex. 50–100 récentes) + index `created_at desc` déjà présent.
- **Items périmés/vendus** : `opportunities.status` existe (`active`/…) — afficher en priorité les `active` ; gestion fine de l'expiration = hors scope Phase C (potentielle Phase D).
- **Données réelles « arnaque »** (PC à 5 € notés 95) : le feed les montrera en 🟡 ; envisager un durcissement du préfiltre côté moteur ultérieurement (hors scope Phase C).
- **Realtime** : bien démonter les canaux (`removeChannel`) à la navigation pour éviter les fuites (piège connu du hub actuel).
