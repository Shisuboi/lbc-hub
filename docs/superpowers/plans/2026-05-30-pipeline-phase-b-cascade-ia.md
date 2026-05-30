# Phase B — Cascade IA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brancher la cascade IA (triage groupé → vérification → photo) par-dessus le moteur Phase A : le scrape dépose les annonces neuves dans une file locale, un worker IA séparé les enrichit (catégorie, score, marge, prix max, lot, signaux, photo) et n'écrit dans Supabase que des opportunités **notées** — le tout sur le free tier Gemini, sans casser l'API HTTP, le scrape manuel, ni les 62 tests de la Phase A.

**Architecture:** Modules `engine/` à responsabilité unique, injection de dépendances. Le scrape (`process_search`, inchangé) reçoit un **`LocalSink`** qui met les opportunités brutes en file SQLite (`pending_enrichment`) au lieu de Supabase. Un **`enrichment_worker`** (2ᵉ coroutine sous `--auto`) draine la file, exécute la cascade via un **`LLMRouter`** (pluggable, gate 🔴 sur tier Pro — Pro suspendu), et écrit l'opportunité enrichie via le client `Supa` existant. Stages IA = fonctions pures testées avec un routeur simulé ; appels Gemini = REST `aiohttp` (zéro nouvelle dépendance).

**Tech Stack:** Python 3.11, `aiohttp` (présent), `sqlite3` (stdlib), Playwright (présent, non requis ici), pytest (`asyncio_mode = auto`). Gemini via REST `generateContent` + `responseSchema`. **Aucune nouvelle dépendance.**

**Branche :** `feature/pipeline-phase-b-ia` (déjà créée, spec committée).

**Spec de référence :** `docs/superpowers/specs/2026-05-30-pipeline-phase-b-cascade-ia-design.md`

---

## Décisions de cadrage spécifiques à la Phase B

