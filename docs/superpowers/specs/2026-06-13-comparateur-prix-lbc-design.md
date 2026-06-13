# Comparateur de prix LBC ciblé (remplace la recherche web Gemini)

**Date :** 2026-06-13
**Statut :** design validé, prêt pour plan d'implémentation

## Contexte & motivation

La cascade IA estime le prix de revente (`est_market_price`) pour calculer la marge. Jusqu'ici
elle s'appuyait sur :
- un **grounding** : médiane des prix réels collectés passivement (table `market_observations`,
  par modèle via `extract_model_name`), injecté dans les prompts par `_grounding_line` ;
- un calibrage anti-« prix de tête 2024 » dans les prompts.

Une tentative d'ajouter une **recherche web Gemini** (outil `googleSearch`) a échoué : le grounding
Google Search **n'est pas inclus dans le free tier** (429 `RESOURCE_EXHAUSTED` / « check your plan and
billing details » dès le 1ᵉʳ appel). Il faudrait activer la facturation. Décision produit (Tristan) :
**rester 100 % gratuit** et remplacer cette voie par une recherche **sur Leboncoin lui-même**.

## Objectif

Quand le moteur vérifie une annonce candidate, **garantir une médiane marché solide pour le modèle
exact** en relançant à la demande une recherche LBC ciblée sur ce modèle, et en versant les prix
trouvés dans `market_observations`. Le système de grounding **déjà en place** s'occupe du reste
(médiane → prompt → marge/prix max), sans nouveau canal ni nouveau texte de prompt.

Bénéfice : résout le démarrage à froid (35 comparables d'un coup au lieu d'attendre d'en croiser 5
par hasard), prix réels du marché de l'occasion FR, **gratuit**, **zéro nouveau site fragile** (on
réutilise le scraper LBC déjà maintenu).

## Approche retenue : alimenter le grounding existant (Approche A)

Écartée — Approche B (canal `market_context` texte séparé alimenté par LBC) : plus de code et
redondant avec la médiane `_grounding_line` déjà existante.

## Flux

```
verify stage (annonce candidate, dig_deeper ou score >= seuil)
  → model = extract_model_name(titre)
  → si model ET lookup dû (pas cherché depuis < 3 j) ET sous le plafond/jour :
        url  = build_comparator_url(model, category)        # recherche LBC du modèle
        ads  = comparator_fetch(url)                         # Chromium partagé (scrape_lock)
        pour chaque ad: brain.record_market_obs(category, prix, ville, model_name=model)
        brain.mark_model_lookup(model)                       # cooldown même si 0 résultat / échec
  → verify_one(...)   # market_grounding(model) renvoie désormais une médiane robuste
  → prompt cite « médiane de N annonces réelles du même modèle : X € »
```

## Composants

### `engine/comparator.py` (nouveau)
- `build_comparator_url(model_name: str, category: str | None = None) -> str`
  Construit une URL de recherche LBC `text=<model>` (triée par prix), scopée à la **catégorie LBC de
  la recherche active** quand elle est dérivable (paramètre `category=NN` extrait du `source_url` de
  la `watchlist_searches`) ; sinon recherche texte simple. Échappe/encode le texte.
- `async def fetch_model_comparables(model_name, scrape_fn, category=None) -> list[dict]`
  Appelle `scrape_fn(url)` (qui retourne déjà des ads `{title, price, city, url, …}`) et renvoie la
  liste d'ads. Pas d'effet de bord (l'enregistrement en base est fait par l'appelant).

### Cache par modèle — `engine/db.py`
- Nouvelle table :
  ```sql
  CREATE TABLE IF NOT EXISTS model_lookup (
      model_name TEXT PRIMARY KEY,
      fetched_at INTEGER NOT NULL
  );
  ```
- `model_lookup_due(model_name, max_age_days=3, now=None) -> bool`
  True si le modèle n'a jamais été cherché, ou l'a été il y a plus de `max_age_days`.
- `mark_model_lookup(model_name, now=None) -> None`
  Upsert `fetched_at` (`ON CONFLICT(model_name) DO UPDATE`).

### Câblage — `server.py`
- Construit une coroutine `comparator_fetch(model_name, category)` qui :
  - respecte le **verrou de scrape** (`scrape_lock`) — jamais deux navigations en parallèle ;
  - réutilise le Chromium partagé (`get_context`) ;
  - bâtit l'URL via `comparator.build_comparator_url`, ouvre une page, extrait via
    `extract_ads_from_results`, renvoie les ads.
  Même mécanique que `description_fetch` existant.
