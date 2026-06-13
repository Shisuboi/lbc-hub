# Comparateur de prix LBC ciblé — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la recherche web Gemini (payante) par une recherche Leboncoin ciblée sur le modèle exact d'une annonce, qui alimente le grounding marché déjà en place — gratuit, robuste, zéro nouveau site.

**Architecture:** Au stade vérif, le worker extrait le modèle de l'annonce, lance (si modèle réel + pas en cache + sous le plafond/jour) une recherche LBC ciblée via le Chromium partagé, verse les prix trouvés dans `market_observations`, et laisse le grounding existant (`market_grounding` + `_grounding_line`) injecter la médiane dans les prompts. Un cache SQLite par modèle (3 j) et un plafond journalier bornent le risque Datadome.

**Tech Stack:** Python 3.11, aiohttp, Playwright (Chromium partagé), SQLite (`lbc_brain.sqlite3`), pytest (`asyncio_mode=auto`).

**Spec:** `docs/superpowers/specs/2026-06-13-comparateur-prix-lbc-design.md`

---

## Structure des fichiers

**Créés :**
- `engine/comparator.py` — helpers purs : `lbc_category_from_url`, `build_comparator_url`.
- `tests/test_engine_comparator.py` — tests des helpers.
- `tests/test_engine_model_lookup.py` — tests du cache par modèle.

**Modifiés :**
- `engine/db.py` — RETIRE `search_market_context` + `get/set_market_context` ; AJOUTE table `model_lookup` + `model_lookup_due` / `mark_model_lookup`.
- `engine/llm_client.py` — RETIRE `generate_text`.
- `engine/router.py` — RETIRE `generate_text` + stage `"research"`.
- `engine/config.py` — RETIRE `research_model`.
- `engine/cascade.py` — RETIRE le param `market_context` de `verify_one`.
- `engine/prompts.py` — RETIRE le bloc/param `market_context` de `build_verify_prompt`.
- `engine/enrich.py` — RETIRE le bloc recherche Gemini + `_research_cooldown` ; AJOUTE le bloc comparateur LBC + plafond/jour ; nouveau param `comparator_fetch`.
- `server.py` — câble une closure `comparator_fetch` (Chromium partagé + `scrape_lock`) dans `enrichment_worker`.
- `.env.example` — RETIRE `GEMINI_RESEARCH_MODEL` ; AJOUTE `COMPARATOR_DAILY_CAP`.

**Supprimés :**
- `engine/researcher.py`, `tests/test_engine_researcher.py`, `tests/test_engine_market_context.py`.

> Note d'archi (raffinement vs spec) : `comparator.py` ne contient que les helpers d'URL **purs** (testables sans réseau). La composition « URL + scrape » vit dans une closure de `server.py` (même patron que `description_fetch` existant), injectée sous le nom `comparator_fetch`. Pas de `fetch_model_comparables` intermédiaire (couche non testable inutile).

---

## Task 1 : Retirer la voie Gemini web (retour au comportement antérieur côté recherche)