- **Tout cloud gratuit** : triage/vérif/photo sur `gemini-3.1-flash-lite` au démarrage. Le Pro (vérif des 🔴) est **conçu pluggable mais désactivé** (B-04 : Tristan n'a pas accès au compte Pro). Le router permettra de l'activer via `.env` sans réécriture. Idem pour un futur provider **local Ollama** (B-05/§9).
- **Gate 🔴 dur** : une opportunité ne devient `urgent` que si le modèle de **vérification** a un tier ≥ `MIN_TIER_FOR_URGENT` (défaut `"pro"`). Pro absent → enrichissement complet mais **plafond 🟡**. Le trieur ne renvoie jamais `urgent` (vérifié côté code).
- **Écriture après triage, mise à jour après vérif/photo** (upsert `on_conflict=ad_id`, idempotent). Supabase ne voit jamais d'opportunité brute.
- **Batching dans le worker** : la cascade expose des fonctions de stage pures (`triage_batch`, `verify_one`, `photo_one`) ; c'est `enrichment_worker` qui groupe (10-20 annonces → 1 appel de triage).
- **Reset quota** : approximé à minuit Pacifique via un offset fixe `-8h` (`quota_day`), pour rester **zéro dépendance** (pas de `tzdata`). Imprécision DST ≤ 1 h, sans impact pratique.
- **Pas de migration de colonnes** attendue (les colonnes IA de `opportunities` existent depuis la Phase A). Task 13 le **vérifie** ; mini-migration seulement si une colonne manque.
- **Hors périmètre** : Telegram, hub, géo/`member_settings` (Phases C/D). Scrape de comparaison ciblé des 🔴 = non inclus (grounding = médiane locale).

---

## Contrats partagés (types utilisés dans tout le plan)

```python
# "ad" reconstruit par le worker depuis le payload en file :
ad = {
    "ad_id": str, "title": str, "price": float, "url": str,
    "image_url": str | None, "city": str | None, "category": str | None,  # category = slug LBC
}

# "search" (seuils de rentabilité) résolu par le worker, défauts si absent :
search = {"id": str, "min_margin_eur": float | None, "min_margin_pct": float | None}

# Résultat d'un stage de triage (par annonce) :
{"category": "interesting" | "passable", "score": float, "reason": str, "dig_deeper": bool}

# Résultat de vérification (avant calcul marge) :
{"refined_score": float, "est_market_price": float, "signals": list,
 "is_lot": bool, "lot_unit_price": float | None, "lot_notes": str | None, "explanation": str}

# Tiers (rang croissant de capacité) — pour le gate 🔴 :
TIER_RANKS = {"flash-lite": 1, "flash": 2, "pro": 3}
```

`Router.generate(stage, prompt, schema, image_bytes=None)` → `(data: dict, model_id: str, tier_rank: int)` ; lève `QuotaExhausted` si plus aucun modèle dispo pour le stage.

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `engine/parse.py` | `+ extract_category(url)` (pur) | Modify |
| `engine/db.py` | `+ pending_enrichment` & `llm_usage` (+ `quota_day`) | Modify |
| `engine/sink.py` | `LocalSink` : `insert_opportunity` → `brain.queue_pending` | Create |
| `engine/grounding.py` | `market_grounding(brain, categorie)` → médiane/échantillon | Create |
| `engine/config.py` | `+ clés IA` (modèles, gate, seuils) | Modify |
| `engine/prompts.py` | schémas JSON + builders de prompt (triage/vérif/photo) | Create |
| `engine/router.py` | `LLMRouter` (registre, tier, route, usage, fallback, gate) | Create |
| `engine/llm_client.py` | `GeminiClient` : REST `generateContent` (texte + vision) | Create |
| `engine/cascade.py` | `triage_batch`, `verify_one`, `photo_one`, `compute_margin_and_category` | Create |
| `engine/supa.py` | `+ merge_enrichment(payload, ia)` | Modify |
| `engine/enrich.py` | `enrichment_worker` : draine la file, orchestre la cascade, écrit | Create |
| `engine/bootstrap.py` / `server.py` | injecter `LocalSink` + démarrer le worker sous `--auto` | Modify |
| `CLAUDE.md` | documenter la cascade + le Pro suspendu | Modify |
| `tests/test_engine_*.py` | unitaires + check-list LIVE | Create |

---

## Task 1: `extract_category` (helper pur)

**Files:**
- Modify: `engine/parse.py`
- Test: `tests/test_engine_parse_category.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_parse_category.py
from engine.parse import extract_category


def test_category_standard_url():
    url = "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678"
    assert extract_category(url) == "consoles_jeux_video"


def test_category_with_query_and_slash():
    url = "https://www.leboncoin.fr/ad/informatique/2999000111/?foo=bar"
    assert extract_category(url) == "informatique"


def test_category_legacy_htm_path():
    # ancien format /<categorie>/<id>.htm
    url = "https://www.leboncoin.fr/velos/1234567890.htm"
    assert extract_category(url) == "velos"


def test_category_none_when_absent():
    assert extract_category("https://www.leboncoin.fr/recherche?text=ps5") is None
    assert extract_category("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_parse_category.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract_category'`

- [ ] **Step 3: Write minimal implementation (ajouter à `engine/parse.py`)**

```python
# engine/parse.py  (ajouter en bas)
_CATEGORY_AD_RE = re.compile(r"/ad/([a-z0-9_]+)/\d", re.IGNORECASE)
_CATEGORY_LEGACY_RE = re.compile(r"leboncoin\.fr/([a-z0-9_]+)/\d+\.htm", re.IGNORECASE)


def extract_category(url: str) -> str | None:
    """Extrait le slug de catégorie d'une URL d'annonce LBC ('/ad/<cat>/<id>')."""
    if not url:
        return None
    m = _CATEGORY_AD_RE.search(url)
    if m:
        return m.group(1).lower()
    m = _CATEGORY_LEGACY_RE.search(url)
    return m.group(1).lower() if m else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_parse_category.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/parse.py tests/test_engine_parse_category.py
git commit -m "feat(engine): extract_category depuis l'URL d'annonce LBC"
```

---

## Task 2: Cerveau — file `pending_enrichment`

**Files:**
- Modify: `engine/db.py`
- Test: `tests/test_engine_db_pending.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_db_pending.py
from engine.db import Brain


def test_queue_and_peek_pending_fifo():
    b = Brain(":memory:")
    b.queue_pending({"ad_id": "1", "title": "A"}, search_id="s1", ad_id="1", now=1000)
    b.queue_pending({"ad_id": "2", "title": "B"}, search_id="s1", ad_id="2", now=1001)
    items = b.peek_pending(limit=10)
    assert [it["ad_id"] for it in items] == ["1", "2"]
    assert items[0]["payload"]["title"] == "A"
    assert items[0]["search_id"] == "s1"


def test_delete_pending_removes_item():
    b = Brain(":memory:")
    b.queue_pending({"ad_id": "1"}, search_id="s1", ad_id="1", now=1000)
    items = b.peek_pending(limit=10)
    b.delete_pending(items[0]["id"])
    assert b.peek_pending(limit=10) == []


def test_bump_pending_retry_increments():
    b = Brain(":memory:")
    b.queue_pending({"ad_id": "1"}, search_id="s1", ad_id="1", now=1000)
    pid = b.peek_pending(limit=10)[0]["id"]
    b.bump_pending_retry(pid)
    assert b.peek_pending(limit=10)[0]["retries"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_db_pending.py -v`
Expected: FAIL with `AttributeError: 'Brain' object has no attribute 'queue_pending'`

- [ ] **Step 3: Write minimal implementation**

Dans `engine/db.py`, ajouter à la constante `SCHEMA` (avant la fin de la chaîne) :

```python
CREATE TABLE IF NOT EXISTS pending_enrichment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id TEXT NOT NULL,
    search_id TEXT,
    payload TEXT NOT NULL,
    queued_at INTEGER NOT NULL,
    retries INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS pending_ad_idx ON pending_enrichment(ad_id);
```

Puis ajouter ces méthodes à la classe `Brain` :

```python
# engine/db.py  (méthodes de Brain)
    def queue_pending(self, payload: dict, search_id: str | None, ad_id: str, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO pending_enrichment (ad_id, search_id, payload, queued_at, retries) VALUES (?, ?, ?, ?, 0)",
            (ad_id, search_id, json.dumps(payload), now),
        )
        self.conn.commit()

    def peek_pending(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, ad_id, search_id, payload, retries FROM pending_enrichment ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r["id"], "ad_id": r["ad_id"], "search_id": r["search_id"],
             "payload": json.loads(r["payload"]), "retries": r["retries"]}
            for r in rows
        ]

    def delete_pending(self, pending_id: int) -> None:
        self.conn.execute("DELETE FROM pending_enrichment WHERE id = ?", (pending_id,))
        self.conn.commit()

    def bump_pending_retry(self, pending_id: int) -> None:
        self.conn.execute(
            "UPDATE pending_enrichment SET retries = retries + 1 WHERE id = ?", (pending_id,)
        )
        self.conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_db_pending.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/db.py tests/test_engine_db_pending.py
git commit -m "feat(engine): Brain - file pending_enrichment (queue worker IA)"
```

---

## Task 3: Cerveau — comptage quotas `llm_usage` + `quota_day`

**Files:**
- Modify: `engine/db.py`
- Test: `tests/test_engine_db_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_db_usage.py
from engine.db import Brain, quota_day


def test_quota_day_is_pacific_offset_string():
    # 2026-05-30 03:00 UTC → encore le 29 en Pacifique (UTC-8)
    assert quota_day(1748574000) == quota_day(1748574000)  # déterministe
    assert isinstance(quota_day(1748574000), str)
    assert len(quota_day(1748574000)) == 10  # YYYY-MM-DD


def test_inc_and_count_usage():
    b = Brain(":memory:")
    day = "2026-05-30"
    assert b.usage_count("gemini", "flash-lite", day) == 0
    b.inc_usage("gemini", "flash-lite", day, tokens=120)
    b.inc_usage("gemini", "flash-lite", day, tokens=80)
    assert b.usage_count("gemini", "flash-lite", day) == 2


def test_usage_count_isolated_per_model_and_day():
    b = Brain(":memory:")
    b.inc_usage("gemini", "flash-lite", "2026-05-30", tokens=10)
    assert b.usage_count("gemini", "pro", "2026-05-30") == 0
    assert b.usage_count("gemini", "flash-lite", "2026-05-31") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_db_usage.py -v`
Expected: FAIL with `ImportError: cannot import name 'quota_day'`

- [ ] **Step 3: Write minimal implementation**

Ajouter à `SCHEMA` :

```python
CREATE TABLE IF NOT EXISTS llm_usage (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    day TEXT NOT NULL,
    request_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    PRIMARY KEY (provider, model, day)
);
```

Ajouter la fonction module + les méthodes :

```python
# engine/db.py  (fonction au niveau module, près du haut)
from datetime import datetime, timezone, timedelta

# Approximation du reset minuit Pacifique (offset fixe, zéro dépendance tzdata).
_PACIFIC_OFFSET = timedelta(hours=-8)


def quota_day(ts: int | None = None) -> str:
    """Jour-quota au format 'YYYY-MM-DD' (~minuit Pacifique, offset fixe -8h)."""
    t = ts if ts is not None else time.time()
    dt = datetime.fromtimestamp(t, tz=timezone.utc) + _PACIFIC_OFFSET
    return dt.strftime("%Y-%m-%d")
```

```python
# engine/db.py  (méthodes de Brain)
    def inc_usage(self, provider: str, model: str, day: str, tokens: int = 0) -> None:
        self.conn.execute(
            "INSERT INTO llm_usage (provider, model, day, request_count, token_count) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(provider, model, day) DO UPDATE SET "
            "request_count = request_count + 1, token_count = token_count + excluded.token_count",
            (provider, model, day, tokens),
        )
        self.conn.commit()

    def usage_count(self, provider: str, model: str, day: str) -> int:
        row = self.conn.execute(
            "SELECT request_count FROM llm_usage WHERE provider = ? AND model = ? AND day = ?",
            (provider, model, day),
        ).fetchone()
        return row["request_count"] if row else 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_db_usage.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/db.py tests/test_engine_db_usage.py
git commit -m "feat(engine): Brain - llm_usage + quota_day (comptage quotas)"
```

---

## Task 4: `LocalSink` (le scrape dépose en file au lieu de Supabase)

**Files:**
- Create: `engine/sink.py`
- Test: `tests/test_engine_sink.py`

> `LocalSink` implémente la **même interface** que `Supa` (`async insert_opportunity(payload)`), si bien que `process_search` (Phase A) l'utilise sans changer une ligne. Il extrait `ad_id` / `source_search_id` du payload et met en file.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_sink.py
from engine.db import Brain
from engine.sink import LocalSink


async def test_sink_queues_payload_into_pending():
    brain = Brain(":memory:")
    sink = LocalSink(brain)
    await sink.insert_opportunity({"ad_id": "42", "source_search_id": "s1", "title": "PS5"})
    items = brain.peek_pending(limit=10)
    assert len(items) == 1
    assert items[0]["ad_id"] == "42"
    assert items[0]["search_id"] == "s1"
    assert items[0]["payload"]["title"] == "PS5"


async def test_sink_handles_missing_search_id():
    brain = Brain(":memory:")
    sink = LocalSink(brain)
    await sink.insert_opportunity({"ad_id": "7", "title": "x"})
    assert brain.peek_pending(limit=10)[0]["search_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_sink.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.sink'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/sink.py
"""Destination locale pour le scrape : met les opportunités brutes en file d'enrichissement.

Interface identique à engine.supa.Supa.insert_opportunity → process_search (Phase A)
l'utilise tel quel. En Phase B, le démon injecte ce sink au lieu du client Supabase direct,
pour que Supabase ne reçoive QUE des opportunités enrichies (via enrichment_worker).
"""


class LocalSink:
    def __init__(self, brain):
        self.brain = brain

    async def insert_opportunity(self, payload: dict) -> None:
        self.brain.queue_pending(
            payload,
            search_id=payload.get("source_search_id"),
            ad_id=payload.get("ad_id"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_sink.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/sink.py tests/test_engine_sink.py
git commit -m "feat(engine): LocalSink (scrape -> file d'enrichissement)"
```

---

## Task 5: Grounding prix marché (médiane locale)

**Files:**
- Create: `engine/grounding.py`
- Test: `tests/test_engine_grounding.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_grounding.py
from engine.db import Brain
from engine.grounding import market_grounding


def test_grounding_empty_category_returns_none_median():
    brain = Brain(":memory:")
    g = market_grounding(brain, "consoles_jeux_video")
    assert g["sample_size"] == 0
    assert g["median_price"] is None


def test_grounding_computes_median_and_sample():
    brain = Brain(":memory:")
    for p in (100.0, 200.0, 300.0):
        brain.record_market_obs("consoles_jeux_video", p, "Paris", now=1000)
    g = market_grounding(brain, "consoles_jeux_video")
    assert g["sample_size"] == 3
    assert g["median_price"] == 200.0


def test_grounding_even_sample_averages_two_middles():
    brain = Brain(":memory:")
    for p in (100.0, 200.0, 300.0, 500.0):
        brain.record_market_obs("velos", p, None, now=1000)
    g = market_grounding(brain, "velos")
    assert g["median_price"] == 250.0


def test_grounding_unknown_category_isolated():
    brain = Brain(":memory:")
    brain.record_market_obs("velos", 100.0, None, now=1000)
    assert market_grounding(brain, "informatique")["sample_size"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_grounding.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.grounding'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/grounding.py
"""Grounding prix marché : nourrit l'IA de vrais comparables locaux (pas de prix 'de tête').

Source = table market_observations du cerveau (alimentée à chaque scrape). Démarrage à froid
= échantillon vide → médiane None (l'IA estime alors avec prudence, marges approximatives).
"""
from statistics import median


def market_grounding(brain, categorie: str | None) -> dict:
    """Retourne {median_price, sample_size, min_price, max_price} pour une catégorie."""
    if not categorie:
        return {"median_price": None, "sample_size": 0, "min_price": None, "max_price": None}
    rows = brain.conn.execute(
        "SELECT prix FROM market_observations WHERE categorie = ? AND prix > 0",
        (categorie,),
    ).fetchall()
    prices = [r["prix"] for r in rows]
    if not prices:
        return {"median_price": None, "sample_size": 0, "min_price": None, "max_price": None}
    return {
        "median_price": float(median(prices)),
        "sample_size": len(prices),
        "min_price": min(prices),
        "max_price": max(prices),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_grounding.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/grounding.py tests/test_engine_grounding.py
git commit -m "feat(engine): grounding prix marche (mediane locale par categorie)"
```

---

## Task 6: Configuration IA (`engine/config.py`)

**Files:**
- Modify: `engine/config.py`
- Modify: `.env.example`
- Test: `tests/test_engine_config_ai.py`

> Les clés IA sont **optionnelles** (le moteur Phase A doit pouvoir démarrer sans). `load_config` ne doit PAS exiger `GEMINI_API_KEY`. On ajoute un helper `ai_settings(cfg)` qui applique les défauts.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_config_ai.py
from engine.config import ai_settings


def test_ai_settings_defaults():
    s = ai_settings({})
    assert s["triage_model"] == "gemini-3.1-flash-lite"
    assert s["photo_model"] == "gemini-3.1-flash-lite"
    assert s["min_tier_for_urgent"] == "pro"   # Pro = seul juge du 🔴 (B-04)
    assert s["pro_enabled"] is False            # Pro suspendu par défaut
    assert s["urgent_score_threshold"] == 75.0
    assert s["default_min_margin_eur"] == 30.0
    assert s["default_min_margin_pct"] == 30.0
    assert s["api_key"] is None


def test_ai_settings_pro_enabled_when_key_and_flag():
    s = ai_settings({
        "GEMINI_API_KEY": "k",
        "GEMINI_PRO_ENABLED": "true",
        "GEMINI_VERIFY_MODEL": "gemini-3.1-pro-preview",
    })
    assert s["api_key"] == "k"
    assert s["pro_enabled"] is True
    assert s["verify_model"] == "gemini-3.1-pro-preview"


def test_ai_settings_overrides_thresholds():
    s = ai_settings({"URGENT_SCORE_THRESHOLD": "80", "DEFAULT_MIN_MARGIN_EUR": "50"})
    assert s["urgent_score_threshold"] == 80.0
    assert s["default_min_margin_eur"] == 50.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_config_ai.py -v`
Expected: FAIL with `ImportError: cannot import name 'ai_settings'`

- [ ] **Step 3: Write minimal implementation (ajouter à `engine/config.py`)**

```python
# engine/config.py  (ajouter en bas)
def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def ai_settings(cfg: dict) -> dict:
    """Extrait/complète les réglages IA depuis la config brute. Clés IA toutes optionnelles."""
    return {
        "api_key": cfg.get("GEMINI_API_KEY") or None,
        "triage_model": cfg.get("GEMINI_TRIAGE_MODEL") or "gemini-3.1-flash-lite",
        "verify_model": cfg.get("GEMINI_VERIFY_MODEL") or "gemini-3.1-flash-lite",
        "pro_model": cfg.get("GEMINI_PRO_MODEL") or "gemini-3.1-pro-preview",
        "photo_model": cfg.get("GEMINI_PHOTO_MODEL") or "gemini-3.1-flash-lite",
        "pro_enabled": _to_bool(cfg.get("GEMINI_PRO_ENABLED")) and bool(cfg.get("GEMINI_API_KEY")),
        "min_tier_for_urgent": cfg.get("MIN_TIER_FOR_URGENT") or "pro",
        "urgent_score_threshold": _to_float(cfg.get("URGENT_SCORE_THRESHOLD"), 75.0),
        "default_min_margin_eur": _to_float(cfg.get("DEFAULT_MIN_MARGIN_EUR"), 30.0),
        "default_min_margin_pct": _to_float(cfg.get("DEFAULT_MIN_MARGIN_PCT"), 30.0),
    }
```

Ajouter à `.env.example` :

```bash
# --- Phase B : cascade IA (toutes optionnelles ; sans clé, le moteur tourne sans IA) ---
# GEMINI_API_KEY=...                      # free tier (AI Studio). Sans elle = pas d'enrichissement.
# GEMINI_PRO_ENABLED=false                # passer à true quand l'accès au compte Pro est dispo (B-04)
# GEMINI_VERIFY_MODEL=gemini-3.1-flash-lite   # mettre gemini-3.1-pro-preview une fois Pro activé
# MIN_TIER_FOR_URGENT=pro                 # seul le tier Pro peut declarer une annonce 🔴
# URGENT_SCORE_THRESHOLD=75
# DEFAULT_MIN_MARGIN_EUR=30
# DEFAULT_MIN_MARGIN_PCT=30
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_config_ai.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/config.py .env.example tests/test_engine_config_ai.py
git commit -m "feat(engine): config IA (modeles, gate Pro, seuils) - cles optionnelles"
```

---

## Task 7: Prompts & schémas JSON (`engine/prompts.py`)

**Files:**
- Create: `engine/prompts.py`
- Test: `tests/test_engine_prompts.py`

> Les prompts forcent l'IA à respecter notre cadre. Point dur : le **triage interdit `urgent`** (le schéma ne propose que `interesting`/`passable`). Le grounding (médiane) est injecté en clair.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_prompts.py
from engine.prompts import (
    TRIAGE_SCHEMA, VERIFY_SCHEMA, PHOTO_SCHEMA,
    build_triage_prompt, build_verify_prompt, build_photo_prompt,
)


def test_triage_schema_excludes_urgent():
    cat_enum = TRIAGE_SCHEMA["properties"]["items"]["items"]["properties"]["category"]["enum"]
    assert "urgent" not in cat_enum
    assert set(cat_enum) == {"interesting", "passable"}


def test_build_triage_prompt_lists_all_ads_and_grounding():
    ads = [
        {"ad_id": "1", "title": "PS5 Slim", "price": 250.0, "city": "Paris"},
        {"ad_id": "2", "title": "PC portable", "price": 1200.0, "city": "Lyon"},
    ]
    grounding = {"median_price": 300.0, "sample_size": 12}
    prompt = build_triage_prompt(ads, grounding)
    assert "PS5 Slim" in prompt and "PC portable" in prompt
    assert "300" in prompt  # médiane injectée
    assert "urgent" not in prompt.lower() or "jamais" in prompt.lower()


def test_build_verify_prompt_includes_price_and_grounding():
    ad = {"title": "PS5 Slim", "price": 250.0, "city": "Paris", "category": "consoles_jeux_video"}
    grounding = {"median_price": 380.0, "sample_size": 8}
    prompt = build_verify_prompt(ad, grounding)
    assert "250" in prompt and "380" in prompt


def test_build_photo_prompt_mentions_arnaque():
    prompt = build_photo_prompt({"title": "PS5 Slim"})
    assert "arnaque" in prompt.lower() or "état" in prompt.lower()


def test_verify_schema_has_market_price_field():
    assert "est_market_price" in VERIFY_SCHEMA["properties"]
    assert "refined_score" in VERIFY_SCHEMA["properties"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.prompts'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/prompts.py
"""Prompts et schémas JSON (responseSchema Gemini) de la cascade IA.

Règle dure : le triage ne peut PAS classer 'urgent' (schéma limité à interesting/passable).
Seul le vérificateur (tier Pro) promeut en 🔴, côté code (cf. cascade.compute_margin_and_category).
"""

# --- ÉTAGE 1 : triage groupé ---
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ad_id": {"type": "string"},
                    "category": {"type": "string", "enum": ["interesting", "passable"]},
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                    "dig_deeper": {"type": "boolean"},
                },
                "required": ["ad_id", "category", "score", "dig_deeper"],
            },
        }
    },
    "required": ["items"],
}

# --- ÉTAGE 2 : vérification approfondie ---
VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "refined_score": {"type": "number"},
        "est_market_price": {"type": "number"},
        "signals": {"type": "array", "items": {"type": "string"}},
        "is_lot": {"type": "boolean"},
        "lot_unit_price": {"type": "number"},
        "lot_notes": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["refined_score", "est_market_price", "explanation"],
}

# --- ÉTAGE 3 : photo (vision) ---
PHOTO_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "scam_risk": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["verdict", "scam_risk"],
}


