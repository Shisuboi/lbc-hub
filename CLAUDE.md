# LBC DealFinder Hub — Contexte projet

## Qui je suis
- Développeur non-codeur : Tristan (tristanfranceschetti@gmail.com)
- Claude prend **toutes** les décisions techniques, Tristan gère le produit/UX
- Langue : **toujours répondre en français**

## Ce qu'est le projet (modèle actuel — Phase C)
Hub communautaire privé pour un groupe d'amis, **centré sur un flux d'opportunités de revente**
produites en continu par un **moteur autonome** (`server.py --auto`). Le moteur scrape Leboncoin,
note les annonces via une cascade IA, et publie les opportunités dans Supabase. Le site (GitHub
Pages) affiche ce flux (`/feed`), le détail + commentaires par item (`/item/:id`), la watchlist
partagée (`/watchlist`) et un dashboard financier (`/dashboard`).

> ⚠️ **Pivot Phase C (juin 2026)** : on a **abandonné** l'ancien modèle « recherches unitaires »
> (chaque membre scrapait une recherche et la publiait sur `/hub` ; analyse via copier-coller dans
> Claude.ai ; tables `searches`/`listings`). Ce modèle, ses pages (`/hub`, `/scraper`, `/search`) et
> ses fichiers ont été **retirés** (sous-phase C-5). Les **tables DB `searches`/`listings`/`favorites`
> (ancienne)/`invitations` restent en base** (inutilisées, zéro risque ; nettoyage SQL possible plus
> tard).

## Stack validée
- **Frontend** : Vanilla JS (ES6 modules), SPA history API, Supabase SDK v2 (self-hébergé)
- **Hébergement** : GitHub Pages (`https://shisuboi.github.io/lbc-hub`), déploiement auto sur push `master`
- **Repo GitHub** : `https://github.com/Shisuboi/lbc-hub` (user `Shisuboi`)
- **Base de données** : Supabase (PostgreSQL + Auth + Realtime) — free tier
- **Moteur / scraping** : Python 3.11+ + aiohttp + Playwright (`server.py`, port 8080)
- **IA d'analyse** : **cascade Gemini** dans `engine/` (Phase B, sous `--auto`). L'ancien workflow
  manuel « Générer le prompt + import JSON dans Claude.ai » a été **retiré en Phase C-5**.
- **Tests** : pytest pour le backend (`engine/` + `server.py`) uniquement — **pas de tests frontend**
  (validation manuelle : chargement de page + console F12 ; Node n'est pas installé, le site se sert
  via `python server.py`).

## Architecture clé
```
[Browser] → GitHub Pages (SPA) → Supabase (auth JWT + DB + Realtime)   ← lecture du feed/commentaires
[PC moteur] → server.py --auto → scrape Leboncoin (Playwright) → cascade IA → Supabase (service_role)
```
- Le **frontend** lit/écrit Supabase via le SDK JS (anon key + JWT + RLS) : feed, item, commentaires,
  watchlist, favoris, dashboard.
- Le **moteur `--auto`** est la **seule** brique qui écrit avec la clé `service_role` (opportunités +
  télémétrie `scrape_heartbeats`). C'est l'exception assumée à l'invariant « le frontend seul touche
  Supabase ».

## Moteur autonome (pipeline de revente — Phase A)
- `server.py --auto` démarre des coroutines de fond qui scrapent les `watchlist_searches` actives,
  dédupliquent via SQLite local (`lbc_brain.sqlite3`), détectent les baisses de prix, et écrivent
  dans Supabase via la clé `service_role`.
- Package `engine/` : `config` (.env), `parse` (extract_ad_id/clean_price), `db`
  (Brain SQLite : seen_ads, price_observations, market_observations, scrape_log, outbox,
  pending_enrichment, llm_usage), `prefilter` (règles non-IA), `supa` (REST PostgREST +
  build_opportunity_payload + `upsert_heartbeat`), `scheduler` (run_engine round-robin résilient +
  outbox flush), `scraper` (extraction page de résultats Playwright), `bootstrap` (browser partagé +
  verrou), `telemetry` (heartbeat_worker → `scrape_heartbeats`, Phase C-3).
- Un seul Chromium partagé entre scrape manuel et auto (`scrape_lock` dans server.py).
- ⚠️ **Piège LBC** : `engine/scraper.py` dépend du HTML de Leboncoin, qui change régulièrement (les
  `data-qa-id` de titre/prix/ville ont disparu en 2026). L'extracteur s'appuie sur la **sémantique
  stable** (`article[aria-label]` = titre, `a[href*="/ad/"]` = URL, `<span>` au texte `…€` = prix,
  « Située à <ville> » = ville) via un script DOM in-page. Si le scrape sort des prix à 0 / titres
  vides → LBC a encore changé : ré-inspecter une carte `<article>` et mettre à jour `_EXTRACT_JS`.