- L'injecte dans `enrichment_worker(..., comparator_fetch=…)`.

### Orchestration — `engine/enrich.py`
- Au stade vérif, avant `verify_one`, pour le `model_name` de l'annonce candidate :
  - garde-fous : `model_name` non vide **ET** `brain.model_lookup_due(model_name)` **ET** plafond
    journalier non atteint ;
  - exécute `comparator_fetch`, enregistre chaque prix dans `market_observations`, puis
    `mark_model_lookup` ;
  - **best-effort** : tout échec (captcha Datadome, timeout, 0 résultat) → on log une ligne, on
    appelle quand même `mark_model_lookup` (cooldown anti-rafale) et on continue avec les données
    disponibles.
- Plafond journalier de recherches comparatives (compteur module-level, reset le lendemain), défaut
  généreux (≈ 100/j), configurable via `.env` (`COMPARATOR_DAILY_CAP`).

## Garde-fous anti-blocage (Datadome)

- Recherche comparative **sérialisée** par `scrape_lock` (aucune navigation parallèle).
- **Cache 3 j/modèle** : un modèle déjà vu n'est pas re-cherché → après chauffe, peu de navigations.
- **Plafond/jour** comme soupape de sécurité.
- Cooldown sur échec (via `mark_model_lookup` appelé même en cas d'échec).

## Nettoyage (retrait de la voie Gemini web, désormais inutile)

À supprimer (ajoutés dans les commits `7a80c4d` / `4c3c69d`) :
- `engine/researcher.py` ;
- `GeminiClient.generate_text` + injection `googleSearch` (`engine/llm_client.py`) ;
- `LLMRouter.generate_text` + stage `"research"` (`engine/router.py`) ;
- `research_model` (`engine/config.py`) + `GEMINI_RESEARCH_MODEL` (`.env.example`) ;
- table `search_market_context` + `get/set_market_context` (`engine/db.py`) ;
- param `market_context` de `verify_one` (`engine/cascade.py`) et de `build_verify_prompt`
  + bloc `_market_context_block` (`engine/prompts.py`) ;
- bloc recherche + back-off `_research_cooldown` dans `engine/enrich.py` ;
- tests associés (`test_engine_researcher.py`, tests `generate_text`/`market_context`/research).

`build_searches_lookup` propage déjà l'objet search complet (incluant `category` via `source_url`/
champs) — on conserve cette propagation (utile pour scoper la catégorie de comparaison).

## Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Captcha / timeout / scrape vide | log 1 ligne, `mark_model_lookup` (cooldown), vérif continue sans nouveaux comparables |
| Plafond/jour atteint | on saute la recherche, vérif continue sur le grounding existant |
| `extract_model_name` vide/vague | pas de recherche (on garde le grounding catégorie) |
| Supabase/réseau | inchangé (la recherche ne touche que SQLite + Chromium) |

## Limitations connues (assumées)

- Prix LBC = prix **demandés** (invendus), pas prix vendus → déjà compensé par la décote 15-30 %
  dans le prompt de vérif.
- Qualité dépendante de `extract_model_name` (titres vagues → recherche bruitée). Comportement
  existant du grounding, non aggravé.

## Plan de test

**Unitaires (mockés) :**
- `comparator.build_comparator_url` : encode le modèle, scope la catégorie quand fournie.
- `comparator.fetch_model_comparables` : avec un `scrape_fn` factice → renvoie les ads.
- `db.model_lookup_due` / `mark_model_lookup` : neuf → dû ; récent → pas dû ; > 3 j → dû ; upsert.
- `enrich` : annonce candidate → 1 recherche, prix enregistrés dans `market_observations`, lookup
  marqué ; 2ᵉ annonce même modèle → **pas** de 2ᵉ recherche (cache) ; échec recherche → vérif
  continue + lookup marqué ; plafond/jour atteint → pas de recherche.
- Suppression des tests de la voie Gemini web.

**Validation manuelle (`python server.py --auto`) :**
1. Au 1ᵉʳ modèle candidat : log « recherche comparative LBC pour le modèle … ».
2. 2ᵉ annonce du même modèle : pas de nouvelle recherche (cache hit).
3. Médiane visible dans le prompt/explication (« médiane de N annonces réelles : X € »).
4. Pas de rafale de navigations ; pas de captcha déclenché en boucle.