def _grounding_line(grounding: dict) -> str:
    if not grounding or not grounding.get("median_price"):
        return "Prix marché de référence : INCONNU (peu de données, estime avec prudence)."
    return (
        f"Prix marché de référence (médiane de {grounding['sample_size']} annonces réelles) : "
        f"{grounding['median_price']:.0f} €."
    )


def build_triage_prompt(ads: list[dict], grounding: dict) -> str:
    lignes = "\n".join(
        f"- ad_id={a['ad_id']} | {a.get('title','')} | {a.get('price',0):.0f} € | {a.get('city','')}"
        for a in ads
    )
    return (
        "Tu tries des annonces Leboncoin pour de la revente. Pour CHAQUE annonce, donne une "
        "catégorie ('interesting' si ça mérite une analyse approfondie, 'passable' sinon), un "
        "score 0-100, une raison courte, et dig_deeper=true si une vérification fine est utile.\n"
        "IMPORTANT : tu ne déclares JAMAIS une annonce 'urgent' — ce n'est pas ton rôle. Dans le "
        "doute, choisis 'interesting' (mieux vaut garder une annonce moyenne que jeter une bonne).\n"
        f"{_grounding_line(grounding)}\n\n"
        f"Annonces :\n{lignes}"
    )


def build_verify_prompt(ad: dict, grounding: dict) -> str:
    return (
        "Tu vérifies une annonce Leboncoin pour de la revente. Estime le prix de revente réaliste "
        "(est_market_price) en t'appuyant sur le prix marché ci-dessous, un score affiné 0-100, "
        "les signaux d'opportunité, et si c'est un LOT (is_lot, prix unitaire, notes).\n"
        f"{_grounding_line(grounding)}\n\n"
        f"Annonce : {ad.get('title','')} | prix demandé {ad.get('price',0):.0f} € | "
        f"{ad.get('city','')} | catégorie {ad.get('category','?')}."
    )