- Secrets dans `.env` (jamais committé — déjà dans `.gitignore`). Voir `.env.example`.
- Déploiement 24/7 : voir `docs/DEPLOY-agent-windows.md` (`start-agent.bat` + Planificateur).
- Spec : `docs/superpowers/specs/2026-05-29-pipeline-revente-opportunites-design.md`.

## Cascade IA (pipeline de revente — Phase B)
- **Sous `--auto`** : `process_search` écrit dans un **`LocalSink`** (file SQLite `pending_enrichment`).
  Une 2ᵉ coroutine `enrichment_worker` draine la file, exécute la cascade, et **n'écrit dans Supabase
  que des opportunités notées**. Une 3ᵉ coroutine `heartbeat_worker` (Phase C-3) publie la télémétrie.
- **Cascade 3 étages** (`engine/cascade.py`) : ① **triage groupé** (10-20 annonces/appel,
  `gemini-3.1-flash-lite` gratuit) → 🟡/⚫ + score, ne déclare JAMAIS urgent ; ② **vérification**
  (1 appel/candidate) → prix marché, marge €/%, prix max, lot, signaux ; ③ **photo** (vision, 🔴
  uniquement) → état réel + `scam_risk`.
- **Gate 🔴** : `urgent` seulement si **(a)** le vérificateur a un **tier ≥ `MIN_TIER_FOR_URGENT`**
  (défaut `"flash-lite"` → gate ouverte aux modèles gratuits), **(b)** un score ≥ `URGENT_SCORE_THRESHOLD`
  (défaut 85), **ET (c)** un **grounding FIABLE** : prix marché ancré sur de vrais comparables du même
  modèle (`grounding_level == "model"`, ≥5 annonces LBC observées). Sans (c), l'estimation est « de
  tête » → plafond 🟡 (un 🔴 notifie + dit « fonce », il exige de la confiance). En pratique le
  comparateur tourne juste avant la vérif et remplit le grounding → un modèle parsable + ≥5 comparables
  s'ouvre au 🔴 ; un titre vague sans modèle (`extract_model_name` None) reste 🟡 max. Quand le compte
  Pro Gemini sera dispo : `GEMINI_PRO_ENABLED=true` + `GEMINI_VERIFY_MODEL` + clé Pro +
  `MIN_TIER_FOR_URGENT=pro` pour restreindre. `scam_risk == "high"` à la photo **rétrograde** un 🔴 en 🟡.
- **Modules `engine/`** : `router` (LLMRouter, quotas `llm_usage`, fallback, gate tier),
  `llm_client` (GeminiClient REST), `cascade`, `prompts` (schémas JSON), `grounding` (médiane marché),
  `sink` (LocalSink), `enrich` (worker).
- **`.env` IA optionnelles** : **sans `GEMINI_API_KEY`, l'enrichissement est désactivé** (le moteur
  scrape + met en file). Démarrage 100 % gratuit acté.
- **Résilience** : quota épuisé → stop, file conservée ; LLM malformé → retry sans boucler ; garde
  anti-poison (≥ 5 échecs abandonné) ; Supabase down → outbox.
- Spec : `docs/superpowers/specs/2026-05-30-pipeline-phase-b-cascade-ia-design.md`.
  Validation LIVE : `docs/TESTING-phase-b-live.md`.

## Principe CORS critique
- `server.py` renvoie `Access-Control-Allow-Private-Network: true` sur toutes ses réponses.
- Chrome/Edge supportent HTTPS→localhost (exception mixed content) ; Firefox/Safari : workaround `/install`.

## Auth / accès
- Inscriptions publiques **OFF** dans Supabase.
- **Self-service onboarding** : l'admin crée le user auth dans le Dashboard Supabase et envoie
  identifiant + mdp. Au 1er login, l'invité atterrit sur `/onboarding` et choisit son pseudo (RPC
  `create_self_profile`). La page `/admin` montre les instructions de création d'un user.
- Rétro-compat : RPC `consume_invitation` + route `/invite/:token` restent actifs pour les vieux liens.
- ⚠️ `profiles.id == auth.uid()` (convention). Les RLS « own » comparent `auth.uid() = user_id/owner_id`.

## Schéma DB (modèle actuel)

