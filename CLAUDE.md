# LBC DealFinder Hub — Contexte projet

## Qui je suis
- Développeur non-codeur : Tristan (tristanfranceschetti@gmail.com)
- Claude prend **toutes** les décisions techniques, Tristan gère le produit/UX
- Langue : **toujours répondre en français**

## Ce qu'est le projet
Outil local de scraping Leboncoin → transformation en **plateforme communautaire privée** (hub) pour un groupe d'amis. Chaque user scrape en local, publie ses résultats sur un hub hébergé.

## Stack validée
- **Frontend** : Vanilla JS (ES6 modules), SPA history API, Supabase SDK v2
- **Hébergement** : GitHub Pages (`https://shisuboi.github.io/lbc-hub`)
- **Repo GitHub** : `https://github.com/Shisuboi/lbc-hub`
- **Base de données** : Supabase (PostgreSQL + Auth + Realtime) — free tier
- **Scraping local** : Python 3.11 + aiohttp + Playwright (server.py port 8080)
- **IA** : Claude.ai (workflow "Générer le prompt + import JSON" — D-01 appliqué, plus de dépendance Ollama)
- **Tests** : pytest pour endpoints server.py uniquement (pas de tests frontend)

## Architecture clé
```
[Browser] → GitHub Pages (SPA) → Supabase (auth JWT + DB + Realtime)
[Browser] → localhost:8080 (server.py, optionnel, pour scraping)
server.py ne touche JAMAIS Supabase — le frontend publie directement via SDK JS + JWT
```
> ⚠️ Exception depuis Phase A du pipeline de revente : voir « Moteur autonome » ci-dessous.

## Moteur autonome (pipeline de revente — Phase A livrée)
- `server.py --auto` démarre une boucle de fond qui scrape les `watchlist_searches`
  actives, déduplique via SQLite local (`lbc_brain.sqlite3`), détecte les baisses de
  prix, et **écrit des opportunités brutes dans Supabase via la clé `service_role`**.
- ⚠️ **L'invariant « server.py ne touche JAMAIS Supabase » est volontairement levé**
  pour le mode `--auto` (et UNIQUEMENT lui). Le scrape manuel et le frontend restent
  inchangés (anon key + JWT + RLS). Sans `--auto`, l'API HTTP est strictement identique.
- Package `engine/` : `config` (.env), `parse` (extract_ad_id/clean_price), `db`
  (Brain SQLite : seen_ads, price_observations, market_observations, scrape_log, outbox),
  `prefilter` (règles non-IA), `supa` (REST PostgREST + build_opportunity_payload),
  `scheduler` (run_engine round-robin résilient + outbox flush), `scraper`
  (extraction page de résultats Playwright), `bootstrap` (browser partagé + verrou).
- Un seul Chromium partagé entre scrape manuel et auto (`scrape_lock` dans server.py).
- ⚠️ **Piège LBC** : `engine/scraper.py` dépend du HTML de Leboncoin, qui change
  régulièrement (les `data-qa-id` de titre/prix/ville ont disparu en 2026). L'extracteur
  s'appuie donc sur la **sémantique stable** (`article[aria-label]` = titre,
  `a[href*="/ad/"]` = URL, `<span>` au texte `…€` = prix, « Située à <ville> » = ville)
  via un script DOM in-page. Si le scrape sort des prix à 0 / titres vides → LBC a encore
  changé : ré-inspecter une carte `<article>` et mettre à jour `_EXTRACT_JS`.
- Secrets dans `.env` (jamais committé — déjà dans `.gitignore`).
- Migration : `supabase/migrations/2026-05-29-pipeline-foundation.sql`
  (tables `opportunities` + `watchlist_searches` + RLS, à appliquer à la main).
- Déploiement 24/7 : voir `docs/DEPLOY-agent-windows.md` (`start-agent.bat` + Planificateur).
- Phase A = SANS IA (opportunités brutes, champs IA = null). Cascade IA = Phase B.
- Spec : `docs/superpowers/specs/2026-05-29-pipeline-revente-opportunites-design.md`.
- Plan : `docs/superpowers/plans/2026-05-29-pipeline-phase-a-fondation-moteur.md`.

## Principe CORS critique
- `server.py` doit renvoyer `Access-Control-Allow-Private-Network: true` sur toutes ses réponses
- Chrome/Edge supportent HTTPS→localhost (exception mixed content)
- Firefox/Safari : workaround documenté dans /install