def build_photo_prompt(ad: dict) -> str:
    return (
        "Analyse la photo de cette annonce Leboncoin. Décris l'état réel visible, les incohérences "
        "éventuelles, et évalue le risque d'arnaque (scam_risk low/medium/high). "
        f"Annonce : {ad.get('title','')}."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_prompts.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/prompts.py tests/test_engine_prompts.py
git commit -m "feat(engine): prompts + schemas JSON de la cascade (triage sans urgent)"
```

---

## Task 8: `LLMRouter` (registre, tier, route, usage, fallback, gate)

**Files:**
- Create: `engine/router.py`
- Test: `tests/test_engine_router.py`

> Le routeur reçoit un **provider injecté** (un `GeminiClient` ou un fake) → testable sans réseau. Il choisit, pour un stage, le 1ᵉʳ modèle dont le quota du jour n'est pas épuisé, appelle le provider, incrémente `llm_usage`, et renvoie `(data, model_id, tier_rank)`. Si tous épuisés → `QuotaExhausted`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_router.py
import pytest
from engine.db import Brain
from engine.router import LLMRouter, QuotaExhausted, TIER_RANKS


class FakeProvider:
    name = "gemini"

    def __init__(self):
        self.calls = []

    async def generate_json(self, model_id, prompt, schema, image_bytes=None):
        self.calls.append(model_id)
        return ({"ok": True, "model": model_id}, 100)  # (data, tokens)


def make_router(provider, settings=None, brain=None):
    settings = settings or {
        "triage_model": "gemini-3.1-flash-lite",
        "verify_model": "gemini-3.1-flash-lite",
        "photo_model": "gemini-3.1-flash-lite",
        "pro_model": "gemini-3.1-pro-preview",
        "pro_enabled": False,
        "min_tier_for_urgent": "pro",
    }
    return LLMRouter(provider, settings, brain or Brain(":memory:"))


async def test_route_triage_uses_flash_lite():
    p = FakeProvider()
    r = make_router(p)
    data, model_id, tier = await r.generate("triage", "prompt", {"x": 1})
    assert data["ok"] is True
    assert model_id == "gemini-3.1-flash-lite"
    assert tier == TIER_RANKS["flash-lite"]


async def test_verify_uses_flash_when_pro_disabled():
    p = FakeProvider()
    r = make_router(p)
    _, model_id, tier = await r.generate("verify", "prompt", {"x": 1})
    assert model_id == "gemini-3.1-flash-lite"
    assert tier == TIER_RANKS["flash-lite"]  # < pro → pas de 🔴 possible


async def test_verify_prefers_pro_when_enabled():
    p = FakeProvider()
    settings = {
        "triage_model": "gemini-3.1-flash-lite", "verify_model": "gemini-3.5-flash",
        "photo_model": "gemini-3.1-flash-lite", "pro_model": "gemini-3.1-pro-preview",
        "pro_enabled": True, "min_tier_for_urgent": "pro",
    }
    r = make_router(p, settings)
    _, model_id, tier = await r.generate("verify", "prompt", {"x": 1})
    assert model_id == "gemini-3.1-pro-preview"
    assert tier == TIER_RANKS["pro"]


async def test_usage_is_counted():
    p = FakeProvider()
    brain = Brain(":memory:")
    r = make_router(p, brain=brain)
    await r.generate("triage", "prompt", {"x": 1})
    await r.generate("triage", "prompt", {"x": 1})
    from engine.db import quota_day
    assert brain.usage_count("gemini", "gemini-3.1-flash-lite", quota_day()) == 2


async def test_quota_exhausted_raises_when_cap_reached():
    p = FakeProvider()
    brain = Brain(":memory:")
    # cap artificiel via settings: 1 req/jour pour le modèle de triage
    r = make_router(p, brain=brain)
    r.caps["gemini-3.1-flash-lite"] = 1
    await r.generate("triage", "prompt", {"x": 1})  # ok (1/1)
    with pytest.raises(QuotaExhausted):
        await r.generate("triage", "prompt", {"x": 1})  # dépasse


def test_min_tier_rank_helper():
    p = FakeProvider()
    r = make_router(p)
    assert r.min_urgent_rank == TIER_RANKS["pro"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.router'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/router.py
"""Routeur multi-modèles : choisit le modèle par stage, compte les quotas, bascule, gate 🔴.

Reçoit un provider injecté (engine.llm_client.GeminiClient ou un fake) → testable sans réseau.
Extensible : un futur provider local (Ollama) ou Groq s'ajoute sans toucher la cascade.
"""
from engine.db import quota_day

# Rang de capacité croissant — sert au gate 🔴 (seul tier >= min peut déclarer urgent).
TIER_RANKS = {"flash-lite": 1, "flash": 2, "pro": 3}

# Plafonds journaliers par défaut (free tier). Configurables via .env plus tard si besoin.
_DEFAULT_CAPS = {
    "gemini-3.1-flash-lite": 1500,
    "gemini-3.5-flash": 1500,
    "gemini-3.1-pro-preview": 100000,  # payant (crédits Cloud) : pas de cap free
}


class QuotaExhausted(Exception):
    """Plus aucun modèle disponible pour ce stage aujourd'hui."""


def _tier_of(model_id: str) -> int:
    if "pro" in model_id:
        return TIER_RANKS["pro"]
    if "flash-lite" in model_id:
        return TIER_RANKS["flash-lite"]
    return TIER_RANKS["flash"]


class LLMRouter:
    def __init__(self, provider, settings: dict, brain):
        self.provider = provider
        self.settings = settings
        self.brain = brain
        self.caps = dict(_DEFAULT_CAPS)
        self.min_urgent_rank = TIER_RANKS.get(settings.get("min_tier_for_urgent", "pro"), 3)

    def _candidates(self, stage: str) -> list[str]:
        """Modèles candidats pour un stage, par ordre de préférence."""
        s = self.settings
        if stage == "triage":
            return [s["triage_model"]]
        if stage == "photo":
            return [s["photo_model"]]
        if stage == "verify":
            if s.get("pro_enabled"):
                return [s["pro_model"], s["verify_model"]]
            return [s["verify_model"]]
        raise ValueError(f"stage inconnu: {stage}")

    async def generate(self, stage: str, prompt: str, schema: dict, image_bytes=None):
        """Retourne (data, model_id, tier_rank). Lève QuotaExhausted si tout est épuisé."""
        day = quota_day()
        provider_name = getattr(self.provider, "name", "gemini")
        for model_id in self._candidates(stage):
            cap = self.caps.get(model_id, 1500)
            if self.brain.usage_count(provider_name, model_id, day) >= cap:
                continue  # ce modèle est épuisé aujourd'hui → on tente le suivant
            data, tokens = await self.provider.generate_json(model_id, prompt, schema, image_bytes)
            self.brain.inc_usage(provider_name, model_id, day, tokens=tokens or 0)
            return data, model_id, _tier_of(model_id)
        raise QuotaExhausted(f"stage={stage} : tous les modèles épuisés")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_router.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/router.py tests/test_engine_router.py
git commit -m "feat(engine): LLMRouter (route par stage, quotas, fallback, gate tier)"
```

---

## Task 9: `GeminiClient` (REST `generateContent`, texte + vision)

**Files:**
- Create: `engine/llm_client.py`
- Test: `tests/test_engine_llm_client.py`

> Implémente `generate_json(model_id, prompt, schema, image_bytes=None)` attendu par le routeur. Test via un **serveur aiohttp mock** (comme `test_engine_supa_client.py`), pas de vrai appel réseau.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_llm_client.py
import json
import pytest
from aiohttp import web, ClientSession
from engine.llm_client import GeminiClient


@pytest.fixture
async def mock_gemini(aiohttp_server):
    captured = {"bodies": [], "paths": []}

    async def generate(request):
        captured["paths"].append(request.path)
        captured["bodies"].append(await request.json())
        payload = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"refined_score": 88})}]}}],
            "usageMetadata": {"totalTokenCount": 142},
        }
        return web.json_response(payload)

    app = web.Application()
    app.router.add_post("/v1beta/models/{model}:generateContent", generate)
    server = await aiohttp_server(app)
    server.captured = captured
    return server


