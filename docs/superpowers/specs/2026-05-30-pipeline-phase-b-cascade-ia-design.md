# Pipeline de revente — Phase B : la cascade IA — Design

- **Date** : 2026-05-30
- **Projet** : LBC DealFinder Hub (`lbc-hub`)
- **Statut** : Spec validée (brainstorming terminé, prête pour le plan d'implémentation)
- **Auteur** : Claude (décisions techniques) + Tristan (produit/UX)
- **Branche cible** : `feature/pipeline-phase-b-ia`
- **Spec parente** : `docs/superpowers/specs/2026-05-29-pipeline-revente-opportunites-design.md` (§6 cascade IA)
- **Phase précédente** : Phase A livrée et mergée (`server.py --auto` écrit des opportunités **brutes**).

---

## 1. Objectif

Brancher la **cascade IA** par-dessus le moteur autonome de la Phase A : enrichir chaque
opportunité (catégorie 🔴/🟡/⚫, score, prix marché estimé, marge € + %, prix max d'achat,
détection de lot, signaux, verdict photo) **avant** qu'elle n'apparaisse dans Supabase, le tout
en respectant les **forfaits API gratuits** et sans casser l'API HTTP, le scrape manuel, ni les
62 tests de la Phase A.

Phase A écrivait des opportunités brutes (champs IA = `null`). **Phase B remplit ces champs.**

---

## 2. Décisions de brainstorming (entrées de conception)

| # | Décision | Choix retenu |
|---|---|---|
| B-01 | **Démarrage budget** | **100 % gratuit** au départ (Flash-Lite). Le Pro est conçu pluggable mais **désactivé** (cf. B-04). |
| B-02 | **Quand une opportunité apparaît** | **Seulement une fois analysée** : Supabase ne reçoit jamais d'opportunité brute. L'apparition est conditionnée au **triage** (catégorie + score), rapide. |
| B-03 | **Architecture du flux** | **Cascade découplée** : le scrape dépose les annonces neuves dans une **file locale SQLite** ; un **worker IA séparé** vide la file, exécute la cascade, et écrit l'opportunité **notée** dans Supabase. Le scrape ne bloque jamais sur l'IA. |
| B-04 | **Qui peut déclarer 🔴 urgent** | **Seul le « vérificateur » (tier Pro) peut promouvoir en 🔴.** Le trieur gratuit ne classe qu'en 🟡/⚫. ⚠️ **Pro actuellement SUSPENDU** (Tristan n'a pas accès au compte Pro) → construit pluggable, désactivé. Tant que Pro absent : enrichissement sur Flash gratuit mais **plafond 🟡** (zéro faux « urgent »). Réglage `MIN_TIER_FOR_URGENT`. |
| B-05 | **SDK vs REST** | **REST via `aiohttp`** (déjà présent), sortie JSON stricte (`responseMimeType` + `responseSchema`). **Zéro nouvelle dépendance**, cohérent avec `engine/supa.py`. |
| B-06 | **Priorité géographique** | **Hors périmètre Phase B** (dépend de `member_settings`, Phase C/D). Pas de table des communes embarquée ici. |
| B-07 | **Grounding prix marché** | Médiane locale par catégorie (`market_observations`) injectée dans le prompt du vérificateur. Scrape de comparaison ciblé des 🔴 = **tâche optionnelle** en fin de plan. |

### Modèles Gemini vérifiés en LIVE (30/05/2026)

| Étage | Modèle (ID exact) | Statut | Notes |
|---|---|---|---|
| Triage | `gemini-3.1-flash-lite` | Stable, free tier (~1 500 req/jour, 30 RPM) | Gère la vision |
| Vérif (cible) | `gemini-3.1-pro-preview` (ou `gemini-2.5-pro` stable) | Payant (crédits Cloud) | **Suspendu** (B-04) |
| Vérif (intérim gratuit) | `gemini-3.5-flash` ou `gemini-3.1-flash-lite` | Free tier | Plafond 🟡 tant que Pro absent |
| Photo | `gemini-3.1-flash-lite` (vision) | Free tier | 🔴 uniquement |

> ⚠️ Les IDs de modèles et quotas free tier **changent vite** (Google a coupé 50-80 % en déc. 2025).
> Les modèles sont configurables via `.env` ; les quotas réels ne sont visibles que dans le compte
> AI Studio de Tristan. **Re-vérifier en LIVE** au moment de l'implémentation.