## Auth / accès
- Inscriptions publiques **OFF** dans Supabase
- **Depuis v1.8.0** : self-service onboarding. L'admin crée juste le user auth dans le Dashboard Supabase et envoie identifiant + mdp à l'invité. Au 1er login, l'invité atterrit sur `/onboarding` et choisit son pseudo lui-même (RPC `create_self_profile`).
- La page `/admin` ne montre plus la génération de lien d'invitation, juste les instructions de création d'un user.
- Rétro-compat : le RPC `consume_invitation` + la route `/invite/:token` restent actifs pour les liens déjà envoyés avant v1.8.0.

## Schéma DB important (versions cibles)
- `profiles` : id, username, avatar_color, role ('user'|'admin'), created_at
- `invitations` : token, created_by, used_by, used_at, expires_at
- `searches` : id, user_id, title, criteria, source_url, platform ('leboncoin'|'ebay'|'vinted'|'other'), model_name, model_type ('cloud'|'local'), listing_count, best_score, min_price, **scraped_at** (date du scraping, PAS de la publication), created_at
- `listings` : id, search_id, titre, prix, url, note_sur_100, caracteristiques, explication, match_criteres, created_at

## Décisions UX validées
- `scraped_at` est LA date affichée partout (= moment du scraping, pas de la publication Supabase)
- Cards du feed : bandeau violet = modèle cloud, gris = local
- Badge plateforme sur les cards (🟠 LBC, 🔵 eBay, 🟢 Vinted)
- Avertissement bas de page : "modèle cloud = précision élevée"
- Routing SPA : 404.html → index.html fallback pour GitHub Pages
- Prefix router `/lbc-hub` (= nom du repo GitHub)
- GitHub username : `Shisuboi`
- GitHub Pages URL finale : `https://shisuboi.github.io/lbc-hub`