async def test_generate_json_parses_structured_output(mock_gemini):
    base = str(mock_gemini.make_url("")).rstrip("/")
    async with ClientSession() as session:
        client = GeminiClient("test-key", session, base_url=base)
        data, tokens = await client.generate_json(
            "gemini-3.1-flash-lite", "prompt", {"type": "object"}
        )
    assert data["refined_score"] == 88
    assert tokens == 142
    # le schéma et le prompt sont bien envoyés
    body = mock_gemini.captured["bodies"][-1]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["contents"][0]["parts"][0]["text"] == "prompt"


async def test_generate_json_includes_image_inline(mock_gemini):
    base = str(mock_gemini.make_url("")).rstrip("/")
    async with ClientSession() as session:
        client = GeminiClient("test-key", session, base_url=base)
        await client.generate_json(
            "gemini-3.1-flash-lite", "prompt", {"type": "object"}, image_bytes=b"\xff\xd8\xff"
        )
    parts = mock_gemini.captured["bodies"][-1]["contents"][0]["parts"]
    assert any("inline_data" in p for p in parts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.llm_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/llm_client.py
"""Client REST Gemini (generateContent) — texte + vision, sortie JSON stricte.

Zéro nouvelle dépendance : aiohttp (déjà présent). Expose generate_json(...) tel
qu'attendu par engine.router.LLMRouter. La clé API passe en query param ?key=...
"""
import base64
import json

_DEFAULT_BASE = "https://generativelanguage.googleapis.com"


class GeminiClient:
    name = "gemini"

    def __init__(self, api_key: str, session, base_url: str = _DEFAULT_BASE):
        self.api_key = api_key
        self.session = session
        self.base = base_url.rstrip("/")

    async def generate_json(self, model_id: str, prompt: str, schema: dict, image_bytes=None):
        """Retourne (data: dict, token_count: int). Lève en cas d'erreur HTTP."""
        parts = [{"text": prompt}]
        if image_bytes:
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            })
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        url = f"{self.base}/v1beta/models/{model_id}:generateContent"
        params = {"key": self.api_key}
        async with self.session.post(url, params=params, json=body) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        tokens = payload.get("usageMetadata", {}).get("totalTokenCount", 0)
        return json.loads(text), tokens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_llm_client.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/llm_client.py tests/test_engine_llm_client.py
git commit -m "feat(engine): GeminiClient REST (generateContent texte + vision)"
```

---

## Task 10: Cascade — stages purs + calcul marge/gate 🔴

**Files:**
- Create: `engine/cascade.py`
- Test: `tests/test_engine_cascade.py`

> Le cœur. Fonctions de stage testées avec un **FakeRouter** (réponses canned). `compute_margin_and_category` est pure → on teste à fond le gate 🔴, le plafond 🟡 (Pro absent) et le rabaissement d'un `urgent` du trieur.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_cascade.py
import pytest
from engine.db import Brain
from engine.cascade import (
    compute_margin_and_category, triage_batch, verify_one, photo_one,
)
from engine.router import TIER_RANKS, QuotaExhausted


# ---- compute_margin_and_category (pur) ----

def test_margin_basic():
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=90,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    assert out["est_margin_eur"] == 150.0
    assert out["est_margin_pct"] == 75.0
    # max_buy = 350 - max(30, 200*0.30=60) = 350 - 60 = 290
    assert out["max_buy_price"] == 290.0
    assert out["category"] == "urgent"   # score>=75, marge OK, tier Pro


def test_no_urgent_when_tier_below_min():
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=95,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["flash"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    assert out["category"] == "interesting"  # plafond 🟡 car tier < pro (Pro suspendu)


def test_no_urgent_when_margin_too_low():
    out = compute_margin_and_category(
        price=300.0, est_market_price=320.0, refined_score=95,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    # marge 20€ < 30€ ET 6.7% < 30% → pas urgent
    assert out["category"] == "interesting"


def test_passable_when_low_score():
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=40,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    assert out["category"] == "passable"


# ---- triage_batch (FakeRouter) ----

class FakeRouter:
    def __init__(self, data, tier_rank=TIER_RANKS["flash-lite"]):
        self._data = data
        self._tier = tier_rank
        self.min_urgent_rank = TIER_RANKS["pro"]

    async def generate(self, stage, prompt, schema, image_bytes=None):
        return self._data, "fake-model", self._tier


async def test_triage_batch_maps_results_and_blocks_urgent():
    ads = [{"ad_id": "1", "title": "PS5", "price": 200.0, "city": "Paris"}]
    # le routeur (ici fake) renvoie 'urgent' à tort → doit être rabaissé à 'interesting'
    router = FakeRouter({"items": [
        {"ad_id": "1", "category": "urgent", "score": 90, "dig_deeper": True, "reason": "x"},
    ]})
    brain = Brain(":memory:")
    out = await triage_batch(ads, router, brain)
    assert out["1"]["category"] == "interesting"  # jamais urgent au triage
    assert out["1"]["dig_deeper"] is True


async def test_triage_batch_records_market_obs():
    ads = [{"ad_id": "1", "title": "PS5", "price": 200.0, "city": "Paris",
            "category": "consoles_jeux_video"}]
    router = FakeRouter({"items": [
        {"ad_id": "1", "category": "interesting", "score": 60, "dig_deeper": False, "reason": "x"},
    ]})
    brain = Brain(":memory:")
    await triage_batch(ads, router, brain)
    rows = brain.conn.execute("select prix from market_observations").fetchall()
    assert rows[0]["prix"] == 200.0


# ---- verify_one (FakeRouter) ----

async def test_verify_one_promotes_urgent_with_pro():
    ad = {"ad_id": "1", "title": "PS5", "price": 200.0, "city": "Paris",
          "category": "consoles_jeux_video"}
    search = {"min_margin_eur": 30, "min_margin_pct": 30}
    router = FakeRouter(
        {"refined_score": 92, "est_market_price": 350.0, "signals": ["sous-coté"],
         "is_lot": False, "explanation": "ok"},
        tier_rank=TIER_RANKS["pro"],
    )
    brain = Brain(":memory:")
    out = await verify_one(ad, search, router, brain, urgent_score_threshold=75)
    assert out["category"] == "urgent"
    assert out["est_margin_eur"] == 150.0
    assert out["model_used"] == "fake-model"


async def test_verify_one_capped_at_interesting_without_pro():
    ad = {"ad_id": "1", "title": "PS5", "price": 200.0, "city": "Paris",
          "category": "consoles_jeux_video"}
    search = {"min_margin_eur": 30, "min_margin_pct": 30}
    router = FakeRouter(
        {"refined_score": 92, "est_market_price": 350.0, "signals": [],
         "is_lot": False, "explanation": "ok"},
        tier_rank=TIER_RANKS["flash"],   # pas Pro
    )
    brain = Brain(":memory:")
    out = await verify_one(ad, search, router, brain, urgent_score_threshold=75)
    assert out["category"] == "interesting"  # plafond 🟡


# ---- photo_one (FakeRouter) ----

async def test_photo_one_returns_verdict():
    ad = {"ad_id": "1", "title": "PS5"}
    router = FakeRouter({"verdict": "bon état", "scam_risk": "low"})
    out = await photo_one(ad, b"\xff\xd8\xff", router)
    assert out["photo_verdict"] == "bon état"
    assert out["scam_risk"] == "low"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_cascade.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.cascade'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/cascade.py
"""Cascade IA : stages purs (triage groupé, vérif, photo) + calcul marge/gate 🔴.

Le batching (10-20 annonces → 1 appel triage) vit dans enrichment_worker ; ici on expose
des fonctions de stage qui prennent un 'router' injecté (LLMRouter ou fake) → testables.
"""
from engine.prompts import (
    TRIAGE_SCHEMA, VERIFY_SCHEMA, PHOTO_SCHEMA,
    build_triage_prompt, build_verify_prompt, build_photo_prompt,
)
from engine.grounding import market_grounding


def compute_margin_and_category(
    price: float, est_market_price: float, refined_score: float,
    min_margin_eur: float, min_margin_pct: float,
    tier_rank: int, min_urgent_rank: int, urgent_score_threshold: float,
) -> dict:
    """Calcule marge €/%, prix max d'achat, et la catégorie finale (gate 🔴)."""
    price = float(price or 0.0)
    est = float(est_market_price or 0.0)
    margin_eur = round(est - price, 2)
    margin_pct = round((margin_eur / price * 100.0), 2) if price > 0 else 0.0
    required = max(min_margin_eur, price * min_margin_pct / 100.0)
    max_buy = round(est - required, 2)

    margin_ok = margin_eur >= min_margin_eur and margin_pct >= min_margin_pct
    score_ok = refined_score >= urgent_score_threshold
    tier_ok = tier_rank >= min_urgent_rank
    if score_ok and margin_ok and tier_ok:
        category = "urgent"
    elif refined_score >= 50:
        category = "interesting"
    else:
        category = "passable"

    return {
        "est_market_price": est,
        "est_margin_eur": margin_eur,
        "est_margin_pct": margin_pct,
        "max_buy_price": max_buy,
        "category": category,
    }


async def triage_batch(ads: list[dict], router, brain) -> dict:
    """Étage 1 : 1 appel pour N annonces. Retourne {ad_id: {category, score, dig_deeper, reason}}.

    - Enregistre chaque annonce comme observation marché (byproduct).
    - Force category ∈ {interesting, passable} (le triage ne déclare JAMAIS urgent).
    """
    for a in ads:
        if a.get("category") and a.get("price"):
            brain.record_market_obs(a["category"], float(a["price"]), a.get("city"))

    grounding = market_grounding(brain, ads[0].get("category") if ads else None)
    prompt = build_triage_prompt(ads, grounding)
    data, _model, _tier = await router.generate("triage", prompt, TRIAGE_SCHEMA)

    out: dict = {}
    for item in data.get("items", []):
        cat = item.get("category")
        if cat not in ("interesting", "passable"):
            cat = "interesting"  # garde-fou : jamais urgent au triage
        out[str(item["ad_id"])] = {
            "category": cat,
            "score": float(item.get("score", 0)),
            "dig_deeper": bool(item.get("dig_deeper", False)),
            "reason": item.get("reason", ""),
        }
    return out


async def verify_one(ad: dict, search: dict, router, brain, urgent_score_threshold: float) -> dict:
    """Étage 2 : vérification fine d'une annonce. Seul un tier >= min peut donner 🔴."""
    grounding = market_grounding(brain, ad.get("category"))
    prompt = build_verify_prompt(ad, grounding)
    data, model_id, tier_rank = await router.generate("verify", prompt, VERIFY_SCHEMA)

    margin = compute_margin_and_category(
        price=ad.get("price", 0.0),
        est_market_price=data.get("est_market_price", 0.0),
        refined_score=data.get("refined_score", 0.0),
        min_margin_eur=search.get("min_margin_eur") or 0.0,
        min_margin_pct=search.get("min_margin_pct") or 0.0,
        tier_rank=tier_rank, min_urgent_rank=router.min_urgent_rank,
        urgent_score_threshold=urgent_score_threshold,
    )
    return {
        **margin,
        "resale_score": float(data.get("refined_score", 0.0)),
        "signals": data.get("signals", []),
        "is_lot": bool(data.get("is_lot", False)),
        "lot_unit_price": data.get("lot_unit_price"),
        "lot_notes": data.get("lot_notes"),
        "explanation": data.get("explanation", ""),
        "model_used": model_id,
    }


async def photo_one(ad: dict, image_bytes: bytes, router) -> dict:
    """Étage 3 : analyse photo (🔴 uniquement). Retourne {photo_verdict, scam_risk}."""
    prompt = build_photo_prompt(ad)
    data, _model, _tier = await router.generate("photo", prompt, PHOTO_SCHEMA, image_bytes=image_bytes)
    return {"photo_verdict": data.get("verdict", ""), "scam_risk": data.get("scam_risk", "low")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_cascade.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/cascade.py tests/test_engine_cascade.py
git commit -m "feat(engine): cascade (triage/verify/photo) + calcul marge & gate 🔴"
```