---

## 3. Architecture

### 3.1 Vue d'ensemble

```
SCRAPE (Phase A, intact)         WORKER IA (Phase B, nouveau)                  SUPABASE
────────────────────────         ─────────────────────────────                ────────
process_search trouve les   ─▶  pending_enrichment        ─▶  ① TRIEUR (gratuit)   ─▶  insert opportunité
annonces neuves/baissées         (file locale SQLite)          batch 10-20 → 🟡/⚫     DÉJÀ notée (jamais brute)
  → dépose au lieu d'écrire                                        │ score, "creuser?"
    directement                                                     ▼ (candidates)
                                                              ② VÉRIFICATEUR (tier Pro/Flash)
                                                              marge €/%, prix max, lot,
                                                              signaux + comparables réels
                                                              → 🔴 SEULEMENT si tier ≥ Pro
                                                                    │
                                                                    ▼ (🔴 uniquement)
                                                              ③ PHOTO (vision, gratuit)
                                                              état réel, signaux arnaque
```

### 3.2 Le pivot vs Phase A

En Phase A, `process_search` appelait `supa.insert_opportunity(payload_brut)`. En Phase B,
**le démon injecte une destination différente** : un **sink local** (interface identique
`insert_opportunity(payload)`) qui écrit dans la table SQLite `pending_enrichment` au lieu de
Supabase. Le code de `process_search` et **ses tests ne changent pas** (ils injectent un
`FakeSupa`). Seul le câblage dans `engine/bootstrap.py` / `server.py --auto` change.

Le **worker IA** (`engine/enrich.py`) est une 2ᵉ coroutine de la boucle de fond : il draine
`pending_enrichment`, exécute la cascade, et écrit dans le **vrai** Supabase l'opportunité enrichie.

> **Invariant respecté** : le scrape reste rapide et découplé ; un quota IA épuisé ne bloque
> jamais la détection (dégradation gracieuse, §6).

### 3.3 Modules (responsabilité unique, injection de dépendances)

| Fichier | Responsabilité | Action |
|---|---|---|
| `engine/llm_client.py` | `GeminiClient` : appel REST `generateContent` (texte + vision), parsing JSON strict, gestion erreurs/timeouts | Create |
| `engine/router.py` | `LLMRouter` : registre des modèles + tier + quotas, comptage `llm_usage`, sélection/bascule, **gate 🔴 sur tier** | Create |
| `engine/prompts.py` | Templates de prompt + `responseSchema` par étage (triage / vérif / photo) | Create |
| `engine/grounding.py` | `market_grounding(brain, categorie)` → médiane/échantillon de prix réels | Create |
| `engine/cascade.py` | `run_cascade(ad, router, brain)` : orchestre les 3 étages, calcule marge/prix max, applique seuils | Create |
| `engine/enrich.py` | `enrichment_worker` : draine `pending_enrichment`, lance la cascade, écrit l'opportunité enrichie via `Supa` | Create |
| `engine/parse.py` | `+ extract_category(url)` (pur) | Modify |
| `engine/db.py` | `+ tables llm_usage, pending_enrichment` + méthodes (queue/peek/delete, usage inc/count) ; `record_market_obs` déjà présent | Modify |
| `engine/config.py` | `+ GEMINI_API_KEY` (optionnel), IDs de modèles, `MIN_TIER_FOR_URGENT`, plafonds | Modify |
| `engine/supa.py` | `+ update_opportunity` si besoin (sinon upsert `on_conflict=ad_id` suffit) | Modify |
| `engine/bootstrap.py` / `server.py` | câbler le sink local + démarrer `enrichment_worker` en parallèle de `run_engine` sous `--auto` | Modify |
| `engine/sink.py` | `LocalSink` : interface `insert_opportunity` → `brain.queue_pending` | Create |
| `supabase/migrations/2026-05-30-phase-b-*.sql` | **uniquement si** une colonne manque (à vérifier ; colonnes IA déjà créées en Phase A) | Create (conditionnel) |
| `tests/test_engine_*.py` | unitaires (IA simulée) + script de validation LIVE | Create |
| `CLAUDE.md` | documenter la cascade + le Pro suspendu | Modify |

---

## 4. La cascade IA (détail des étages)

### Étage 0 — Pré-filtre règles (déjà fait, Phase A)
`engine/prefilter.py` : prix > 0, sous `price_max`, hors `exclude_keywords`. Zéro IA. Inchangé.