**Tables vivantes (Phase C) :**
- `profiles` : id (= auth.uid()), username, avatar_color, role ('user'|'admin'), created_at
- `opportunities` : ad_id (unique), source_search_id, platform, title, price, url, image_url,
  location_*, category ('urgent'|'interesting'|'passable'), resale_score, est_market_price,
  est_margin_eur/pct, max_buy_price, is_lot, signals, explanation, photo_verdict, price_dropped,
  previous_price, model_used, status, scraped_at, created_at
- `watchlist_searches` : id, owner_id, title, criteria, source_url, platform, geo_*, price_max,
  exclude_keywords, min_margin_eur/pct, active (≤ 1 active via RPC `set_active_watchlist`), created_at
- `item_comments` : id, opportunity_id, user_id, body, edited_at, created_at (RLS own/admin, realtime)
- `scrape_heartbeats` : search_id (PK), heartbeat_at, last_pass_at, new_ads_per_min, ads_seen_total,
  blocked_recent, updated_at (écrite par le moteur via service_role, lue en realtime)
- `item_favorites` : user_id, opportunity_id, created_at (favoris Phase C, sur opportunity_id)
- `transactions` : dashboard financier (`/dashboard`)

**Tables legacy (dormantes, laissées en base) :** `searches`, `listings`, `favorites` (ancienne, sur
`search_id`), `invitations`.

**RPCs vivantes :** `create_self_profile(new_username)`, `set_active_watchlist(p_search_id)` (SECURITY
DEFINER, atomique). **Legacy :** `validate_invitation`, `consume_invitation`.

## Décisions UX (Phase C)
- **DA** : police Outfit, fond dégradé indigo, glassmorphism, accent #6366f1 ; couleurs par catégorie
  🔴 #f43f5e / 🟡 #facc15 / ⚫ #94a3b8.
- `/feed` : lignes denses (`opportunity-row`), badge catégorie + score, marge €/%, compteur `💬 N`,
  **point « nouveau commentaire »** (C-4, localStorage `comment-seen`), favoris ⭐, toolbar
  filtres/tri/recherche, realtime nouvelle opportunité.
- `/item/:id` : faits clés + analyse IA + fil de commentaires temps réel.
- `/watchlist` : gestion des recherches (ajout/activer/pause/éditer/supprimer, une seule active) +
  **panneau monitoring live** (PC 🟢/⚫, annonces/min, dernière passe, cumul).
- `/profile/:username` : identité (avatar/pseudo/rôle/membre depuis) + ses derniers commentaires.
- Routing SPA : `404.html` → `index.html` fallback (GitHub Pages) ; prefix router `/lbc-hub` en prod.

## Sync cross-machines
- Code + plan + specs + CLAUDE.md : **git + GitHub** (`git pull` sur chaque machine).
- Config Claude projet : `.claude/settings.json` dans le repo.
- Mémoire globale Claude : `~/.claude/` à copier sur le laptop (une fois) puis sync.
- Plugins Superpowers : réinstaller sur chaque machine.
- **Pour faire tourner le moteur sur une machine** : Python 3.11+, `pip install` des deps,
  `playwright install chromium`, copier `.env` (secrets), puis `python server.py --auto`.

## Fichiers critiques
- `server.py` — sert la SPA en dev (réécrit `<base>` `/lbc-hub/`→`/`) + héberge le moteur `--auto`.
  Garde des endpoints de scrape manuel (`/api/start`, `/api/import-results`…) **dormants** depuis le
  retrait de `/scraper` (C-5) — inoffensifs.
- `index.html` — shell SPA avec `<base href>` STATIQUE `/lbc-hub/` (réécrit en `/` par server.py en dev)
  + script SPA route restore.
- `js/main.js` — entrypoint SPA, ORDRE IMPORTANT (renderHeader avant onAuthChange).
- `js/supabase-client.js` — config SDK (`lock: noop`, `autoRefreshToken: false`, etc.).
- `js/vendor/supabase.min.js` — SDK self-hébergé (anti-Tracking-Prevention).
- `engine/` — moteur autonome (voir sections Phase A/B).

## Supabase Auth — config URL
- Dev local : Site URL = `http://localhost:8080`. Prod : `https://shisuboi.github.io/lbc-hub`.
- Redirect URLs (laisser en permanence) : `https://shisuboi.github.io/lbc-hub/*`,
  `http://localhost:8080/*`, `http://localhost:8080/**`.

---

## Phase actuelle

**Phase C livrée et déployée en prod (2026-06-02).** Le hub tourne sur le modèle « flux d'opportunités ».