---

## Task 11: `merge_enrichment` (fusion IA → payload Supabase)

**Files:**
- Modify: `engine/supa.py`
- Test: `tests/test_engine_supa_merge.py`

> Le payload en file (brut, champs IA = null) doit être fusionné avec les résultats de la cascade avant l'upsert. Fonction pure. On ne garde que les colonnes existantes de `opportunities`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_supa_merge.py
from engine.supa import merge_enrichment


def base_payload():
    return {
        "ad_id": "1", "title": "PS5", "price": 200.0, "url": "u", "image_url": "img",
        "category": None, "resale_score": None, "est_margin_eur": None, "status": "active",
    }


def test_merge_sets_ai_fields():
    ia = {"category": "urgent", "resale_score": 90.0, "est_market_price": 350.0,
          "est_margin_eur": 150.0, "est_margin_pct": 75.0, "max_buy_price": 290.0,
          "is_lot": False, "signals": ["x"], "explanation": "ok", "model_used": "m"}
    out = merge_enrichment(base_payload(), ia)
    assert out["category"] == "urgent"
    assert out["resale_score"] == 90.0
    assert out["est_margin_eur"] == 150.0
    assert out["model_used"] == "m"
    # champs de base préservés
    assert out["ad_id"] == "1" and out["title"] == "PS5"


def test_merge_serializes_signals_to_json_compatible():
    ia = {"category": "interesting", "signals": ["a", "b"]}
    out = merge_enrichment(base_payload(), ia)
    assert out["signals"] == ["a", "b"]


def test_merge_ignores_unknown_keys():
    ia = {"category": "passable", "dig_deeper": True, "reason": "x"}  # pas des colonnes
    out = merge_enrichment(base_payload(), ia)
    assert "dig_deeper" not in out
    assert "reason" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_supa_merge.py -v`
Expected: FAIL with `ImportError: cannot import name 'merge_enrichment'`

- [ ] **Step 3: Write minimal implementation (ajouter à `engine/supa.py`)**

```python
# engine/supa.py  (ajouter, near build_opportunity_payload)

# Colonnes IA de `opportunities` qu'on autorise à écrire depuis la cascade.
_AI_COLUMNS = (
    "category", "resale_score", "est_market_price", "est_margin_eur", "est_margin_pct",
    "max_buy_price", "is_lot", "lot_unit_price", "lot_notes", "signals", "explanation",
    "photo_verdict", "model_used",
)


def merge_enrichment(payload: dict, ia: dict) -> dict:
    """Fusionne les résultats de la cascade dans le payload d'opportunité (colonnes connues only)."""
    out = dict(payload)
    for col in _AI_COLUMNS:
        if col in ia:
            out[col] = ia[col]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_supa_merge.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/supa.py tests/test_engine_supa_merge.py