### Étage 1 — Triage groupé (trieur, gratuit)
- **Entrée** : 10-20 annonces d'une même file (titre + prix + ville + catégorie + médiane marché).
- **Modèle** : `gemini-3.1-flash-lite` (tier `triage`).
- **Sortie JSON par annonce** : `{ category: "interesting"|"passable", score: 0-100, reason: str, dig_deeper: bool }`.
- **Contrainte dure** : le trieur **ne peut JAMAIS renvoyer `urgent`** (validé côté code, pas seulement côté prompt). Une réponse `urgent` du trieur est rabaissée à `interesting`.
- Économie : ÷10-20 d'appels.

### Étage 2 — Vérification approfondie (vérificateur)
- **Entrée** : 1 annonce candidate (`dig_deeper=true` ou score élevé) + comparables réels (grounding).
- **Modèle** : tier `pro` si dispo (`MIN_TIER_FOR_URGENT="pro"`), sinon meilleur free (`flash`).
- **Sortie JSON** : `{ refined_score, est_market_price, signals[], is_lot, lot_unit_price, lot_notes, explanation }`.
- **Calcul déterministe (code, pas IA)** à partir de `est_market_price`, `price`, et des seuils de la recherche :
  - `est_margin_eur = est_market_price − price`
  - `est_margin_pct = est_margin_eur / price × 100`
  - `max_buy_price = est_market_price − max(min_margin_eur, price × min_margin_pct/100)`
- **Promotion 🔴** : `category = "urgent"` **ssi** `refined_score ≥ seuil` **ET** `est_margin_eur ≥ min_margin_eur` **ET** `est_margin_pct ≥ min_margin_pct` **ET** `tier_du_modèle ≥ MIN_TIER_FOR_URGENT`. Sinon plafonné à 🟡.

### Étage 3 — Analyse photo (vision, gratuit)
- **Déclenché** : sur les 🔴 uniquement.
- **Entrée** : octets de l'image (téléchargés sur le PC, jamais stockés), via le CDN LBC.
- **Modèle** : `gemini-3.1-flash-lite` vision.
- **Sortie** : `photo_verdict` (texte) : état réel, incohérences, signaux d'arnaque. **N'annule pas** le 🔴 mais l'enrichit (un signal d'arnaque fort peut rétrograder — règle simple côté code).

### Timing d'écriture Supabase (lève l'ambiguïté B-02)
- **Écriture** de l'opportunité **dès la fin du triage** (Étage 1) : elle apparaît avec sa
  catégorie 🟡/⚫ + score (jamais brute). Une 🟡/⚫ non-candidate (`dig_deeper=false`) s'arrête là.
- **Mise à jour en place** (upsert `on_conflict=ad_id`) après l'Étage 2 (marge, prix max, promotion
  éventuelle en 🔴) puis l'Étage 3 (verdict photo). La carte est déjà visible et s'enrichit.

### Seuils de rentabilité
- Par recherche : `watchlist_searches.min_margin_eur` / `min_margin_pct` (colonnes déjà créées en Phase A).
- **Défauts si null** : `min_margin_eur = 30`, `min_margin_pct = 30`, `seuil_score_urgent = 75` (configurables `.env`).

---

## 5. Le routeur (`LLMRouter`)

- **Registre de modèles** : chaque modèle a `{ id, tier (triage|flash|pro), provider, rpd, rpm }`.
- **Comptage** : table SQLite `llm_usage(provider, model, day, request_count, token_count)`. Reset implicite par `day` (minuit Pacifique → on stocke la date Pacifique).
- **Sélection** : `route(stage)` rend le modèle le moins cher disponible pour l'étage ; si quota épuisé → bascule (provider de réserve type Groq, pluggable) ; si tout épuisé → **prioriser les 🔴**, reporter le reste au reset (dégradation gracieuse).
- **Gate 🔴** : le routeur expose `tier_for(stage)` ; la cascade ne promeut en `urgent` que si `tier ≥ MIN_TIER_FOR_URGENT`.
- **Extensibilité** : interface `LLMProvider` (même philosophie que `PlatformScraper`). En Phase B : provider Gemini implémenté ; Groq/OpenRouter en réserve (interface seulement).

---

## 6. Résilience & dégradation gracieuse