### Sous-phases Phase C (toutes en prod)
| Sous-phase | Contenu |
|---|---|
| C-1 | `/feed` + `/item/:id` + nouvelle DA (glassmorphism) + favoris item |
| C-2 | Commentaires par item + temps réel (+ fix base href statique Firefox) |
| C-3 | `/watchlist` gestion (RPC `set_active_watchlist`) + monitoring live (`scrape_heartbeats`) |
| C-4 | Badge « nouveau commentaire » sur le feed (localStorage `comment-seen`) |
| C-5 | Nettoyage legacy (`/hub`,`/scraper`,`/search` + 8 fichiers) + profil refait Phase C |

Specs/plans : `docs/superpowers/specs/2026-06-01-phase-c-hub-opportunites-design.md` +
`docs/superpowers/{specs,plans}/2026-06-0{1,2}-phase-c*.md`.

### Routes SPA actives (`js/main.js`)
`/` (login), `/install`, `/invite/:token` (legacy), `/onboarding`, `/feed`, `/item/:id`,
`/watchlist`, `/dashboard`, `/profile/:username`, `/admin`.

### Architecture frontend (Phase C)
- `js/pages/` : login, install, invite, feed, item, watchlist, dashboard, profile, admin.
- `js/components/` : header, opportunity-row, comments.
- `js/lib/` : colors, opportunities, comments, comment-seen, item-favorites, watchlist, transactions.
- `js/router.js` — mini-router history API, strip prefix `/lbc-hub`.

### Migrations Supabase (dans `supabase/migrations/`, à appliquer à la main)
- `2026-05-28-self-onboarding.sql` — RPC `create_self_profile`
- `2026-05-29-pipeline-foundation.sql` — `opportunities` + `watchlist_searches` + RLS
- `2026-06-01-transactions.sql` — `transactions` (dashboard)
- `2026-06-01-phase-c1-favorites.sql` — `item_favorites`
- `2026-06-02-phase-c2-comments.sql` — `item_comments` + RLS + realtime
- `2026-06-02-phase-c3-watchlist.sql` — `scrape_heartbeats` + RPC `set_active_watchlist` + override admin
- (legacy, déjà appliquées : `2026-05-27-favorites.sql`, `2026-05-27-listings-expired.sql`)

### Bugs / pièges connus à éviter
1. **`navigator.locks` du Supabase SDK** : peut figer `getSession()` au boot. Mitigation = `lock: noop`.
2. **Edge / Firefox Tracking Prevention** sur SDK CDN cross-origin → blocage localStorage. Mitigation =
   SDK self-hébergé.
3. **SPA refresh** → 405 si server.py n'a pas le catch-all GET. Mitigation = `add_get('/{path:.*}',
   index_handler)`.
4. **`<base href>` STATIQUE** dans `index.html` : `<base href="/lbc-hub/">` en dur, réécrit en `/` par
   server.py en dev. ⚠️ NE PAS revenir à `document.write('<base>')` : le préchargeur de Firefox résout
   les assets relatifs AVANT le script → erreurs MIME au refresh d'une route profonde (`/item/:id`).
5. **Cross-tab `sessionStorage`** : le flow invitation utilise `sessionStorage.pendingInvite` (par
   onglet) — faire le flow dans un seul onglet.
6. **`onAuthChange` AVANT `renderHeader`** = deadlock SDK. Ordre dans `main.js` : `renderHeader()` →
   `initRouter()` → `onAuthChange(...)`.
7. **`requireAuth({ force })` à chaque navigation = hang Firefox**. Utiliser `getProfile()` sans
   `force` (cache invalidé au login/logout). Voir `js/auth.js`.
8. **Canal realtime à nom fixe + retour sur page** → « cannot add postgres_changes after subscribe() ».
   Mitigation = nom de canal **unique** par souscription (cf. `js/lib/watchlist.js subscribeHeartbeats`).
9. **RLS commentaires** : insert exige `auth.uid() = user_id`. Une erreur « new row violates RLS » au
   post = cache de session mélangé (profil ≠ session active) → logout/login propre.

### Reste à faire / pistes
- **Valider en live** : faire tourner `python server.py --auto` et vérifier : panneau monitoring
  `/watchlist` (🟢 PC actif, annonces/min), opportunités publiées dans le feed, notifs Telegram,
  signal 🔴 urgent (gate ouverte depuis juin 2026 avec flash-lite + seuil 85).
- **Nettoyage SQL legacy** (optionnel) : `searches`/`listings`/`favorites` (ancienne)/`invitations` +
  RPC d'invitation peuvent être supprimés de la base plus tard (zéro dépendance frontend).
- **Compte Pro Gemini** (futur) : quand dispo, mettre `GEMINI_PRO_ENABLED=true` +
  `MIN_TIER_FOR_URGENT=pro` dans `.env` pour des analyses de vérification plus précises.
