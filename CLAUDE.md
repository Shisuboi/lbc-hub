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
- **IA locale** : Ollama
- **IA cloud** : Claude.ai (import JSON manuel, workflow existant)
- **Tests** : pytest pour endpoints server.py uniquement (pas de tests frontend)

## Architecture clé
```
[Browser] → GitHub Pages (SPA) → Supabase (auth JWT + DB + Realtime)
[Browser] → localhost:8080 (server.py, optionnel, pour scraping)
server.py ne touche JAMAIS Supabase — le frontend publie directement via SDK JS + JWT
```

## Principe CORS critique
- `server.py` doit renvoyer `Access-Control-Allow-Private-Network: true` sur toutes ses réponses
- Chrome/Edge supportent HTTPS→localhost (exception mixed content)
- Firefox/Safari : workaround documenté dans /install

## Auth / accès
- Inscriptions publiques **OFF** dans Supabase
- Invitations manuelles par l'admin (Tristan) via dashboard Supabase + snippet SQL
- Flow Phase 1 : admin crée user auth + invitation SQL → communique credentials → user va sur /invite/:token et choisit son pseudo (RPC consume_invitation)

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
- `server.py` — scraper Python (ne PAS casser l'existant en refactorant)
- `app.js` — logique scraper originale (à migrer dans `js/pages/scraper.js`, pas supprimer avant)
- `index.html` — shell SPA (backup dans `index.html.scraper-backup` avant modification)
- `docs/superpowers/plans/2026-05-27-lbc-hub-mvp-phase1.md` — plan d'implémentation Phase 1
- `docs/superpowers/specs/2026-05-26-lbc-hub-platform-design.md` — spec validée

## Ce qui NE change PAS
- Scraping Playwright reste identique
- Analyse Ollama locale reste identique
- Workflow import JSON Claude.ai reste identique
- Dark theme UI reste identique
- server.py reste optionnel (uniquement pour scraper)

## Phase actuelle
**Phase 1 — Hub MVP** (en cours)
Phase 2 = profils, admin UI, tri feed, Realtime amélioré
Phase 3 = favoris, notifications, badge "annonce expirée"