- **File `pending_enrichment`** : si le worker tombe ou que les quotas sont épuisés, les annonces attendent dans la file locale (rien n'est perdu). Au retour, le worker reprend.
- **Quotas épuisés** : triage prioritaire sur les candidates à fort signal ; le reste attend le reset.
- **Outbox Supabase** (déjà en Phase A) : si Supabase/Internet est down au moment d'écrire l'opportunité enrichie, on passe par l'outbox existante.
- **Un échec sur une annonce n'arrête jamais le worker** (try/except par annonce, comme `run_engine`).
- **Idempotence** : upsert `on_conflict=ad_id` → ré-enrichir une annonce ne crée pas de doublon.

---

## 7. Données

### 7.1 SQLite local (ajouts)

```
pending_enrichment(id PK, ad_id, search_id, payload TEXT, queued_at, retries)  -- file du worker
llm_usage(provider, model, day TEXT, request_count, token_count)               -- pour le routeur
market_observations(categorie, prix, ville, observed_at)                        -- déjà présent, désormais alimenté
```

### 7.2 Supabase

- **Table `opportunities`** : toutes les colonnes IA existent déjà (Phase A, nullable). **Aucune migration de colonne attendue.** À confirmer en début de plan ; si une colonne manque, mini-migration `2026-05-30-phase-b-*.sql`.
- **`watchlist_searches.min_margin_eur` / `min_margin_pct`** : déjà créées en Phase A. OK.
- Écriture **moteur** via `service_role` (inchangé). RLS frontend inchangé.

---

## 8. Tests

### 8.1 Unitaires (IA simulée — rapides, hors-ligne)
- `extract_category` (URLs variées).
- `LLMRouter` : sélection, comptage `llm_usage`, bascule quota épuisé, **gate Pro** (free → jamais 🔴).
- `grounding` : médiane/échantillon corrects, cas vide (cold-start).
- `cascade` : avec un `FakeRouter` rendant des réponses canned → vérifie le calcul marge/prix max, la promotion 🔴 (gate), le plafond 🟡 quand Pro absent, le rabaissement d'un `urgent` venu du trieur.
- `enrichment_worker` : draine la file, écrit l'opportunité enrichie, idempotence, résilience (échec par item).
- `db` : `pending_enrichment` queue/peek/delete, `llm_usage` inc/count.
- **Non-régression** : les 62 tests Phase A restent verts.

### 8.2 Validation LIVE (obligatoire avant « fini »)
- Vrais appels `gemini-3.1-flash-lite` (free tier) sur de **vraies** opportunités issues du moteur.
- Vérifier : JSON bien formé, catégories cohérentes, marges plausibles vs marché, plafond 🟡 (Pro absent), comptage `llm_usage` correct, aucun dépassement de quota silencieux.
- Leçon Phase A : seul le test live révèle les surprises (format réel des réponses, quotas réels).

---

## 9. Périmètre — ce qui N'EST PAS dans la Phase B

- **Notifications / bot Telegram** → Phase C.
- **Hub (onglet Opportunités, « Je contacte »)** → Phase C.
- **Priorité géographique / table communes / `member_settings`** → Phase C/D (B-06).
- **Pro réellement actif** → suspendu jusqu'à accès au compte Pro (B-04) ; le code est prêt.
- **Scrape de comparaison ciblé des 🔴** → tâche **optionnelle** en fin de plan (sinon grounding = médiane locale seule).

---

## 10. Ce qui NE change PAS

- API HTTP de `server.py`, endpoints, SSE, import JSON, scrape manuel : **intacts**.
- Moteur Phase A (`run_engine`, dédup, baisse de prix, outbox) : **intact** ; seul le sink injecté change sous `--auto`.
- Frontend / SDK JS / RLS : **inchangés**.
- Un seul Chromium partagé (`scrape_lock`) : inchangé (la photo télécharge via HTTP, pas via le navigateur).

---

## 11. Journal des décisions

Voir tableau §2 (B-01 → B-07). Décision la plus structurante : **B-04** (Pro = seul juge du 🔴, suspendu)
+ **B-03** (cascade découplée via file locale). Mémoire projet : `phase-b-pro-verifier-suspendu`.

---

## 12. Prochaine étape

Rédiger le **plan d'implémentation Phase B** via la skill `writing-plans`, au format du plan Phase A
(tâches TDD, fichiers, étapes, commits), puis exécuter en `subagent-driven-development`.