## Multi-plateforme (future-proof)
- `searches.source_url` (générique, pas `url_lbc`)
- `searches.platform` pour filtrer par source dans le feed
- `server.py` : abstraire le scraper derrière une interface `PlatformScraper` (aujourd'hui = LeboncoinScraper)

## Sync cross-machines
- Code + plan + specs + CLAUDE.md : **git + GitHub** (pull sur chaque machine)
- Config Claude projet : `.claude/settings.json` dans le repo
- Mémoire globale Claude : `~/.claude/` à copier sur le laptop (une fois) puis OneDrive sync
- Plugins Superpowers : réinstaller sur chaque machine

## Fichiers critiques
- `server.py` — scraper Python (D-01 appliqué : scrape only, plus d'analyse IA)
- `index.html` — shell SPA avec `<base href>` dynamique (prod/dev) + script SPA route restore
- `js/main.js` — entrypoint SPA, ORDRE IMPORTANT (renderHeader avant onAuthChange)
- `js/supabase-client.js` — config SDK avec `lock: noop`, etc. (cf. "Bugs / pièges connus")
- `js/vendor/supabase.min.js` — SDK self-hébergé (anti-Tracking-Prevention)
- `docs/superpowers/plans/2026-05-27-lbc-hub-mvp-phase1.md` — plan d'origine Phase 1
- `docs/superpowers/specs/2026-05-26-lbc-hub-platform-design.md` — spec validée
- `TESTING.md` + `TESTING-phase2-3.md` — check-lists de tests E2E

## Ce qui NE change PAS
- Scraping Playwright reste identique
- Workflow import JSON Claude.ai reste identique
- Dark theme UI reste identique
- server.py reste optionnel (uniquement pour scraper)

## Invitations (legacy)
- Le flow par token est **déprécié depuis v1.8.0** mais reste fonctionnel pour les liens déjà envoyés.
- Plus aucune génération de nouveau token côté UI (le bouton a été retiré de `/admin`). Les tables `invitations` + RPC `consume_invitation` + route `/invite/:token` restent en DB / code pour la rétro-compat.
- Nouveau flow : voir section "Auth / accès" ci-dessus.

## Supabase Auth — config URL
- Pendant le dev local : Site URL = `http://localhost:8080`
- Au déploiement (Section 9) : remettre Site URL = `https://shisuboi.github.io/lbc-hub`
- Redirect URLs (laisser les 3 en permanence) :
  - `https://shisuboi.github.io/lbc-hub/*`
  - `http://localhost:8080/*`
  - `http://localhost:8080/**`

## Phase actuelle
**Phases 1 → 4 (partiel) livrées et testées E2E.** Code stable, déployé en prod.

### État au 28/05/2026 — récap complet pour reprise (PC fixe)

**Branche** : `master`.
**Tag courant** : `v1.7.0-stable` (testé E2E complet le 28/05/2026).
**Prod en ligne** : https://shisuboi.github.io/lbc-hub/ (déploiement auto sur push master via GH Actions).
**Tests pytest backend** : ✅ 3/3 passent (`python -m pytest tests/ -v`).
**Tests E2E manuels** :
- Phase 1 (v1.0.0) : ✅ validés
- Phases 2-3 (v1.1.0 → v1.6.0) : ✅ validés le 28/05/2026 (cf. `TESTING-phase2-3.md`)
- Phase 4 partielle (v1.7.x) : ✅ validée le 28/05/2026

### Historique des tags (du plus ancien au plus récent)

| Tag | Date | Feature livrée |
|---|---|---|
| `v1.0.0-phase1` | 27/05 | MVP : auth, hub, search detail, scraper Ollama, install, deploy GH Pages |
| `v1.1.0-admin` | 27/05 | Page `/admin` (gestion invitations) — admin only |
| `v1.2.0-d01` | 27/05 | Retrait Ollama : workflow forcé Claude.ai (D-01) |
| `v1.3.0-feed-sort` | 27/05 | Toolbar tri + filtres (plateforme/auteur/texte) sur `/hub` |
| `v1.4.0-profiles` | 27/05 | Pages publiques `/profile/:username` + @username cliquable |
| `v1.5.0-favorites` | 27/05 | Star ⭐ + chip "Favoris" sur `/hub` |
| `v1.6.0-phase3` | 27/05 | Notifications (title-badge + Notification API) + badge "annonce expirée" |
| `v1.7.0-stable` | 28/05 | Bugfixes session (expire btn, scroll SPA, hub classList), dropdown modèle IA, import JSON sans server.py, login sans email réel (convention @lbc-hub.local) |

### Routes SPA actives (`js/main.js`)
- `/` — login
- `/install` — guide d'installation public
- `/invite/:token` — création de profil après acceptation invitation
- `/onboarding` — fallback si user loggé sans profil
- `/hub` — feed des recherches (avec toolbar tri+filtres+favoris+notif)
- `/scraper` — page scraper local (workflow Claude.ai après D-01)
- `/search/:id` — détail d'une recherche + listings (avec étoile favori + toggle expiré)
- `/profile/:username` — profil public d'un membre
- `/admin` — gestion des invitations (admin only)

### Endpoints `server.py` (port 8080)
- `GET /api/ping` — health check
- `POST /api/start` — démarrer un scraping (params : url, pages, criteres, delay)
- `POST /api/resume` — débloquer un job en attente de captcha
- `POST /api/stop` — arrêter un job en cours
- `GET /api/scraped-info` — métadonnées sur `leboncoin_brut.json` existant
- `GET /api/raw-ads` — télécharger `leboncoin_brut.json` (pour joindre à Claude.ai)
- `GET /api/events` — SSE stream (status, logs, scraped, results)
- `POST /api/import-results` — pousser les annonces analysées par Claude.ai
- `GET /*` (catch-all) — SPA fallback (sert `index.html`)

### Schéma DB final (Supabase)

```sql
-- Tables (toutes en public, toutes en RLS activé)
profiles    (id, username, avatar_color, role, created_at)
invitations (token, created_by, used_by, used_at, expires_at, created_at)
searches    (id, user_id, title, criteria, source_url, platform, model_name,
             model_type, listing_count, best_score, min_price, scraped_at, created_at)
listings    (id, search_id, titre, prix, url, note_sur_100, caracteristiques,
             explication, match_criteres, expired_at, created_at)
favorites   (user_id, search_id, created_at) -- PK composite

-- RPCs
validate_invitation(invitation_token uuid)
consume_invitation(invitation_token uuid, new_username text)

-- Indexes
profiles_username_idx, searches_created_at_idx, searches_user_id_idx,
searches_platform_idx, listings_search_id_idx, listings_note_idx,
listings_expired_idx (partial), favorites_user_idx, favorites_search_idx
```

### Migrations Supabase à appliquer manuellement (si pas encore fait)

Dans `supabase/migrations/` :
1. `2026-05-27-favorites.sql` — table `favorites` + RLS
2. `2026-05-27-listings-expired.sql` — colonne `listings.expired_at` + UPDATE RLS
3. `2026-05-28-self-onboarding.sql` — RPC `create_self_profile` (Option B, v1.8.0)

Sans la #1/#2 : les boutons ⭐ et 🚫 affichent l'UI mais ne persistent rien (try/catch silencieux).
Sans la #3 : `/onboarding` plante quand l'invité valide son pseudo (RPC absent).

### Architecture frontend
- `js/main.js` — entrypoint SPA, routes lazy-load, onAuthChange registered APRÈS premier renderHeader (sinon SDK deadlock)
- `js/router.js` — history API mini-router, strip prefix `/lbc-hub` (prod GH Pages)
- `js/supabase-client.js` — SDK self-hébergé dans `js/vendor/supabase.min.js` (anti-Tracking-Prevention Edge/Firefox), config `lock: noop`, `autoRefreshToken: false`, `detectSessionInUrl: false`, `storage: localStorage`
- `js/auth.js` — `requireAuth({requireRole})`, getProfile cached
- `js/components/` — header, feed-card (article wrapper avec auteur en lien séparé), listing-card (avec expired banner + actions row)
- `js/pages/` — login, invite, hub, search, scraper, install, admin, profile
- `js/lib/` — colors, publish, server-ping, favorites

### Fichiers de doc à consulter en cas de reprise
- `TESTING.md` — check-list Phase 1 (faite et validée)
- `TESTING-phase2-3.md` — check-list Phase 2-3 (à dérouler à la reprise)
- `docs/superpowers/plans/2026-05-27-lbc-hub-mvp-phase1.md` — plan d'origine Phase 1 (avec section "Décisions / Évolutions")
- `docs/superpowers/specs/2026-05-26-lbc-hub-platform-design.md` — spec produit
- `README-rapide.txt` — guide rapide pour les amis (dans le ZIP de distribution)

### Bugs / pièges connus à éviter
1. **`navigator.locks` du Supabase SDK** : peut figer `getSession()` au boot si un onglet zombie tient le verrou. Mitigation appliquée = `lock: noop` dans `supabase-client.js`.
2. **Edge / Firefox Tracking Prevention** sur SDK CDN cross-origin → blocage localStorage. Mitigation = SDK self-hébergé.
3. **SPA refresh sur `/hub`** → 405 si server.py n'a pas le catch-all GET. Mitigation = route `add_get('/{path:.*}', index_handler)` dans `create_app()`.
4. **`<base href>` dynamique** dans `index.html` : prod `/lbc-hub/`, dev `/`. Sans ça, les chemins relatifs cassent au refresh sur SPA route.
5. **Cross-tab `sessionStorage`** : l'invitation flow utilise `sessionStorage.pendingInvite` qui est PAR ONGLET — il faut faire le flow dans un seul onglet, sinon le token est perdu.
6. **`onAuthChange` AVANT `renderHeader`** = deadlock du SDK. L'ordre dans `main.js` doit rester : `await renderHeader()` → `initRouter()` → `onAuthChange(...)`.
7. **`requireAuth({ force })` à chaque navigation = hang Firefox**. Forcer `getProfile(true)` dans `requireAuth` déclenche un fetch HTTP `from('profiles').select().single()` à chaque clic de lien. Sur Firefox, ce fetch hang par intermittence (spinner `⏳ Chargement…` figé jusqu'au F5). Mitigation = `getProfile()` sans `force`, le cache est déjà invalidé au login/logout. Voir `js/auth.js` ligne 40.

### Prochaine étape pour Claude (reprise PC fixe)

1. **Pull le repo** : `git pull --tags` sur `master`
2. Tout est stable et testé — reprendre directement sur les idées Phase 4
3. Phase 4 restante : auto-détection annonces expirées, recherches planifiées, commentaires, modération admin

### Phases futures
- ~~Phase 2 = profils, admin UI, tri feed, Realtime amélioré~~ ✅ LIVRÉ (v1.1.0–v1.4.0)
- ~~Phase 3 = favoris, notifications, badge "annonce expirée"~~ ✅ LIVRÉ (v1.5.0–v1.6.0)
- ~~Phase 4 partielle = bugfixes (expire btn, scroll SPA, hub null), sélecteur modèle IA (input libre + datalist + cloud/local), import JSON sans server.py, login sans email réel (@lbc-hub.local)~~ ✅ LIVRÉ (v1.7.x)
- Phase 4 suite (idées) : auto-détection annonces expirées (HEAD check côté server.py),
  recherches "sauvegardées" (re-run du même scrape sur planning), commentaires
  sous une recherche, modération admin (delete search/listing/user)

### Décisions notées pour Phase 2 (voir `docs/superpowers/plans/2026-05-27-lbc-hub-mvp-phase1.md` § Décisions / Évolutions)
- **D-01** : ✅ APPLIQUÉ — l'analyse Ollama locale a été retirée. server.py se contente de scraper Leboncoin et d'écrire `leboncoin_brut.json`. L'analyse passe par Claude.ai via le workflow "Générer le prompt + import JSON". Page `/scraper` simplifiée en conséquence.