git commit -m "feat(engine): merge_enrichment (cascade -> payload opportunite)"
```

---

## Task 12: `enrichment_worker` (draine la file → cascade → écrit)

**Files:**
- Create: `engine/enrich.py`
- Test: `tests/test_engine_enrich.py`

> Orchestration : prend un lot de la file, fait UN triage groupé, écrit chaque opportunité (post-triage), puis pour les candidates fait la vérif (update), puis la photo sur les 🔴 (update). Résilient : un échec par item n'arrête pas le worker ; quota épuisé → on s'arrête proprement (les items restent en file).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_enrich.py
import pytest
from engine.db import Brain
from engine.enrich import enrich_once
from engine.router import TIER_RANKS, QuotaExhausted


class FakeSupa:
    def __init__(self):
        self.upserts = []

    async def insert_opportunity(self, payload):
        self.upserts.append(dict(payload))


class ScriptedRouter:
    """Router simulé : réponses par stage, tier configurable."""
    def __init__(self, triage_items, verify=None, photo=None, verify_tier=TIER_RANKS["flash"]):
        self.triage_items = triage_items
        self.verify = verify
        self.photo = photo
        self.verify_tier = verify_tier
        self.min_urgent_rank = TIER_RANKS["pro"]

    async def generate(self, stage, prompt, schema, image_bytes=None):
        if stage == "triage":
            return {"items": self.triage_items}, "flash-lite", TIER_RANKS["flash-lite"]
        if stage == "verify":
            return self.verify, "verify-model", self.verify_tier
        if stage == "photo":
            return self.photo, "photo-model", TIER_RANKS["flash-lite"]
        raise ValueError(stage)


def queue_ad(brain, ad_id, price=200.0, url="https://www.leboncoin.fr/ad/consoles_jeux_video/1"):
    payload = {
        "ad_id": ad_id, "source_search_id": "s1", "title": f"PS5 {ad_id}", "price": price,
        "url": url, "image_url": None, "location_city": "Paris",
        "category": None, "resale_score": None, "status": "active",
    }
    brain.queue_pending(payload, search_id="s1", ad_id=ad_id, now=1000)


async def test_enrich_once_writes_triaged_opportunity():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    router = ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "passable", "score": 40, "dig_deeper": False}],
    )
    n = await enrich_once(brain, supa, router, settings={"urgent_score_threshold": 75},
                          searches_by_id={}, image_fetch=None)
    assert n == 1
    assert supa.upserts[-1]["category"] == "passable"
    assert brain.peek_pending(limit=10) == []  # consommé


async def test_enrich_once_verifies_candidate_and_updates():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    router = ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "interesting", "score": 80, "dig_deeper": True}],
        verify={"refined_score": 92, "est_market_price": 350.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["pro"],
    )
    await enrich_once(brain, supa, router,
                      settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None)
    # 2 upserts : 1 post-triage (interesting), 1 post-vérif (urgent)
    assert supa.upserts[-1]["category"] == "urgent"
    assert supa.upserts[-1]["est_margin_eur"] == 150.0


async def test_enrich_once_quota_exhausted_keeps_items():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")

    class Boom:
        min_urgent_rank = TIER_RANKS["pro"]
        async def generate(self, *a, **k):
            raise QuotaExhausted("epuise")

    n = await enrich_once(brain, supa, Boom(), settings={"urgent_score_threshold": 75},
                          searches_by_id={}, image_fetch=None)
    assert n == 0
    assert len(brain.peek_pending(limit=10)) == 1  # rien perdu, reste en file
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_enrich.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.enrich'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/enrich.py
"""Worker d'enrichissement : draine pending_enrichment, exécute la cascade, écrit dans Supabase.

Découplé du scrape (2e coroutine sous --auto). Écrit l'opportunité dès le triage (jamais brute),
met à jour après vérif puis photo. Résilient : QuotaExhausted → on s'arrête, les items restent
en file pour le prochain cycle (dégradation gracieuse, §6 de la spec).
"""
import asyncio
from engine.parse import extract_category
from engine.cascade import triage_batch, verify_one, photo_one
from engine.supa import merge_enrichment
from engine.router import QuotaExhausted


def _ad_from_payload(payload: dict) -> dict:
    return {
        "ad_id": payload.get("ad_id"),
        "title": payload.get("title"),
        "price": payload.get("price"),
        "url": payload.get("url"),
        "image_url": payload.get("image_url"),
        "city": payload.get("location_city"),
        "category": extract_category(payload.get("url") or ""),
    }


async def enrich_once(brain, supa, router, settings, searches_by_id, image_fetch, batch_size=15) -> int:
    """Traite un lot. Retourne le nombre d'opportunités écrites (post-triage). 0 si rien/quota."""
    items = brain.peek_pending(limit=batch_size)
    if not items:
        return 0

    ads = [_ad_from_payload(it["payload"]) for it in items]
    by_id = {it["ad_id"]: it for it in items}
    threshold = settings.get("urgent_score_threshold", 75.0)

    try:
        triaged = await triage_batch(ads, router, brain)
    except QuotaExhausted:
        return 0  # rien consommé, tout reste en file

    written = 0
    for ad in ads:
        ad_id = ad["ad_id"]
        item = by_id[ad_id]
        t = triaged.get(ad_id)
        if t is None:
            continue
        payload = merge_enrichment(item["payload"], {
            "category": t["category"], "resale_score": t["score"],
        })
        try:
            await supa.insert_opportunity(payload)  # écriture post-triage (jamais brute)
        except Exception:
            brain.queue_outbox(payload)  # Supabase down → outbox (résilience Phase A)

        # vérif des candidates
        if t["dig_deeper"] or t["score"] >= threshold:
            search = searches_by_id.get(item["search_id"]) or {}
            try:
                ia = await verify_one(ad, search, router, brain, urgent_score_threshold=threshold)
            except QuotaExhausted:
                brain.delete_pending(item["id"])  # déjà écrit au triage ; on n'insiste pas
                written += 1
                break  # quota fini : on arrête le lot, le reste attend
            payload = merge_enrichment(payload, ia)
            try:
                await supa.insert_opportunity(payload)
            except Exception:
                brain.queue_outbox(payload)

            # photo sur les 🔴 uniquement
            if payload.get("category") == "urgent" and ad.get("image_url") and image_fetch:
                try:
                    img = await image_fetch(ad["image_url"])
                    photo = await photo_one(ad, img, router)
                    payload = merge_enrichment(payload, photo)
                    await supa.insert_opportunity(payload)
                except QuotaExhausted:
                    pass  # déjà 🔴 sans photo, acceptable
                except Exception:
                    pass

        brain.delete_pending(item["id"])
        written += 1
    return written


async def enrichment_worker(brain, supa, router, settings, fetch_searches, image_fetch,
                            stop_event, pause: float = 5.0, max_loops=None) -> None:
    """Boucle du worker. `fetch_searches` → {search_id: {min_margin_eur, min_margin_pct}}."""
    loops = 0
    while not stop_event.is_set():
        try:
            searches_by_id = await fetch_searches()
            await enrich_once(brain, supa, router, settings, searches_by_id, image_fetch)
        except Exception as exc:
            print(f"[enrich] erreur cycle: {exc}")
        loops += 1
        if max_loops is not None and loops >= max_loops:
            return
        if pause:
            await asyncio.sleep(pause)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_enrich.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/enrich.py tests/test_engine_enrich.py
git commit -m "feat(engine): enrichment_worker (file -> cascade -> Supabase, resilient)"
```

---

## Task 13: Vérification du schéma Supabase (colonnes IA)

**Files:**
- Create (conditionnel): `supabase/migrations/2026-05-30-phase-b-verif.sql`

> Pas de test automatisé. Objectif : **confirmer** que `opportunities` a bien toutes les colonnes IA (créées en Phase A). N'écrire une migration QUE si une colonne manque.

- [ ] **Step 1: Vérifier les colonnes existantes**

Dans Supabase Dashboard → SQL Editor, exécuter :

```sql
select column_name from information_schema.columns
where table_name = 'opportunities' order by column_name;
```

Confirmer la présence de : `category, resale_score, est_market_price, est_margin_eur,
est_margin_pct, max_buy_price, is_lot, lot_unit_price, lot_notes, signals, explanation,
photo_verdict, model_used`.

- [ ] **Step 2: Si une colonne manque uniquement**, créer `supabase/migrations/2026-05-30-phase-b-verif.sql` avec les `alter table ... add column if not exists ...` correspondants, puis l'appliquer. Sinon, **noter dans le commit que tout est déjà présent** (pas de fichier).

- [ ] **Step 3: Confirmer `watchlist_searches.min_margin_eur` / `min_margin_pct`** (créées en Phase A) :

```sql
select column_name from information_schema.columns
where table_name = 'watchlist_searches' and column_name like 'min_margin%';
```

- [ ] **Step 4: Commit (si fichier créé)**

```bash
git add supabase/migrations/2026-05-30-phase-b-verif.sql
git commit -m "chore(db): verif/complement colonnes IA opportunities (Phase B)"
```

---

## Task 14: Câblage `--auto` (sink local + worker en parallèle)

**Files:**
- Modify: `engine/bootstrap.py`
- Modify: `server.py` (bootstrap de la boucle sous `--auto`)
- Test: `tests/test_engine_bootstrap_phaseb.py`

> Sous `--auto` : `process_search` reçoit un **`LocalSink`** (au lieu du `Supa` direct), et on lance `enrichment_worker` **en parallèle** de `run_engine` (deux coroutines, `asyncio.gather`). Le worker a son propre `Supa` (écriture réelle). On ajoute une fonction `build_engine_runtime(...)` testable qui assemble les pièces sans réseau.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_bootstrap_phaseb.py
import asyncio
from engine.db import Brain
from engine.bootstrap import build_searches_lookup


