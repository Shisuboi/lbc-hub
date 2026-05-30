# Prompt de démarrage — Phase B (cascade IA)

> Copie-colle tout ce qui suit dans une **nouvelle discussion** Claude Code, depuis le dossier `C:\Users\Tristan\Documents\lbc`.

---

Projet : **lbc-hub** (plateforme communautaire de revente Leboncoin). Je suis Tristan, non-codeur — tu prends toutes les décisions techniques, tu réponds en français.

Je veux démarrer la **Phase B du pipeline de revente : la cascade IA**.

## Où on en est (Phase A = livrée)

La Phase A (moteur autonome) est **terminée, mergée dans `master`, et validée en réel** : `server.py --auto` scrape Leboncoin en boucle, déduplique via un cerveau SQLite local (`lbc_brain.sqlite3`), détecte les baisses de prix, et écrit des **opportunités brutes** dans Supabase (table `opportunities`) via la clé `service_role`. Lors de la validation E2E, 29 vraies opportunités ont été écrites.

- **62 tests passent** : `python -m pytest tests/ -v`
- Package `engine/` : `config`, `parse`, `db` (Brain SQLite), `prefilter`, `supa` (REST + `build_opportunity_payload`), `scheduler` (`process_search`/`run_engine` + outbox), `scraper`, `bootstrap`.
- En Phase A, **tous les champs IA de `opportunities` sont à `null`** (`category`, `resale_score`, `est_market_price`, `est_margin_eur`, `est_margin_pct`, `max_buy_price`, `is_lot`, `lot_unit_price`, `lot_notes`, `signals`, `explanation`, `photo_verdict`, `model_used`). **C'est exactement ce que la Phase B doit remplir.**
- La table SQLite `market_observations` existe mais n'est pas encore alimentée (elle dépend de la catégorisation, donc de la Phase B).

## À lire EN PREMIER avant toute chose

1. `docs/superpowers/specs/2026-05-29-pipeline-revente-opportunites-design.md` — **surtout la section 6 (« Pipeline IA — la cascade de coût »)**, plus 6.1 (grounding prix marché), 6.2 (LLMRouter), 6.3 (urgence/seuils), 6.4 (priorité géo).
2. `docs/superpowers/plans/2026-05-29-pipeline-phase-a-fondation-moteur.md` — sert de **modèle de format** pour le plan Phase B (tâches TDD, fichiers, étapes, commits).
3. `CLAUDE.md` — section « Moteur autonome (Phase A livrée) » + le « Piège LBC » sur les sélecteurs du scraper.
4. Le package `engine/` (lis les modules) pour voir où la Phase B vient se brancher.

## Ce qu'est la Phase B (résumé de la spec)

Une cascade à 4 étages, du moins cher au plus cher, qui enrichit chaque opportunité :
- **Étage 0 — Pré-filtre règles** : DÉJÀ FAIT en Phase A (`engine/prefilter.py`).
- **Étage 1 — Triage groupé** : 10-20 annonces/requête → catégorie 🔴/🟡/⚫, score 0-100, raison courte, drapeau « creuser ? ». Modèle gratuit (Gemini Flash-Lite / Groq).
- **Étage 2 — Analyse approfondie** : 1 appel/annonce sur les 🔴 (+ 🟡 limités) → score affiné, **prix marché estimé**, **marge €+%**, **prix max d'achat**, **détection de lot**, signaux. Gemini Pro (crédits Cloud) → fallback Flash.
- **Étage 3 — Analyse photo (vision)** : 🔴 uniquement → état réel, signaux d'arnaque.
- **Grounding marché** : nourrir l'IA de vrais comparables (base `market_observations` locale + scrape de comparaison ciblé pour les 🔴), pas de prix « de tête ».
- **LLMRouter** : connaît les quotas de chaque fournisseur, compte l'usage du jour (table SQLite `llm_usage`), route le triage vers le moins cher dispo, bascule quand épuisé, plafond Pro configurable + fallback Flash automatique.
- **Urgence/seuils** : 🔴 = score élevé + grosse marge. Seuil de rentabilité hybride **€ ET %**, réglable par recherche (`watchlist_searches.min_margin_eur` / `min_margin_pct`).
- **Priorité géo** : table open-data communes françaises embarquée (aucune API), score de proximité par membre.

## Décisions à trancher avec moi (en brainstorming, AVANT le plan)

⚠️ La spec date de mai 2026 et **suppose** certains modèles/quotas Gemini. À vérifier en LIVE car les free tiers changent vite. Points à clarifier :
- Quels **modèles et endpoints Gemini exacts** sont dispo aujourd'hui (free tier triage + Pro via crédits Cloud) ? SDK Python `google-genai` ou appels REST via aiohttp ?
- Mes **clés API** : j'ai un abo Google AI Pro avec crédits Cloud. Comment on configure la clé Gemini dans `.env` ? (Groq en réserve ?)
- Comment obtenir la **catégorie** d'une annonce pour `market_observations` (depuis l'URL LBC genre `/ad/ordinateurs/…` → « ordinateurs » ?).
- Source de la **table géo** des communes (CSV embarqué ?).
- **Budget/plafond Pro** mensuel à fixer, et le comportement de fallback.
- Faut-il une **2ᵉ passe** (le moteur écrit brut puis un worker IA enrichit) ou enrichir avant l'écriture ? (impact sur la latence et les quotas).

## Workflow imposé (le même qu'en Phase A, ça a très bien marché)

1. **`superpowers:brainstorming`** d'abord (trancher les décisions ci-dessus).
2. **`superpowers:writing-plans`** pour rédiger le plan Phase B détaillé (tâches TDD, fichiers, étapes, commits), au format du plan Phase A.
3. **`superpowers:subagent-driven-development`** pour exécuter : un sous-agent implémenteur par tâche, puis **revue conformité spec** puis **revue qualité de code** à chaque tâche.
4. TDD strict, `python -m pytest tests/ -v` doit rester vert.

## Contraintes / ne pas casser

- **Travailler sur une nouvelle branche** : `feature/pipeline-phase-b-ia` (ne pas bosser directement sur `master`).
- **Ne JAMAIS casser** : l'API HTTP de `server.py`, le scrape manuel, et le moteur Phase A (les 62 tests doivent continuer à passer).
- **Secrets dans `.env`** (déjà gitignored) — jamais committés. La clé Gemini ira là.
- Nouvelles dépendances pip : **seulement si justifié** (un SDK IA est probablement nécessaire ; à valider en brainstorming). Sinon REST via `aiohttp` déjà présent.
- **Leçon E2E de la Phase A** : les tests sur fixtures ne suffisent pas — **valider en LIVE** contre la vraie API Gemini et de vraies opportunités avant de déclarer fini. (En Phase A, le HTML de LBC avait changé et seul le test live l'a révélé.)

## Repère pratique

- Repo : `C:\Users\Tristan\Documents\lbc` — branche actuelle `master` (Phase A mergée).
- Tests : `python -m pytest tests/ -v` (62 passent).
- Lancer le moteur : `python server.py --auto`.

Commence par lire les docs ci-dessus, puis lance le brainstorming de la Phase B.