Suppression pure de tout ce qui a été ajouté pour le grounding Google Search. Aucune logique nouvelle. À la fin, la suite de tests passe (la cascade fonctionne comme avant l'ajout de la recherche web).

**Files:**
- Delete: `engine/researcher.py`, `tests/test_engine_researcher.py`, `tests/test_engine_market_context.py`
- Modify: `engine/llm_client.py`, `engine/router.py`, `engine/config.py`, `engine/cascade.py`, `engine/prompts.py`, `engine/enrich.py`, `.env.example`
- Modify (tests) : `tests/test_engine_llm_client.py`, `tests/test_engine_router.py`, `tests/test_engine_prompts.py`, `tests/test_engine_enrich.py`

- [ ] **Step 1 : Supprimer les fichiers dédiés à la recherche Gemini**

```bash
git rm engine/researcher.py tests/test_engine_researcher.py tests/test_engine_market_context.py
```

- [ ] **Step 2 : `engine/llm_client.py` — retirer `generate_text`**

Supprimer entièrement la méthode `generate_text` (de `async def generate_text(...)` jusqu'à son `return text, tokens`). Le fichier doit se terminer après `generate_json` (la méthode qui retourne `json.loads(text), tokens`).

- [ ] **Step 3 : `engine/router.py` — retirer `generate_text` et le stage `"research"`**

Dans `_candidates`, supprimer le bloc :

```python
        if stage == "research":
            # Recherche web : on garde un modèle bon marché (verify_model par défaut, sinon flash-lite).
            return [s.get("research_model") or s.get("verify_model") or "gemini-3.1-flash-lite"]
```

(la méthode se termine donc par le `if stage == "verify": ...` suivi de `raise ValueError(f"stage inconnu: {stage}")`).

Supprimer ensuite entièrement la méthode `async def generate_text(self, stage, prompt, use_search=False):` (jusqu'à son `raise QuotaExhausted(...)`). Le fichier se termine après `generate`.

- [ ] **Step 4 : `engine/config.py` — retirer `research_model`**

Supprimer la ligne :

```python
        # Market Researcher (Google Search) : modèle dédié optionnel ; sinon = verify_model.
        "research_model": cfg.get("GEMINI_RESEARCH_MODEL") or None,
```

- [ ] **Step 5 : `engine/prompts.py` — retirer le contexte marché web**

Supprimer la fonction `_market_context_block` en entier. Dans `build_verify_prompt`, remettre la signature et le corps d'origine :

```python
def build_verify_prompt(ad: dict, grounding: dict) -> str:
    return (
        "Nous sommes en juin 2026. CALIBRAGE ESSENTIEL pour estimer est_market_price :\n"
        "① Tes prix internes sont trop élevés : divise ton estimation par 2 à 3 pour les smartphones/"
        "tablettes de 2-4 ans, par 1,5 à 2 pour les PC/Mac de 3-5 ans, par 1,3 à 1,5 pour les consoles. "
        "Penche toujours vers l'estimation basse.\n"
        "② est_market_price = prix auquel l'objet se VENDRA réellement, pas le prix demandé sur LBC. "
        "Les annonces LBC visibles sont des invendus (prix trop élevés). L'acheteur final paiera "
        "15-30 % EN DESSOUS de ce qu'il voit affiché sur LBC. Intègre cette décote dans ton estimation.\n"
        "Si le prix marché de référence ci-dessous est fourni, il a TOUJOURS priorité — utilise-le "
        "comme ancre principale. S'il est INCONNU, estime à partir de tes connaissances du modèle "
        "exact (gamme, année, capacité, état typique) en appliquant le calibrage ci-dessus.\n"
        "Tu vérifies une annonce Leboncoin pour de la revente. Estime le prix de revente réaliste "
        "(est_market_price), un score affiné 0-100, les signaux d'opportunité, et si c'est un LOT "
        "(is_lot, prix unitaire, notes).\n"
        "GARDE-FOU PRIX DÉRISOIRE : prix très bas = probablement cassé/pièces/arnaque. "
        "Dans ce cas est_market_price = valeur pièces (faible), PAS prix sain. Baisse le score, "
        "ajoute signal « prix anormalement bas : suspicion pièces/cassé ».\n"
        "ÉCHELLE DE SCORE — sois STRICT, les scores élevés déclenchent des notifications :\n"
        "  85-100 = EXCELLENTE affaire, TOUS ces critères réunis : (a) marge nette estimée ≥ 30 % "
        "ET ≥ 30 € après achat ; (b) objet clairement fonctionnel (état précisé, pas de doute) ; "
        "(c) prix demandé significativement sous la médiane LBC (> 15 %) ; (d) aucun signal d'arnaque. "
        "Si UN SEUL de ces critères est douteux, le score ne peut PAS dépasser 79.\n"
        "  60-79 = bonne opportunité à creuser, marge réelle probable mais incertaine.\n"
        "  40-59 = marge faible ou trop d'inconnues.\n"
        "  0-39  = pas une affaire (prix dérisoire/gonflé, objet HS, arnaque probable).\n"
        f"{_grounding_line(grounding)}\n\n"
        f"Annonce : {ad.get('title','')} | prix demandé {ad.get('price',0):.0f} € | "
        f"{ad.get('city','')} | catégorie {ad.get('category','?')}."
        + (f"\nDescription vendeur : {ad['description'][:800]}" if ad.get('description') else
           "\nDescription vendeur : non disponible.")
    )
```

- [ ] **Step 6 : `engine/cascade.py` — retirer le param `market_context` de `verify_one`**

Remettre :

```python
async def verify_one(ad: dict, search: dict, router, brain, urgent_score_threshold: float) -> dict:
    """Étage 2 : vérification fine d'une annonce. Seul un tier >= min peut donner 🔴."""
    model = extract_model_name(ad.get("title", ""))
    grounding = market_grounding(brain, ad.get("category"), model_name=model)
    prompt = build_verify_prompt(ad, grounding)
```

- [ ] **Step 7 : `engine/enrich.py` — retirer l'import, le back-off et le bloc recherche**

Retirer l'import `from engine.researcher import run_market_research` et `import time`.
Retirer le bloc module-level `_research_cooldown` / `_RESEARCH_COOLDOWN_S` (et son commentaire).
Dans `enrich_once`, supprimer tout le bloc « Market Researcher … » (de `market_context = None` jusqu'à la fin du `if search_id and query_title:`), et remettre l'appel direct :

```python
            try:
                ia = await verify_one(ad, search, router, brain, urgent_score_threshold=threshold)
```

- [ ] **Step 8 : `.env.example` — retirer la clé recherche**

Supprimer la ligne `# GEMINI_RESEARCH_MODEL=...`.

- [ ] **Step 9 : Tests — retirer les tests de la voie Gemini web**

- `tests/test_engine_llm_client.py` : supprimer `mock_gemini_text`, `test_generate_text_returns_concatenated_text`, `test_generate_text_injects_google_search_tool`, `mock_gemini_429`, `test_generate_text_surfaces_error_body_on_http_error`. Garder les 2 tests `generate_json`.
- `tests/test_engine_router.py` : supprimer `FakeTextProvider`, `test_generate_text_research_stage_uses_verify_model_and_search`, `test_generate_text_counts_usage_and_respects_quota`.
- `tests/test_engine_prompts.py` : supprimer `test_verify_prompt_injects_market_context_when_provided` et `test_verify_prompt_no_market_block_when_context_absent`.
- `tests/test_engine_enrich.py` : supprimer la classe `ResearchRouter`, le helper `_verify_router`, et les tests `test_enrich_runs_research_on_cache_miss_and_stores_it`, `test_enrich_uses_cached_research_no_second_web_call`, `test_enrich_survives_research_failure`, `test_enrich_research_backs_off_after_failure`.

- [ ] **Step 10 : Lancer toute la suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (la suite revient au périmètre d'avant la recherche web, ~206 tests).

- [ ] **Step 11 : Commit**

```bash
git add -A
git commit -m "refactor(engine): retire la voie de recherche web Gemini (grounding Google non gratuit)"
```

---

## Task 2 : Cache par modèle dans `engine/db.py`

**Files:**
- Modify: `engine/db.py`
- Test: `tests/test_engine_model_lookup.py`

- [ ] **Step 1 : Écrire le test du cache**

Créer `tests/test_engine_model_lookup.py` :

```python
"""Cache « modèle déjà cherché récemment » pour borner les recherches comparatives LBC."""
from engine.db import Brain

_DAY = 86400


def make_brain():
    return Brain(":memory:")


def test_due_when_never_searched():
    b = make_brain()
    assert b.model_lookup_due("ThinkPad X1") is True


def test_not_due_right_after_mark():
    b = make_brain()
    b.mark_model_lookup("ThinkPad X1", now=1000)
    assert b.model_lookup_due("ThinkPad X1", now=1000) is False


def test_due_again_after_max_age():
    b = make_brain()
    b.mark_model_lookup("ThinkPad X1", now=1000)
    assert b.model_lookup_due("ThinkPad X1", max_age_days=3, now=1000 + 4 * _DAY) is True


def test_not_due_within_max_age():
    b = make_brain()
    b.mark_model_lookup("ThinkPad X1", now=1000)
    assert b.model_lookup_due("ThinkPad X1", max_age_days=3, now=1000 + 2 * _DAY) is False


def test_mark_is_idempotent_upsert():
    b = make_brain()
    b.mark_model_lookup("ThinkPad X1", now=1000)
    b.mark_model_lookup("ThinkPad X1", now=5000)  # ré-écrit fetched_at
    assert b.model_lookup_due("ThinkPad X1", max_age_days=3, now=5000) is False
    assert b.model_lookup_due("ThinkPad X1", max_age_days=3, now=1000 + 2 * _DAY) is False
```

- [ ] **Step 2 : Lancer le test (échec attendu)**

Run: `python -m pytest tests/test_engine_model_lookup.py -q`
Expected: FAIL avec `AttributeError: 'Brain' object has no attribute 'model_lookup_due'`.

- [ ] **Step 3 : Ajouter la table dans `SCHEMA` (`engine/db.py`)**

Juste avant la fermeture `"""` de la constante `SCHEMA` (après le bloc `telegram_poll_offset` / `INSERT OR IGNORE …`), ajouter :

```sql

CREATE TABLE IF NOT EXISTS model_lookup (
    model_name TEXT PRIMARY KEY,
    fetched_at INTEGER NOT NULL
);
```

- [ ] **Step 4 : Ajouter les méthodes (`engine/db.py`)**

Ajouter ces deux méthodes dans la classe `Brain` (par ex. juste avant `def inc_usage`) :

```python
    def model_lookup_due(self, model_name: str, max_age_days: int = 3, now: int | None = None) -> bool:
        """True si ce modèle n'a jamais fait l'objet d'une recherche comparative, ou il y a plus de
        `max_age_days` jours. Borne la fréquence des recherches LBC ciblées (anti-captcha)."""
        now = int(now if now is not None else time.time())
        row = self.conn.execute(
            "SELECT fetched_at FROM model_lookup WHERE model_name = ?", (model_name,)
        ).fetchone()
        if row is None:
            return True
        return now - row["fetched_at"] > max_age_days * 86400

    def mark_model_lookup(self, model_name: str, now: int | None = None) -> None:
        """Enregistre qu'une recherche comparative vient d'être faite pour ce modèle (upsert)."""
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO model_lookup (model_name, fetched_at) VALUES (?, ?) "
            "ON CONFLICT(model_name) DO UPDATE SET fetched_at = excluded.fetched_at",
            (model_name, now),
        )
        self.conn.commit()
```

- [ ] **Step 5 : Lancer le test (succès attendu)**

Run: `python -m pytest tests/test_engine_model_lookup.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6 : Commit**

```bash
git add engine/db.py tests/test_engine_model_lookup.py
git commit -m "feat(db): cache model_lookup (borne les recherches comparatives LBC, 3j/modele)"
```

---

## Task 3 : `engine/comparator.py` (helpers d'URL purs)

**Files:**
- Create: `engine/comparator.py`
- Test: `tests/test_engine_comparator.py`

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_engine_comparator.py` :

```python
from engine.comparator import lbc_category_from_url, build_comparator_url


def test_category_extracted_from_source_url():
    url = "https://www.leboncoin.fr/recherche?category=15&text=ordinateur&sort=time"
    assert lbc_category_from_url(url) == "15"


def test_category_none_when_absent_or_empty():
    assert lbc_category_from_url("https://www.leboncoin.fr/recherche?text=ordinateur") is None
    assert lbc_category_from_url(None) is None
    assert lbc_category_from_url("") is None


def test_build_url_encodes_model_text():
    url = build_comparator_url("ThinkPad X1 Carbon")
    assert url.startswith("https://www.leboncoin.fr/recherche?")
    assert "text=ThinkPad+X1+Carbon" in url or "text=ThinkPad%20X1%20Carbon" in url
    assert "category=" not in url


def test_build_url_scopes_category_when_provided():
    url = build_comparator_url("ThinkPad X1", category="15")
    assert "category=15" in url
    assert "text=ThinkPad+X1" in url or "text=ThinkPad%20X1" in url
```

- [ ] **Step 2 : Lancer les tests (échec attendu)**

Run: `python -m pytest tests/test_engine_comparator.py -q`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.comparator'`.

- [ ] **Step 3 : Écrire `engine/comparator.py`**

```python
"""Helpers d'URL pour la recherche comparative Leboncoin (prix d'un modèle exact).

Pur (zéro réseau) → testable. La composition « URL + scrape » vit dans server.py (closure
`comparator_fetch`, même patron que `description_fetch`), qui réutilise le Chromium partagé.
"""
from urllib.parse import urlencode, urlparse, parse_qs

_BASE = "https://www.leboncoin.fr/recherche"


def lbc_category_from_url(source_url: str | None) -> str | None:
    """Extrait le paramètre `category` (numérique LBC) d'une URL de recherche, ou None."""
    if not source_url:
        return None
    qs = parse_qs(urlparse(source_url).query)
    vals = qs.get("category")
    return vals[0] if vals else None


def build_comparator_url(model_name: str, category: str | None = None) -> str:
    """URL de recherche LBC pour un modèle donné, scopée à la catégorie si fournie."""
    params = {"text": model_name}
    if category:
        params["category"] = category
    return f"{_BASE}?{urlencode(params)}"
```

- [ ] **Step 4 : Lancer les tests (succès attendu)**

Run: `python -m pytest tests/test_engine_comparator.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5 : Commit**

```bash
git add engine/comparator.py tests/test_engine_comparator.py
git commit -m "feat(engine): comparator.py (helpers URL recherche LBC ciblee par modele)"
```

---

## Task 4 : Déclencher la recherche comparative dans `engine/enrich.py`

Ajoute, au stade vérif, l'appel comparateur (modèle réel + cache dû + sous plafond/jour), l'enregistrement des prix dans `market_observations`, et le marquage du lookup. Best-effort. Nouveau paramètre `comparator_fetch` (callable async `(model_name, category) -> list[ads]`), défaut `None` (désactivé).

**Files:**
- Modify: `engine/enrich.py`
- Test: `tests/test_engine_enrich.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter dans `tests/test_engine_enrich.py` (après les tests existants, avant les tests Telegram). `ScriptedRouter` et `queue_ad` existent déjà dans ce fichier.

```python
class FakeComparator:
    """Simule la closure comparator_fetch de server.py : compte les appels, renvoie des annonces."""
    def __init__(self, prices=(300.0, 320.0, 280.0, 310.0, 290.0), exc=None):
        self.calls = []
        self.prices = prices
        self.exc = exc

    async def __call__(self, model_name, category=None):
        self.calls.append({"model": model_name, "category": category})
        if self.exc:
            raise self.exc
        return [{"title": f"{model_name} {i}", "price": p, "city": "Paris",
                 "url": "https://www.leboncoin.fr/ad/informatique/1"} for i, p in enumerate(self.prices)]


def _candidate_router():
    return ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "interesting", "score": 80, "dig_deeper": True}],
        verify={"refined_score": 70, "est_market_price": 300.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["flash"],
    )


# NB : on stub `extract_model_name` (via monkeypatch sur le namespace d'enrich) pour rendre les
# tests déterministes — indépendants des heuristiques réelles d'extraction de modèle.


async def test_enrich_fetches_comparables_and_records_observations(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1", url="https://www.leboncoin.fr/ad/informatique/1")
    comp = FakeComparator()
    await enrich_once(brain, supa, _candidate_router(), settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"title": "PC", "source_url": "https://www.leboncoin.fr/recherche?category=15&text=pc",
                                             "min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, comparator_fetch=comp)
    assert len(comp.calls) == 1
    assert comp.calls[0]["model"] == "PS5 Slim"
    assert comp.calls[0]["category"] == "15"           # catégorie dérivée du source_url
    assert brain.model_lookup_due("PS5 Slim") is False  # lookup marqué
    # les prix comparables sont enregistrés comme observations marché
    rows = brain.conn.execute("SELECT COUNT(*) AS c FROM market_observations WHERE prix > 0").fetchone()
    assert rows["c"] >= 5


async def test_enrich_skips_comparator_when_no_model(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: None)  # titre vague
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    comp = FakeComparator()
    await enrich_once(brain, supa, _candidate_router(), settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"title": "PC", "min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, comparator_fetch=comp)
    assert comp.calls == []  # pas de modèle → aucune recherche


async def test_enrich_uses_cache_no_second_comparator_call(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    queue_ad(brain, "2")  # même modèle (stub) que l'annonce 1
    comp = FakeComparator()
    await enrich_once(brain, supa, ScriptedRouter(
        triage_items=[
            {"ad_id": "1", "category": "interesting", "score": 80, "dig_deeper": True},
            {"ad_id": "2", "category": "interesting", "score": 80, "dig_deeper": True},
        ],
        verify={"refined_score": 70, "est_market_price": 300.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["flash"],
    ), settings={"urgent_score_threshold": 75},
        searches_by_id={"s1": {"title": "PS5", "min_margin_eur": 30, "min_margin_pct": 30}},
        image_fetch=None, comparator_fetch=comp)
    # 2 annonces, MÊME modèle → une seule recherche comparative (cache)
    assert len(comp.calls) == 1


async def test_enrich_survives_comparator_failure(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    comp = FakeComparator(exc=RuntimeError("captcha Datadome"))
    n = await enrich_once(brain, supa, _candidate_router(), settings={"urgent_score_threshold": 75},
                          searches_by_id={"s1": {"title": "PS5", "min_margin_eur": 30, "min_margin_pct": 30}},
                          image_fetch=None, comparator_fetch=comp)
    assert n == 1  # la vérif continue malgré l'échec
    assert brain.model_lookup_due("PS5 Slim") is False  # lookup marqué quand même (cooldown)


async def test_enrich_respects_daily_cap(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    comp = FakeComparator()
    await enrich_once(brain, supa, _candidate_router(),
                      settings={"urgent_score_threshold": 75, "comparator_daily_cap": 0},  # plafond 0
                      searches_by_id={"s1": {"title": "PS5", "min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, comparator_fetch=comp)
    assert comp.calls == []  # plafond atteint → aucune recherche
```

- [ ] **Step 2 : Lancer les tests (échec attendu)**

Run: `python -m pytest tests/test_engine_enrich.py -q`
Expected: FAIL (signature `enrich_once` sans `comparator_fetch`, et `_comparator_count` inexistant).

- [ ] **Step 3 : `engine/enrich.py` — imports + état plafond journalier**

En haut, ajouter aux imports :

```python
from engine.parse import extract_category, extract_model_name
from engine.comparator import lbc_category_from_url
```

(`extract_category` est déjà importé ; ajouter `extract_model_name` à la même ligne ou en plus.)

Sous le bloc `_quota_exhausted_day`, ajouter le compteur journalier de recherches comparatives :

```python
# ── Plafond journalier de recherches comparatives LBC (module-level, reset le lendemain) ──
# {jour-iso: nombre de recherches faites}. Borne le risque Datadome même en cas de pic de
# nouveaux modèles. Défaut configurable via settings["comparator_daily_cap"].
_comparator_count: dict = {}


def _comparator_quota_left(cap: int) -> bool:
    """True s'il reste du quota de recherches comparatives aujourd'hui."""
    if cap <= 0:
        return False
    return _comparator_count.get(date.today().isoformat(), 0) < cap


def _bump_comparator_count() -> None:
    day = date.today().isoformat()
    _comparator_count[day] = _comparator_count.get(day, 0) + 1
```

- [ ] **Step 4 : `engine/enrich.py` — signatures `enrich_once` / `enrichment_worker`**

`enrich_once` : ajouter le paramètre `comparator_fetch=None` (après `desc_fetch=None`).

```python
async def enrich_once(brain, supa, router, settings, searches_by_id, image_fetch, batch_size=15, telegram=None, desc_fetch=None, comparator_fetch=None) -> int:
```

`enrichment_worker` : ajouter `comparator_fetch=None` et le transmettre.

```python
async def enrichment_worker(brain, supa, router, settings, fetch_searches, image_fetch,
                            stop_event, pause: float = 5.0, max_loops=None, telegram=None,
                            desc_fetch=None, comparator_fetch=None) -> None:
```

et dans la boucle :

```python
            await enrich_once(brain, supa, router, settings, searches_by_id, image_fetch,
                              telegram=telegram, desc_fetch=desc_fetch, comparator_fetch=comparator_fetch)
```

- [ ] **Step 5 : `engine/enrich.py` — insérer le bloc comparateur avant `verify_one`**

Juste avant le `try:` qui appelle `verify_one` (et après la résolution de `search`), insérer :

```python
            # Comparateur LBC ciblé : si l'annonce a un modèle identifiable, qu'il n'a pas été
            # cherché récemment et qu'on est sous le plafond/jour, on relance une recherche LBC du
            # MODÈLE, et on verse les prix trouvés dans market_observations (le grounding existant
            # s'en sert ensuite). Best-effort : un échec (captcha, timeout) ne casse pas la vérif.
            model_name = extract_model_name(ad.get("title", ""))
            cap = int(settings.get("comparator_daily_cap", 100))
            if (comparator_fetch and model_name and brain.model_lookup_due(model_name)
                    and _comparator_quota_left(cap)):
                category = lbc_category_from_url(search.get("source_url"))
                print(f"🔍 [comparateur] Recherche LBC du modèle « {model_name} » "
                      f"(catégorie {category or 'toutes'})…")
                _bump_comparator_count()
                try:
                    comparables = await comparator_fetch(model_name, category)
                    for c in comparables or []:
                        if c.get("price"):
                            brain.record_market_obs(
                                extract_category(c.get("url") or "") or ad.get("category"),
                                float(c["price"]), c.get("city"), model_name=model_name)
                    print(f"  ✓ [comparateur] {len(comparables or [])} comparable(s) enregistré(s) "
                          f"pour « {model_name} ».")
                except Exception as exc:
                    print(f"[comparateur] échec recherche « {model_name} » "
                          f"({type(exc).__name__}: {exc}) — vérif sur les données existantes")
                finally:
                    brain.mark_model_lookup(model_name)  # cooldown même en cas d'échec/0 résultat
```

- [ ] **Step 6 : Lancer les tests enrich (succès attendu)**

Run: `python -m pytest tests/test_engine_enrich.py -q`
Expected: PASS (tests existants + 5 nouveaux).

- [ ] **Step 7 : Lancer toute la suite**

Run: `python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 8 : Commit**

```bash
git add engine/enrich.py tests/test_engine_enrich.py
git commit -m "feat(enrich): recherche comparative LBC par modele -> market_observations (cache + plafond)"
```

---

## Task 5 : Câbler `comparator_fetch` dans `server.py` + `.env.example`

**Files:**
- Modify: `server.py`, `.env.example`

- [ ] **Step 1 : `server.py` — import du builder d'URL**

Ajouter à côté des imports `engine.*` (près de `from engine.bootstrap import make_scrape_fn, build_searches_lookup`) :

```python
from engine.comparator import build_comparator_url
```

- [ ] **Step 2 : `server.py` — closure `comparator_fetch`**

Dans `start_autonomous_engine`, dans le bloc `if ai["api_key"]:` (là où sont définies `image_fetch`, `fetch_searches`, `description_fetch`), ajouter, après `description_fetch` :

```python
        async def comparator_fetch(model_name: str, category: str | None = None) -> list:
            """Recherche LBC ciblée sur un modèle (Chromium partagé, sérialisé par scrape_lock)."""
            url = build_comparator_url(model_name, category)
            async with _desc_sem:
                if scrape_lock.locked():
                    # le scrape principal a la priorité ; on réessaiera ce modèle plus tard
                    return []
                try:
                    ctx = await get_context()
                    page = await ctx.new_page()
                    try:
                        await page.goto(url, wait_until="domcontentloaded")
                        try:
                            await page.wait_for_selector(RESULTS_CONTAINER_SELECTOR, timeout=8000)
                        except Exception:
                            return []  # blocage/pas de résultats → best-effort, on abandonne ce modèle
                        return await extract_ads_from_results(page)
                    finally:
                        await page.close()
                        await asyncio.sleep(0.5)  # pause Datadome entre navigations
                except Exception as exc:
                    print(f"[comparateur] erreur navigation {url}: {exc}")
                    return []
```

> Note : `comparator_fetch` ne prend PAS `scrape_lock` lui-même (contrairement au scrape principal) — il cède la priorité si le verrou est tenu (comme `description_fetch`), pour ne jamais bloquer le scrape 24/7. `_desc_sem`, `get_context`, `RESULTS_CONTAINER_SELECTOR`, `extract_ads_from_results` sont déjà présents/importés dans `server.py`.

- [ ] **Step 3 : `server.py` — passer `comparator_fetch` au worker**

Remplacer l'appel `enrichment_worker(...)` existant par :

```python
        tasks.append(asyncio.create_task(
            enrichment_worker(brain, supa, router, ai, fetch_searches, image_fetch, stop_event,
                              telegram=telegram, desc_fetch=description_fetch,
                              comparator_fetch=comparator_fetch)
        ))
```

- [ ] **Step 4 : `engine/config.py` — exposer `comparator_daily_cap`**

Dans `ai_settings`, ajouter (par ex. après `default_min_margin_pct`) :

```python
        # Plafond journalier de recherches comparatives LBC (anti-captcha). Défaut 100.
        "comparator_daily_cap": int(_to_float(cfg.get("COMPARATOR_DAILY_CAP"), 100)),
```

- [ ] **Step 5 : `.env.example` — documenter la clé**

Ajouter sous les autres clés IA :

```bash
# COMPARATOR_DAILY_CAP=100                 # nb max de recherches comparatives LBC/jour (anti-captcha)
```

- [ ] **Step 6 : Vérifier que tout importe (pas de test serveur — convention projet)**

Run: `python -c "import server"`
Expected: aucune erreur d'import.

Run: `python -m pytest tests/ -q`
Expected: PASS (la suite complète).

- [ ] **Step 7 : Commit**

```bash
git add server.py engine/config.py .env.example
git commit -m "feat(server): cable comparator_fetch (recherche LBC ciblee) dans enrichment_worker"
```

---

## Validation manuelle finale (après les 5 tasks)

Sur la machine moteur :

```bash
git pull
python server.py --auto
```

1. Au 1ᵉʳ modèle candidat : log `🔍 [comparateur] Recherche LBC du modèle « … »` puis `✓ N comparable(s) enregistré(s)`.
2. 2ᵉ annonce du même modèle : **pas** de nouvelle recherche (cache hit, aucun nouveau log comparateur pour ce modèle).
3. Annonce au titre vague : **aucun** log comparateur.
4. Dans le feed / l'explication d'une opportunité : la médiane marché reflète les comparables (« médiane de N annonces réelles : X € »).
5. Pas de rafale de navigations ; pas de captcha déclenché en boucle.