async def test_build_searches_lookup_maps_thresholds():
    class FakeSupa:
        async def fetch_active_searches(self):
            return [
                {"id": "s1", "min_margin_eur": 50, "min_margin_pct": 40, "source_url": "u"},
                {"id": "s2", "min_margin_eur": None, "min_margin_pct": None, "source_url": "u2"},
            ]

    lookup = await build_searches_lookup(FakeSupa(), defaults={"min_margin_eur": 30, "min_margin_pct": 30})
    assert lookup["s1"]["min_margin_eur"] == 50
    # défauts appliqués quand null
    assert lookup["s2"]["min_margin_eur"] == 30
    assert lookup["s2"]["min_margin_pct"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_bootstrap_phaseb.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_searches_lookup'`

- [ ] **Step 3: Write minimal implementation (ajouter à `engine/bootstrap.py`)**

```python
# engine/bootstrap.py  (ajouter)
async def build_searches_lookup(supa, defaults: dict) -> dict:
    """Construit {search_id: {min_margin_eur, min_margin_pct}} avec défauts si null."""
    searches = await supa.fetch_active_searches()
    out = {}
    for s in searches:
        out[s["id"]] = {
            "min_margin_eur": s.get("min_margin_eur") if s.get("min_margin_eur") is not None
            else defaults["min_margin_eur"],
            "min_margin_pct": s.get("min_margin_pct") if s.get("min_margin_pct") is not None
            else defaults["min_margin_pct"],
        }
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_bootstrap_phaseb.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Ajouter les imports IA en haut de `server.py`**

Près des imports existants `from engine.scheduler import run_engine` / `from engine.bootstrap import make_scrape_fn` (déjà présents), ajouter :

```python
from engine.config import ai_settings            # load_config est déjà importé
from engine.sink import LocalSink
from engine.router import LLMRouter
from engine.llm_client import GeminiClient
from engine.enrich import enrichment_worker
from engine.bootstrap import build_searches_lookup
```

- [ ] **Step 6: Remplacer le corps de `start_autonomous_engine` (server.py:533-556)**

Le scrape reçoit désormais un `LocalSink` (au lieu de `supa`) et on lance le worker en 2ᵉ tâche.

```python
async def start_autonomous_engine(app):
    """Démarre la boucle de scrape autonome + le worker d'enrichissement IA (Phase B)."""
    cfg = load_config()
    ai = ai_settings(cfg)
    brain = Brain("lbc_brain.sqlite3")
    session = aiohttp.ClientSession()
    supa = Supa(cfg["SUPABASE_URL"], cfg["SUPABASE_SERVICE_KEY"], session)
    sink = LocalSink(brain)  # le scrape dépose en file locale (PAS Supabase direct)

    async def get_context():
        await ensure_browser()
        return job_state.context

    scrape_fn = make_scrape_fn(
        get_context, extract_ads_from_results, scrape_lock,
        ready_selector=RESULTS_CONTAINER_SELECTOR,
    )
    stop_event = asyncio.Event()
    app["engine_stop"] = stop_event
    app["engine_session"] = session
    app["engine_brain"] = brain

    # Le scrape écrit dans le SINK (file locale) au lieu de Supabase direct.
    tasks = [asyncio.create_task(run_engine(brain, sink, scrape_fn, stop_event, cycle_pause=60.0))]

    if ai["api_key"]:
        provider = GeminiClient(ai["api_key"], session)
        router = LLMRouter(provider, ai, brain)

        async def image_fetch(url):
            async with session.get(url) as r:
                return await r.read()

        async def fetch_searches():
            return await build_searches_lookup(
                supa,
                {"min_margin_eur": ai["default_min_margin_eur"],
                 "min_margin_pct": ai["default_min_margin_pct"]},
            )

        tasks.append(asyncio.create_task(
            enrichment_worker(brain, supa, router, ai, fetch_searches, image_fetch, stop_event)
        ))
        print("🧠 Worker d'enrichissement IA démarré (cascade).")
    else:
        print("⚠️ Pas de GEMINI_API_KEY : enrichissement IA désactivé (opportunités restent en file).")

    app["engine_tasks"] = tasks
    print("🤖 Moteur autonome démarré (scrape 24/7).")
```

- [ ] **Step 7: Mettre à jour `stop_autonomous_engine` (server.py:559-571)** pour annuler **toutes** les tâches

```python
async def stop_autonomous_engine(app):
    if "engine_stop" in app:
        app["engine_stop"].set()
    for t in app.get("engine_tasks", []):
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    if "engine_session" in app:
        await app["engine_session"].close()
    if "engine_brain" in app:
        app["engine_brain"].close()
```

> **Ne pas toucher** l'API HTTP, les handlers, ni le scrape manuel : seuls `start_autonomous_engine`
> et `stop_autonomous_engine` changent. La signature de `run_engine` est inchangée (on lui passe
> `sink` à la place de `supa` — même interface `insert_opportunity`).

- [ ] **Step 8: Run the full suite (non-régression Phase A incluse)**

Run: `python -m pytest tests/ -v`
Expected: PASS (les 62 tests Phase A + tous les nouveaux). Aucun test Phase A modifié.

- [ ] **Step 9: Commit**

```bash
git add engine/bootstrap.py server.py tests/test_engine_bootstrap_phaseb.py
git commit -m "feat(engine): cablage --auto (LocalSink + enrichment_worker en parallele)"
```

---

## Task 15: Documentation `CLAUDE.md` + check-list de validation LIVE

**Files:**
- Modify: `CLAUDE.md`
- Create: `docs/TESTING-phase-b-live.md`

- [ ] **Step 1: Documenter la cascade dans `CLAUDE.md`**

Dans la section « Moteur autonome », ajouter un sous-bloc « Cascade IA (Phase B) » résumant :
- le flux scrape → `pending_enrichment` (file locale) → `enrichment_worker` → Supabase **enrichi** ;
- le **gate 🔴** : seul le tier `pro` promeut en urgent (`MIN_TIER_FOR_URGENT`), **Pro suspendu** par défaut (plafond 🟡) ;
- les nouveaux modules `engine/` (`router`, `llm_client`, `cascade`, `prompts`, `grounding`, `sink`, `enrich`) ;
- les clés `.env` IA (toutes optionnelles ; sans `GEMINI_API_KEY`, l'enrichissement est désactivé et les opportunités restent en file) ;
- rappel : la cascade n'écrit **que** des opportunités notées (jamais brutes).

- [ ] **Step 2: Écrire la check-list LIVE**

```markdown
# TESTING — Phase B (validation LIVE, obligatoire avant « fini »)

Leçon Phase A : les fixtures ne suffisent pas. Valider contre la VRAIE API Gemini + de vraies opportunités.

## Pré-requis
1. `GEMINI_API_KEY` (free tier, AI Studio) dans `.env`. Laisser `GEMINI_PRO_ENABLED=false`.
2. Au moins une `watchlist_searches` active avec une vraie URL LBC.
3. `python -m pytest tests/ -v` → tout vert (62 Phase A + nouveaux).

## Procédure
1. Lancer `python server.py --auto`.
2. Observer les logs : scrape → mise en file → triage groupé → écriture.
3. Dans Supabase, table `opportunities` : vérifier que les nouvelles lignes ont
   `category` ∈ {interesting, passable} (JAMAIS urgent tant que Pro off), `resale_score` non-null,
   et pour les candidates : `est_market_price`, `est_margin_eur/pct`, `max_buy_price`, `explanation`.
4. Vérifier qu'AUCUNE ligne n'apparaît brute (category null) côté Supabase.
5. Vérifier le grounding : `market_observations` se remplit (cerveau SQLite).
6. Vérifier le comptage : table `llm_usage` incrémente ; pas d'erreur 429 silencieuse.
7. Couper Internet 1 min en plein cycle → les annonces restent en file / outbox, rien n'est perdu,
   et l'écriture reprend au retour.

## Quand Pro sera disponible (plus tard)
- `GEMINI_PRO_ENABLED=true` + `GEMINI_VERIFY_MODEL=gemini-3.1-pro-preview` + `GEMINI_API_KEY` du compte Pro.
- Vérifier que des 🔴 apparaissent enfin, et seulement avec marge ≥ seuils.
```

- [ ] **Step 3: Run the full suite une dernière fois**

Run: `python -m pytest tests/ -v`
Expected: PASS (tout).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/TESTING-phase-b-live.md
git commit -m "docs: cascade IA dans CLAUDE.md + check-list de validation LIVE Phase B"
```

---

## Récapitulatif des tâches

| # | Tâche | Livrable |
|---|---|---|
| 1 | `extract_category` | helper pur URL → catégorie |
| 2 | `pending_enrichment` | file locale du worker |
| 3 | `llm_usage` + `quota_day` | comptage quotas |
| 4 | `LocalSink` | scrape → file (interface Supa) |
| 5 | `grounding` | médiane marché locale |
| 6 | config IA | modèles, gate, seuils (clés optionnelles) |
| 7 | `prompts` | schémas + builders (triage sans urgent) |
| 8 | `LLMRouter` | route/quotas/fallback/gate |
| 9 | `GeminiClient` | REST generateContent (texte + vision) |
| 10 | `cascade` | stages purs + marge + gate 🔴 |
| 11 | `merge_enrichment` | fusion IA → payload |
| 12 | `enrichment_worker` | orchestration file → cascade → Supabase |
| 13 | vérif schéma Supabase | colonnes IA (conditionnel) |
| 14 | câblage `--auto` | LocalSink + worker parallèle |
| 15 | docs + check-list LIVE | CLAUDE.md + TESTING-phase-b-live |

---

## Validation finale (definition of done)

- [ ] `python -m pytest tests/ -v` : **tout vert**, dont les 62 tests Phase A **non modifiés**.
- [ ] Validation **LIVE** déroulée (cf. `docs/TESTING-phase-b-live.md`) : vraies opportunités enrichies, jamais brutes côté Supabase, aucun 🔴 tant que Pro off.
- [ ] API HTTP, scrape manuel, frontend, RLS : inchangés.
- [ ] `CLAUDE.md` à jour (cascade + Pro suspendu).
- [ ] Mémoire projet `phase-b-pro-verifier-suspendu` toujours cohérente.
