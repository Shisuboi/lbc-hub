# Phase A — Fondation moteur — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire le démon autonome (`server.py --auto`) qui scrape les recherches en boucle 24/7, déduplique via un cerveau SQLite local, détecte les baisses de prix, et écrit des opportunités **brutes** (sans IA) dans Supabase — le tout sans casser l'API HTTP existante.

**Architecture:** Un package `engine/` découplé (modules à responsabilité unique : `config`, `parse`, `db`, `prefilter`, `supa`, `scheduler`, `scraper`). La boucle (`scheduler.run_engine`) reçoit ses dépendances par injection (un `scrape_fn`, un `Brain` SQLite, un client `Supa` REST) → testable sans navigateur ni réseau. `server.py` gagne un flag `--auto` qui démarre la boucle en tâche de fond en partageant le **seul** Chromium.

**Tech Stack:** Python 3.11, `aiohttp` (déjà présent), Playwright (déjà présent), `sqlite3` (stdlib), pytest + pytest-aiohttp (`asyncio_mode = auto`). Supabase via REST PostgREST + clé `service_role`. **Aucune nouvelle dépendance.**

**Branche :** `feature/pipeline-revente-opportunites` (déjà créée, spec committée).

**Spec de référence :** `docs/superpowers/specs/2026-05-29-pipeline-revente-opportunites-design.md`

---

## Décisions de cadrage spécifiques à la Phase A

- **Pas d'IA** : la cascade (triage/analyse/photo) est en Phase B. Phase A écrit des opportunités brutes (champs IA = `null`).
- **Pré-filtre minimal inclus** (non-IA, donc légitime ici) : on n'écrit que des annonces neuves/baissées, prix > 0, hors mots-clés exclus. Évite de noyer Supabase pendant les tests.
- **Page 1 uniquement, scan complet** (pas de multi-pages ni d'early-exit en Phase A) : la page 1 triée par date contient les nouveautés ET permet de détecter les baisses de prix des annonces encore en page 1. Multi-pages = raffinement ultérieur.
- **Upsert idempotent** : `opportunities.ad_id` est unique ; insert et baisse de prix passent par un upsert `on_conflict=ad_id` → robuste même si le cerveau SQLite est perdu.
- **Migration Phase A** : crée seulement `opportunities` + `watchlist_searches`. Les autres tables (`member_settings`, `trades`, etc.) seront créées dans leurs phases.

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `engine/__init__.py` | marque le package | Create |
| `engine/config.py` | charge `.env` (URL Supabase + service_role) | Create |
| `engine/parse.py` | helpers purs : `extract_ad_id`, `clean_price` | Create |
| `engine/db.py` | `Brain` : cerveau SQLite (seen_ads, price_observations, market_observations, scrape_log, outbox) | Create |
| `engine/prefilter.py` | `passes_prefilter(ad, search)` (règles non-IA) | Create |
| `engine/supa.py` | `build_opportunity_payload` + client REST `Supa` | Create |
| `engine/scheduler.py` | `normalize_search_url`, `dedup_searches`, `process_search`, `run_engine` | Create |
| `engine/scraper.py` | `extract_ads_from_results(page)` (Playwright, page de résultats) | Create |
| `server.py` | flag `--auto` + bootstrap de la boucle (browser partagé) | Modify |
| `.env.example` | gabarit des secrets | Create |
| `start-agent.bat` | lanceur Windows (autostart) | Create |
| `supabase/migrations/2026-05-29-pipeline-foundation.sql` | tables `opportunities` + `watchlist_searches` + RLS + index | Create |
| `tests/test_engine_*.py` | tests unitaires/intégration | Create |
| `CLAUDE.md` | documenter l'invariant cassé + le moteur | Modify |

---

## Task 1: Scaffolding du package `engine/` + configuration

**Files:**
- Create: `engine/__init__.py`
- Create: `engine/config.py`
- Create: `.env.example`
- Test: `tests/test_engine_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_config.py
import pytest
from engine.config import load_config


def test_load_config_reads_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "SUPABASE_URL=https://demo.supabase.co\n"
        "SUPABASE_SERVICE_KEY=secret123\n",
        encoding="utf-8",
    )
    cfg = load_config(str(env))
    assert cfg["SUPABASE_URL"] == "https://demo.supabase.co"
    assert cfg["SUPABASE_SERVICE_KEY"] == "secret123"


def test_load_config_ignores_comments_and_blanks(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# commentaire\n\nSUPABASE_URL=https://x.co\nSUPABASE_SERVICE_KEY=k\n",
        encoding="utf-8",
    )
    cfg = load_config(str(env))
    assert cfg["SUPABASE_URL"] == "https://x.co"


def test_load_config_missing_key_raises(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SUPABASE_URL=https://x.co\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_KEY"):
        load_config(str(env))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/__init__.py
```

(fichier vide)

```python
# engine/config.py
"""Chargement de la configuration du moteur autonome depuis un fichier .env.

Aucune dépendance externe : on lit le .env à la main puis on superpose os.environ.
"""
import os

REQUIRED_KEYS = ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")


def load_config(env_path: str = ".env") -> dict:
    cfg: dict = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                cfg[key.strip()] = value.strip()
    # Les variables d'environnement réelles ont priorité sur le fichier.
    for key in REQUIRED_KEYS:
        if key in os.environ:
            cfg[key] = os.environ[key]
    missing = [k for k in REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        raise RuntimeError(f"Clés de config manquantes : {', '.join(missing)}")
    return cfg
```

```bash
# .env.example
# Copie ce fichier en `.env` (jamais committé) et remplis les valeurs.
# La service_role est une clé "dieu" : ne JAMAIS la mettre dans le frontend.
SUPABASE_URL=https://pfkuphmpzhdmfwaifywj.supabase.co
SUPABASE_SERVICE_KEY=colle-ici-ta-cle-service_role
# Optionnel (Phase C) : TELEGRAM_BOT_TOKEN=...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Ensure `.env` is gitignored**

Vérifier que `.gitignore` contient `.env`. S'il n'y est pas, l'ajouter :

```bash
# .gitignore (ajouter ces lignes si absentes)
.env
engine/*.sqlite3
lbc_brain.sqlite3
```

- [ ] **Step 6: Commit**

```bash
git add engine/__init__.py engine/config.py .env.example .gitignore tests/test_engine_config.py
git commit -m "feat(engine): scaffolding package + chargement config .env"
```

---

## Task 2: Helpers de parsing purs (`extract_ad_id`, `clean_price`)

**Files:**
- Create: `engine/parse.py`
- Test: `tests/test_engine_parse.py`

> Note DRY : `clean_price` duplique temporairement la version de `server.py`. On consolidera dans un cleanup ultérieur ; ne PAS toucher `server.py` ici (le scraper manuel doit rester stable).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_parse.py
from engine.parse import extract_ad_id, clean_price


def test_extract_ad_id_standard_url():
    url = "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678"
    assert extract_ad_id(url) == "2912345678"


def test_extract_ad_id_with_trailing_slash_and_query():
    url = "https://www.leboncoin.fr/ad/informatique/2999000111/?foo=bar"
    assert extract_ad_id(url) == "2999000111"


def test_extract_ad_id_htm_suffix():
    url = "https://www.leboncoin.fr/velos/1234567890.htm"
    assert extract_ad_id(url) == "1234567890"


def test_extract_ad_id_none_when_no_digits():
    assert extract_ad_id("https://www.leboncoin.fr/recherche") is None


def test_clean_price_french_format():
    assert clean_price("1 200 €") == 1200.0


def test_clean_price_decimal_comma():
    assert clean_price("1 000,50 €") == 1000.5


def test_clean_price_empty_returns_zero():
    assert clean_price("") == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.parse'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/parse.py
"""Helpers de parsing purs (sans I/O) — faciles à tester."""
import re
import unicodedata

_AD_ID_RE = re.compile(r"/(\d{6,})(?:\.htm)?/?(?:\?|$)")


def extract_ad_id(url: str) -> str | None:
    """Extrait l'ID numérique stable d'une URL d'annonce Leboncoin."""
    if not url:
        return None
    m = _AD_ID_RE.search(url)
    return m.group(1) if m else None


def clean_price(price_text: str) -> float:
    """Parse un prix au format français (espaces fines, € , virgule décimale)."""
    cleaned = unicodedata.normalize("NFKD", price_text or "")
    cleaned = re.sub(r"[^\d.,]", "", cleaned)
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_parse.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/parse.py tests/test_engine_parse.py
git commit -m "feat(engine): helpers extract_ad_id et clean_price"
```

---

## Task 3: Cerveau SQLite — `Brain.upsert_ad` (dédup + baisse de prix)

**Files:**
- Create: `engine/db.py`
- Test: `tests/test_engine_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_db.py
from engine.db import Brain


def make_brain():
    return Brain(":memory:")


def test_first_time_ad_is_new():
    b = make_brain()
    assert b.upsert_ad("111", 100.0, now=1000) == "new"


def test_same_price_is_seen():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    assert b.upsert_ad("111", 100.0, now=2000) == "seen"


def test_price_drop_detected():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    assert b.upsert_ad("111", 80.0, now=2000) == "price_drop"


def test_price_increase_is_seen():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    assert b.upsert_ad("111", 120.0, now=2000) == "seen"


def test_last_price_is_updated_after_drop():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    b.upsert_ad("111", 80.0, now=2000)
    # une nouvelle baisse repart bien de 80, pas de 100
    assert b.upsert_ad("111", 70.0, now=3000) == "price_drop"
    assert b.upsert_ad("111", 80.0, now=4000) == "seen"


def test_price_observations_recorded_on_change_only():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)   # 1 obs (création)
    b.upsert_ad("111", 100.0, now=2000)   # pas d'obs (inchangé)
    b.upsert_ad("111", 80.0, now=3000)    # 1 obs (baisse)
    rows = b.conn.execute(
        "select price from price_observations where ad_id='111' order by observed_at"
    ).fetchall()
    assert [r["price"] for r in rows] == [100.0, 80.0]


def test_previous_price_helper():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    b.upsert_ad("111", 80.0, now=2000)
    assert b.previous_price("111") == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.db'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/db.py
"""Le cerveau SQLite local du moteur : dédup, historique de prix, marché, logs, outbox."""
import sqlite3
import time
import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_ads (
    ad_id TEXT PRIMARY KEY,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    last_price REAL,
    prev_price REAL,
    status TEXT DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS price_observations (
    ad_id TEXT NOT NULL,
    price REAL NOT NULL,
    observed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS price_obs_ad_idx ON price_observations(ad_id);

CREATE TABLE IF NOT EXISTS market_observations (
    categorie TEXT,
    prix REAL,
    ville TEXT,
    observed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS market_obs_cat_idx ON market_observations(categorie);

CREATE TABLE IF NOT EXISTS scrape_log (
    search_id TEXT,
    last_run_at INTEGER NOT NULL,
    status TEXT,
    blocked_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    retries INTEGER DEFAULT 0
);
"""


class Brain:
    def __init__(self, path: str = "lbc_brain.sqlite3"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_ad(self, ad_id: str, price: float, now: int | None = None) -> str:
        """Retourne 'new', 'price_drop' ou 'seen'. Enregistre une observation si le prix change."""
        now = int(now if now is not None else time.time())
        row = self.conn.execute(
            "SELECT last_price FROM seen_ads WHERE ad_id = ?", (ad_id,)
        ).fetchone()

        if row is None:
            self.conn.execute(
                "INSERT INTO seen_ads (ad_id, first_seen_at, last_seen_at, last_price, prev_price) "
                "VALUES (?, ?, ?, ?, NULL)",
                (ad_id, now, now, price),
            )
            self.conn.execute(
                "INSERT INTO price_observations (ad_id, price, observed_at) VALUES (?, ?, ?)",
                (ad_id, price, now),
            )
            self.conn.commit()
            return "new"

        last_price = row["last_price"]
        event = "seen"
        if last_price is None or price != last_price:
            self.conn.execute(
                "INSERT INTO price_observations (ad_id, price, observed_at) VALUES (?, ?, ?)",
                (ad_id, price, now),
            )
            self.conn.execute(
                "UPDATE seen_ads SET last_seen_at = ?, prev_price = last_price, last_price = ? WHERE ad_id = ?",
                (now, price, ad_id),
            )
            if last_price is not None and price < last_price:
                event = "price_drop"
        else:
            self.conn.execute(
                "UPDATE seen_ads SET last_seen_at = ? WHERE ad_id = ?", (now, ad_id)
            )
        self.conn.commit()
        return event

    def previous_price(self, ad_id: str) -> float | None:
        row = self.conn.execute(
            "SELECT prev_price FROM seen_ads WHERE ad_id = ?", (ad_id,)
        ).fetchone()
        return row["prev_price"] if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_db.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/db.py tests/test_engine_db.py
git commit -m "feat(engine): Brain SQLite - dedup + detection baisse de prix"
```

---

## Task 4: Cerveau SQLite — observations marché, logs, outbox

**Files:**
- Modify: `engine/db.py`
- Test: `tests/test_engine_db.py` (ajouts)

- [ ] **Step 1: Write the failing test (append au fichier)**

```python
# tests/test_engine_db.py  (ajouter à la fin)
def test_record_market_obs_and_count():
    b = make_brain()
    b.record_market_obs("consoles", 100.0, "Bordeaux", now=1000)
    b.record_market_obs("consoles", 120.0, "Lyon", now=1001)
    rows = b.conn.execute(
        "select prix from market_observations where categorie='consoles' order by observed_at"
    ).fetchall()
    assert [r["prix"] for r in rows] == [100.0, 120.0]


def test_log_scrape_writes_row():
    b = make_brain()
    b.log_scrape("search-1", "ok", blocked=0, now=1000)
    row = b.conn.execute("select * from scrape_log").fetchone()
    assert row["search_id"] == "search-1"
    assert row["status"] == "ok"


def test_outbox_queue_and_pop_fifo():
    b = make_brain()
    b.queue_outbox({"a": 1}, now=1000)
    b.queue_outbox({"b": 2}, now=1001)
    items = b.peek_outbox(limit=10)
    assert [it["payload"] for it in items] == [{"a": 1}, {"b": 2}]
    b.delete_outbox(items[0]["id"])
    remaining = b.peek_outbox(limit=10)
    assert [it["payload"] for it in remaining] == [{"b": 2}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_db.py -v`
Expected: FAIL with `AttributeError: 'Brain' object has no attribute 'record_market_obs'`

- [ ] **Step 3: Write minimal implementation (ajouter ces méthodes à la classe `Brain`)**

```python
# engine/db.py  (ajouter dans la classe Brain)
    def record_market_obs(self, categorie: str, prix: float, ville: str | None, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO market_observations (categorie, prix, ville, observed_at) VALUES (?, ?, ?, ?)",
            (categorie, prix, ville, now),
        )
        self.conn.commit()

    def log_scrape(self, search_id: str, status: str, blocked: int = 0, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO scrape_log (search_id, last_run_at, status, blocked_count) VALUES (?, ?, ?, ?)",
            (search_id, now, status, blocked),
        )
        self.conn.commit()

    def queue_outbox(self, payload: dict, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO outbox (payload, created_at, retries) VALUES (?, ?, 0)",
            (json.dumps(payload), now),
        )
        self.conn.commit()

    def peek_outbox(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, payload, retries FROM outbox ORDER BY id ASC LIMIT ?", (limit,)
        ).fetchall()
        return [{"id": r["id"], "payload": json.loads(r["payload"]), "retries": r["retries"]} for r in rows]

    def delete_outbox(self, outbox_id: int) -> None:
        self.conn.execute("DELETE FROM outbox WHERE id = ?", (outbox_id,))
        self.conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_db.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/db.py tests/test_engine_db.py
git commit -m "feat(engine): Brain - market_observations, scrape_log, outbox"
```

---

## Task 5: Pré-filtre par règles (non-IA)

**Files:**
- Create: `engine/prefilter.py`
- Test: `tests/test_engine_prefilter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_prefilter.py
from engine.prefilter import passes_prefilter


def ad(title="PS5 occasion", price=200.0):
    return {"ad_id": "1", "title": title, "price": price, "url": "u", "city": "Paris", "image_url": None}


def test_rejects_zero_price():
    assert passes_prefilter(ad(price=0.0), {}) is False


def test_rejects_negative_price():
    assert passes_prefilter(ad(price=-5.0), {}) is False


def test_accepts_normal_ad_with_no_constraints():
    assert passes_prefilter(ad(), {}) is True


def test_rejects_excluded_keyword_case_insensitive():
    search = {"exclude_keywords": "pour pieces, hs, cassé"}
    assert passes_prefilter(ad(title="PS5 HS pour pieces"), search) is False


def test_accepts_when_no_excluded_keyword_matches():
    search = {"exclude_keywords": "pour pieces, hs"}
    assert passes_prefilter(ad(title="PS5 nickel"), search) is True


def test_rejects_above_price_max():
    search = {"price_max": 150}
    assert passes_prefilter(ad(price=200.0), search) is False


def test_accepts_below_price_max():
    search = {"price_max": 300}
    assert passes_prefilter(ad(price=200.0), search) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_prefilter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.prefilter'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/prefilter.py
"""Pré-filtre par règles, sans IA. Évite d'écrire du bruit dans Supabase."""


def passes_prefilter(ad: dict, search: dict) -> bool:
    price = ad.get("price") or 0.0
    if price <= 0:
        return False

    price_max = search.get("price_max")
    if price_max is not None and price > float(price_max):
        return False

    raw_excludes = search.get("exclude_keywords") or ""
    excludes = [w.strip().lower() for w in raw_excludes.split(",") if w.strip()]
    title = (ad.get("title") or "").lower()
    if any(word in title for word in excludes):
        return False

    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_prefilter.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/prefilter.py tests/test_engine_prefilter.py
git commit -m "feat(engine): pre-filtre par regles (prix + mots-cles exclus)"
```

---

## Task 6: Construction du payload d'opportunité (pur)

**Files:**
- Create: `engine/supa.py`
- Test: `tests/test_engine_supa_payload.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_supa_payload.py
from engine.supa import build_opportunity_payload


def sample_ad():
    return {
        "ad_id": "2912345678",
        "title": "PS5 Slim",
        "price": 250.0,
        "url": "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678",
        "city": "Bordeaux",
        "image_url": "https://img.leboncoin.fr/x.jpg",
    }


def sample_search():
    return {"id": "search-uuid", "platform": "leboncoin"}


def test_payload_core_fields():
    p = build_opportunity_payload(sample_ad(), sample_search(), event="new", scraped_at_iso="2026-05-29T10:00:00Z")
    assert p["ad_id"] == "2912345678"
    assert p["title"] == "PS5 Slim"
    assert p["price"] == 250.0
    assert p["url"].endswith("2912345678")
    assert p["source_search_id"] == "search-uuid"
    assert p["platform"] == "leboncoin"
    assert p["location_city"] == "Bordeaux"
    assert p["image_url"].endswith("x.jpg")
    assert p["status"] == "active"
    assert p["scraped_at"] == "2026-05-29T10:00:00Z"


def test_payload_new_event_not_price_dropped():
    p = build_opportunity_payload(sample_ad(), sample_search(), event="new", scraped_at_iso="t", previous_price=None)
    assert p["price_dropped"] is False
    assert p["previous_price"] is None


def test_payload_price_drop_event():
    p = build_opportunity_payload(sample_ad(), sample_search(), event="price_drop", scraped_at_iso="t", previous_price=300.0)
    assert p["price_dropped"] is True
    assert p["previous_price"] == 300.0


def test_payload_ai_fields_are_null():
    p = build_opportunity_payload(sample_ad(), sample_search(), event="new", scraped_at_iso="t")
    assert p["category"] is None
    assert p["resale_score"] is None
    assert p["est_margin_eur"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_supa_payload.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.supa'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/supa.py
"""Pont vers Supabase via REST PostgREST (clé service_role).

Phase A : on écrit des opportunités BRUTES (champs IA = null). La Phase B enrichira.
"""
import aiohttp


def build_opportunity_payload(
    ad: dict,
    search: dict,
    event: str,
    scraped_at_iso: str,
    previous_price: float | None = None,
) -> dict:
    """Construit la ligne `opportunities` à upserter. Champs IA laissés à null (Phase B)."""
    return {
        "ad_id": ad["ad_id"],
        "source_search_id": search.get("id"),
        "platform": search.get("platform", "leboncoin"),
        "title": ad.get("title"),
        "price": ad.get("price"),
        "url": ad.get("url"),
        "image_url": ad.get("image_url"),
        "location_city": ad.get("city"),
        "location_postal": ad.get("postal"),
        "category": None,
        "resale_score": None,
        "est_market_price": None,
        "est_margin_eur": None,
        "est_margin_pct": None,
        "max_buy_price": None,
        "is_lot": None,
        "signals": None,
        "explanation": None,
        "photo_verdict": None,
        "price_dropped": event == "price_drop",
        "previous_price": previous_price if event == "price_drop" else None,
        "model_used": None,
        "status": "active",
        "scraped_at": scraped_at_iso,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_supa_payload.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/supa.py tests/test_engine_supa_payload.py
git commit -m "feat(engine): build_opportunity_payload (opportunite brute)"
```

---

## Task 7: Client REST `Supa` (lecture watchlist + upsert opportunité)

**Files:**
- Modify: `engine/supa.py`
- Test: `tests/test_engine_supa_client.py`

- [ ] **Step 1: Write the failing test (mock PostgREST avec aiohttp_server)**

```python
# tests/test_engine_supa_client.py
import json
import pytest
from aiohttp import web, ClientSession
from engine.supa import Supa


@pytest.fixture
async def mock_supabase(aiohttp_server):
    captured = {"inserts": [], "headers": []}

    async def get_searches(request):
        captured["headers"].append(dict(request.headers))
        return web.json_response([
            {"id": "s1", "source_url": "https://lbc/u1", "platform": "leboncoin", "active": True},
        ])

    async def post_opportunity(request):
        body = await request.json()
        captured["inserts"].append(body)
        return web.json_response({}, status=201)

    app = web.Application()
    app.router.add_get("/rest/v1/watchlist_searches", get_searches)
    app.router.add_post("/rest/v1/opportunities", post_opportunity)
    server = await aiohttp_server(app)
    server.captured = captured
    return server


async def test_fetch_active_searches(mock_supabase):
    base = str(mock_supabase.make_url("")).rstrip("/")
    async with ClientSession() as session:
        supa = Supa(base, "service-key", session)
        searches = await supa.fetch_active_searches()
    assert len(searches) == 1
    assert searches[0]["id"] == "s1"
    # la clé service_role doit être envoyée
    last = mock_supabase.captured["headers"][-1]
    assert last.get("apikey") == "service-key"
    assert last.get("Authorization") == "Bearer service-key"


async def test_insert_opportunity_posts_payload(mock_supabase):
    base = str(mock_supabase.make_url("")).rstrip("/")
    async with ClientSession() as session:
        supa = Supa(base, "service-key", session)
        await supa.insert_opportunity({"ad_id": "42", "title": "x"})
    assert mock_supabase.captured["inserts"][-1]["ad_id"] == "42"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_supa_client.py -v`
Expected: FAIL with `ImportError: cannot import name 'Supa'`

- [ ] **Step 3: Write minimal implementation (ajouter à `engine/supa.py`)**

```python
# engine/supa.py  (ajouter en bas)
class Supa:
    """Client REST minimal vers PostgREST (Supabase) avec la clé service_role."""

    def __init__(self, base_url: str, service_key: str, session: aiohttp.ClientSession):
        self.base = base_url.rstrip("/")
        self.key = service_key
        self.session = session

    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    async def fetch_active_searches(self) -> list[dict]:
        url = f"{self.base}/rest/v1/watchlist_searches"
        params = {"active": "eq.true", "select": "*"}
        async with self.session.get(url, params=params, headers=self._headers()) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def insert_opportunity(self, payload: dict) -> None:
        """Upsert sur ad_id (idempotent même si le cerveau SQLite est perdu)."""
        url = f"{self.base}/rest/v1/opportunities"
        params = {"on_conflict": "ad_id"}
        headers = self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"})
        async with self.session.post(url, params=params, json=payload, headers=headers) as resp:
            resp.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_supa_client.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/supa.py tests/test_engine_supa_client.py
git commit -m "feat(engine): client REST Supa (fetch watchlist + upsert opportunite)"
```

---

## Task 8: Ordonnancement — `normalize_search_url` + `dedup_searches`

**Files:**
- Create: `engine/scheduler.py`
- Test: `tests/test_engine_scheduler_dedup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_scheduler_dedup.py
from engine.scheduler import normalize_search_url, dedup_searches


def test_normalize_strips_volatile_params_and_lowercases_host():
    a = "https://WWW.leboncoin.fr/recherche?text=ps5&sort=time&page=2"
    b = "https://www.leboncoin.fr/recherche?text=ps5"
    assert normalize_search_url(a) == normalize_search_url(b)


def test_normalize_is_order_independent():
    a = "https://www.leboncoin.fr/recherche?text=ps5&price=10-200"
    b = "https://www.leboncoin.fr/recherche?price=10-200&text=ps5"
    assert normalize_search_url(a) == normalize_search_url(b)


def test_dedup_keeps_one_per_normalized_url():
    searches = [
        {"id": "1", "source_url": "https://www.leboncoin.fr/recherche?text=ps5&sort=time"},
        {"id": "2", "source_url": "https://www.leboncoin.fr/recherche?text=ps5"},
        {"id": "3", "source_url": "https://www.leboncoin.fr/recherche?text=switch"},
    ]
    out = dedup_searches(searches)
    assert len(out) == 2
    urls = {normalize_search_url(s["source_url"]) for s in out}
    assert len(urls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_scheduler_dedup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.scheduler'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/scheduler.py
"""Boucle autonome : ordonnancement round-robin, dédup des recherches, traitement."""
from urllib.parse import urlparse, parse_qsl, urlencode

# Paramètres d'URL volatils à ignorer pour la déduplication des recherches.
_VOLATILE_PARAMS = {"sort", "page", "order"}


def normalize_search_url(url: str) -> str:
    """Forme canonique d'une URL de recherche : host minuscule, params triés, volatils retirés."""
    p = urlparse(url.strip())
    host = p.netloc.lower()
    params = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _VOLATILE_PARAMS]
    params.sort()
    query = urlencode(params)
    path = p.path.rstrip("/")
    return f"{p.scheme.lower()}://{host}{path}?{query}"


def dedup_searches(searches: list[dict]) -> list[dict]:
    """Garde une seule recherche par URL normalisée (deux membres, même recherche = 1 scrape)."""
    seen: set[str] = set()
    out: list[dict] = []
    for s in searches:
        key = normalize_search_url(s.get("source_url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_scheduler_dedup.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/scheduler.py tests/test_engine_scheduler_dedup.py
git commit -m "feat(engine): normalisation + dedup des recherches"
```

---

## Task 9: Ordonnancement — `process_search` + `run_engine`

**Files:**
- Modify: `engine/scheduler.py`
- Test: `tests/test_engine_scheduler_run.py`

- [ ] **Step 1: Write the failing test (fakes injectés : pas de navigateur, pas de réseau)**

```python
# tests/test_engine_scheduler_run.py
import asyncio
import pytest
from engine.db import Brain
from engine.scheduler import process_search, run_engine


class FakeSupa:
    def __init__(self, searches):
        self._searches = searches
        self.inserted = []

    async def fetch_active_searches(self):
        return list(self._searches)

    async def insert_opportunity(self, payload):
        self.inserted.append(payload)


async def test_process_search_inserts_only_new_and_filtered():
    brain = Brain(":memory:")
    supa = FakeSupa([])
    search = {"id": "s1", "source_url": "u", "platform": "leboncoin", "exclude_keywords": "hs"}
    ads = [
        {"ad_id": "1", "title": "PS5 nickel", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None},
        {"ad_id": "2", "title": "PS5 HS", "price": 50.0, "url": "u2", "city": "Lyon", "image_url": None},  # exclu
        {"ad_id": "3", "title": "gratuit", "price": 0.0, "url": "u3", "city": "Nice", "image_url": None},   # prix 0
    ]

    async def scrape_fn(url):
        return ads

    counts = await process_search(scrape_fn, brain, supa, search)
    assert counts["new"] == 1
    assert len(supa.inserted) == 1
    assert supa.inserted[0]["ad_id"] == "1"


async def test_process_search_second_cycle_dedups():
    brain = Brain(":memory:")
    supa = FakeSupa([])
    search = {"id": "s1", "source_url": "u", "platform": "leboncoin"}
    ads = [{"ad_id": "1", "title": "PS5", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None}]

    async def scrape_fn(url):
        return ads

    await process_search(scrape_fn, brain, supa, search)
    counts = await process_search(scrape_fn, brain, supa, search)  # 2e passage
    assert counts["new"] == 0
    assert len(supa.inserted) == 1  # toujours 1 seul insert


async def test_process_search_price_drop_reinserts():
    brain = Brain(":memory:")
    supa = FakeSupa([])
    search = {"id": "s1", "source_url": "u", "platform": "leboncoin"}

    async def scrape_high(url):
        return [{"ad_id": "1", "title": "PS5", "price": 300.0, "url": "u1", "city": "Paris", "image_url": None}]

    async def scrape_low(url):
        return [{"ad_id": "1", "title": "PS5", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None}]

    await process_search(scrape_high, brain, supa, search)
    counts = await process_search(scrape_low, brain, supa, search)
    assert counts["price_drop"] == 1
    assert supa.inserted[-1]["price_dropped"] is True
    assert supa.inserted[-1]["previous_price"] == 300.0


async def test_run_engine_stops_after_max_cycles():
    brain = Brain(":memory:")
    supa = FakeSupa([{"id": "s1", "source_url": "u", "platform": "leboncoin"}])

    async def scrape_fn(url):
        return [{"ad_id": "1", "title": "PS5", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None}]

    stop = asyncio.Event()
    await run_engine(brain, supa, scrape_fn, stop, cycle_pause=0, max_cycles=2)
    # 1 insert au cycle 1, rien au cycle 2 (dédup)
    assert len(supa.inserted) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_scheduler_run.py -v`
Expected: FAIL with `ImportError: cannot import name 'process_search'`

- [ ] **Step 3: Write minimal implementation (ajouter à `engine/scheduler.py`)**

```python
# engine/scheduler.py  (ajouter ces imports en haut)
import asyncio
import time
from datetime import datetime, timezone
from engine.prefilter import passes_prefilter
from engine.supa import build_opportunity_payload
```

```python
# engine/scheduler.py  (ajouter en bas)
async def process_search(scrape_fn, brain, supa, search: dict) -> dict:
    """Scrape une recherche, déduplique, écrit les opportunités neuves/baissées.

    scrape_fn: coroutine(url) -> list[ad]   (injectée → testable sans navigateur)
    """
    counts = {"new": 0, "price_drop": 0, "seen": 0, "filtered": 0}
    ads = await scrape_fn(search.get("source_url", ""))
    scraped_at_iso = datetime.now(timezone.utc).isoformat()

    for ad in ads:
        if not ad.get("ad_id"):
            continue
        if not passes_prefilter(ad, search):
            counts["filtered"] += 1
            continue
        event = brain.upsert_ad(ad["ad_id"], float(ad.get("price") or 0.0))
        if event == "seen":
            counts["seen"] += 1
            continue
        prev = brain.previous_price(ad["ad_id"]) if event == "price_drop" else None
        payload = build_opportunity_payload(ad, search, event, scraped_at_iso, previous_price=prev)
        await supa.insert_opportunity(payload)
        counts[event] += 1

    brain.log_scrape(search.get("id", "?"), "ok")
    return counts


async def run_engine(brain, supa, scrape_fn, stop_event, cycle_pause: float = 60.0, max_cycles=None) -> None:
    """Boucle round-robin. `max_cycles` (tests) limite le nombre de tours ; None = infini."""
    cycle = 0
    while not stop_event.is_set():
        try:
            searches = dedup_searches(await supa.fetch_active_searches())
            for s in searches:
                if stop_event.is_set():
                    break
                try:
                    await process_search(scrape_fn, brain, supa, s)
                except Exception as exc:  # un échec sur une recherche n'arrête pas le moteur
                    brain.log_scrape(s.get("id", "?"), f"error: {exc}")
        except Exception as exc:
            print(f"[engine] cycle error: {exc}")

        cycle += 1
        if max_cycles is not None and cycle >= max_cycles:
            return
        if cycle_pause:
            await asyncio.sleep(cycle_pause)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_scheduler_run.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/scheduler.py tests/test_engine_scheduler_run.py
git commit -m "feat(engine): process_search + boucle run_engine (round-robin, resilient)"
```

---

## Task 10: Scraper page de résultats (Playwright)

**Files:**
- Create: `engine/scraper.py`
- Test: `tests/test_engine_scraper.py`

> Ce test lance un Chromium headless et charge une page de résultats **factice** via `set_content`. Il valide la logique d'extraction (sélecteurs + parsing), pas la vraie page LBC (vérifiée manuellement en Task 15).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_scraper.py
import pytest
from playwright.async_api import async_playwright
from engine.scraper import extract_ads_from_results

FIXTURE_HTML = """
<html><body>
<ul>
  <li>
    <a data-qa-id="aditem_container" href="/ad/consoles_jeux_video/2912345678">
      <p data-qa-id="aditem_title">PS5 Slim</p>
      <span data-qa-id="aditem_price">250 €</span>
      <p data-qa-id="aditem_location">Bordeaux 33000</p>
      <img src="https://img.leboncoin.fr/a.jpg"/>
    </a>
  </li>
  <li>
    <a data-qa-id="aditem_container" href="/ad/informatique/2999000111">
      <p data-qa-id="aditem_title">PC portable</p>
      <span data-qa-id="aditem_price">1 200 €</span>
      <p data-qa-id="aditem_location">Lyon 69000</p>
      <img src="https://img.leboncoin.fr/b.jpg"/>
    </a>
  </li>
</ul>
</body></html>
"""


async def test_extract_ads_from_results_parses_fixture():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(FIXTURE_HTML)
        ads = await extract_ads_from_results(page)
        await browser.close()

    assert len(ads) == 2
    first = ads[0]
    assert first["ad_id"] == "2912345678"
    assert first["title"] == "PS5 Slim"
    assert first["price"] == 250.0
    assert first["city"] == "Bordeaux 33000"
    assert first["url"] == "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678"
    assert first["image_url"] == "https://img.leboncoin.fr/a.jpg"
    assert ads[1]["price"] == 1200.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_scraper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.scraper'`
(Si Chromium n'est pas installé : `python -m playwright install chromium` d'abord.)

- [ ] **Step 3: Write minimal implementation**

```python
# engine/scraper.py
"""Extraction des annonces depuis une page de RÉSULTATS Leboncoin (pas de page détail).

On ne lit que ce que la liste expose déjà : id, titre, prix, ville, miniature, URL.
"""
from urllib.parse import urljoin
from engine.parse import extract_ad_id, clean_price

_BASE = "https://www.leboncoin.fr"
_CONTAINER_SEL = 'a[data-qa-id="aditem_container"], a[href*="/ad/"]'


async def extract_ads_from_results(page) -> list[dict]:
    """Retourne une liste d'annonces depuis la page de résultats déjà chargée."""
    ads: list[dict] = []
    seen_ids: set[str] = set()
    containers = await page.query_selector_all(_CONTAINER_SEL)

    for el in containers:
        href = await el.get_attribute("href")
        if not href or "/ad/" not in href:
            continue
        url = urljoin(_BASE, href)
        ad_id = extract_ad_id(url)
        if not ad_id or ad_id in seen_ids:
            continue
        seen_ids.add(ad_id)

        title_el = await el.query_selector('[data-qa-id="aditem_title"], p[data-test-id="adcard-title"]')
        price_el = await el.query_selector('[data-qa-id="aditem_price"], span[data-test-id="price"]')
        loc_el = await el.query_selector('[data-qa-id="aditem_location"]')
        img_el = await el.query_selector("img")

        title = (await title_el.inner_text()).strip() if title_el else ""
        price = clean_price(await price_el.inner_text()) if price_el else 0.0
        city = (await loc_el.inner_text()).strip() if loc_el else None
        image_url = (await img_el.get_attribute("src")) if img_el else None

        ads.append({
            "ad_id": ad_id,
            "title": title,
            "price": price,
            "url": url,
            "city": city,
            "image_url": image_url,
        })

    return ads
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_scraper.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add engine/scraper.py tests/test_engine_scraper.py
git commit -m "feat(engine): extraction des annonces depuis la page de resultats"
```

---

## Task 11: Migration Supabase (tables `opportunities` + `watchlist_searches`)

**Files:**
- Create: `supabase/migrations/2026-05-29-pipeline-foundation.sql`

> Pas de test automatisé (SQL appliqué à la main dans le Dashboard Supabase). Le contenu doit être exact et idempotent.

- [ ] **Step 1: Write the migration file**

```sql
-- supabase/migrations/2026-05-29-pipeline-foundation.sql
-- Phase A — Fondation du pipeline de revente.
-- À exécuter dans Supabase Dashboard → SQL Editor → New query.

-- ===== WATCHLIST SEARCHES =====
create table if not exists public.watchlist_searches (
    id              uuid primary key default gen_random_uuid(),
    owner_id        uuid not null references public.profiles(id) on delete cascade,
    title           text not null,
    criteria        text default '',
    source_url      text not null,
    platform        text not null default 'leboncoin'
                    check (platform in ('leboncoin','ebay','vinted','other')),
    geo_postal      text,
    geo_radius_km   int,
    price_max       float,
    exclude_keywords text default '',
    min_margin_eur  float,
    min_margin_pct  float,
    active          boolean not null default true,
    created_at      timestamptz not null default now()
);
create index if not exists watchlist_owner_idx  on public.watchlist_searches(owner_id);
create index if not exists watchlist_active_idx on public.watchlist_searches(active) where active;

-- ===== OPPORTUNITIES =====
-- Champs IA nullable (remplis en Phase B). Upsert sur ad_id (idempotent).
create table if not exists public.opportunities (
    id                uuid primary key default gen_random_uuid(),
    ad_id             text not null unique,
    source_search_id  uuid references public.watchlist_searches(id) on delete set null,
    platform          text not null default 'leboncoin',
    title             text,
    price             float,
    url               text,
    image_url         text,
    location_city     text,
    location_postal   text,
    lat               float,
    lon               float,
    category          text check (category in ('urgent','interesting','passable')),
    resale_score      float,
    est_market_price  float,
    est_margin_eur    float,
    est_margin_pct    float,
    max_buy_price     float,
    is_lot            boolean,
    lot_unit_price    float,
    lot_notes         text,
    signals           jsonb,
    explanation       text,
    photo_verdict     text,
    price_dropped     boolean default false,
    previous_price    float,
    model_used        text,
    status            text not null default 'active',
    first_seen_at     timestamptz,
    scraped_at        timestamptz,
    created_at        timestamptz not null default now()
);
create index if not exists opp_created_idx  on public.opportunities(created_at desc);
create index if not exists opp_category_idx on public.opportunities(category);
create index if not exists opp_search_idx   on public.opportunities(source_search_id);

-- ===== RLS =====
alter table public.watchlist_searches enable row level security;
alter table public.opportunities enable row level security;

-- watchlist : tout membre authentifié lit (recherches partagées au groupe) ;
-- chacun n'écrit/édite que les siennes.
create policy "watchlist_select_all" on public.watchlist_searches
    for select using (auth.role() = 'authenticated');
create policy "watchlist_insert_own" on public.watchlist_searches
    for insert with check (auth.uid() = owner_id);
create policy "watchlist_update_own" on public.watchlist_searches
    for update using (auth.uid() = owner_id);
create policy "watchlist_delete_own" on public.watchlist_searches
    for delete using (auth.uid() = owner_id);

-- opportunities : lecture par tout membre authentifié ; AUCUNE écriture via anon/JWT
-- (seul le moteur écrit, et il passe par service_role qui bypass RLS).
create policy "opp_select_all" on public.opportunities
    for select using (auth.role() = 'authenticated');
```

- [ ] **Step 2: Apply the migration (manuel, à faire par Tristan)**

1. Supabase Dashboard → SQL Editor → New query.
2. Coller le contenu de `supabase/migrations/2026-05-29-pipeline-foundation.sql`.
3. Run. Vérifier « Success. No rows returned ».
4. Table Editor → confirmer la présence de `watchlist_searches` et `opportunities`.

- [ ] **Step 3: Seed une recherche de test**

Dans SQL Editor (remplacer l'UUID par celui d'un profil existant : `select id, username from profiles;`) :

```sql
insert into public.watchlist_searches (owner_id, title, source_url, exclude_keywords, price_max)
values (
  '<TON_PROFILE_UUID>',
  'PS5 test',
  'https://www.leboncoin.fr/recherche?text=ps5&sort=time',
  'pour pieces, hs, cassé',
  400
);
```

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/2026-05-29-pipeline-foundation.sql
git commit -m "feat(db): migration Phase A - tables opportunities + watchlist_searches + RLS"
```

---

## Task 12: Câbler le flag `--auto` dans `server.py`

**Files:**
- Modify: `server.py` (fonction `main()` + nouveau bootstrap moteur)
- Test: `tests/test_engine_bootstrap.py`

> On garde l'API HTTP intacte. `--auto` démarre la boucle en tâche de fond qui partage le **seul** Chromium via `ensure_browser()` + un verrou.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_bootstrap.py
from engine.bootstrap import make_scrape_fn


async def test_make_scrape_fn_uses_browser_and_extractor(monkeypatch):
    calls = {"goto": [], "extracted": False}

    class FakePage:
        async def goto(self, url, **kw):
            calls["goto"].append(url)
        async def wait_for_timeout(self, ms):
            pass
        async def close(self):
            pass

    class FakeContext:
        async def new_page(self):
            return FakePage()

    async def fake_get_context():
        return FakeContext()

    async def fake_extract(page):
        calls["extracted"] = True
        return [{"ad_id": "1", "title": "x", "price": 10.0, "url": "u", "city": None, "image_url": None}]

    lock = __import__("asyncio").Lock()
    scrape_fn = make_scrape_fn(fake_get_context, fake_extract, lock)
    ads = await scrape_fn("https://lbc/u1")

    assert calls["goto"] == ["https://lbc/u1"]
    assert calls["extracted"] is True
    assert ads[0]["ad_id"] == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_bootstrap.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.bootstrap'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/bootstrap.py
"""Câblage du moteur autonome au reste de server.py (browser partagé + verrou)."""
import asyncio


def make_scrape_fn(get_context, extract_fn, scrape_lock: asyncio.Lock):
    """Fabrique un scrape_fn(url) qui réutilise le Chromium partagé, sérialisé par un verrou.

    get_context: coroutine() -> contexte Playwright (browser partagé)
    extract_fn:  coroutine(page) -> list[ad]   (= engine.scraper.extract_ads_from_results)
    scrape_lock: asyncio.Lock pour ne jamais naviguer en parallèle (manuel vs auto)
    """
    async def scrape_fn(url: str) -> list:
        async with scrape_lock:
            context = await get_context()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                return await extract_fn(page)
            finally:
                await page.close()
    return scrape_fn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_bootstrap.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Wire `--auto` into `server.py`**

Modifier `server.py`. Ajouter en haut du fichier (après les imports existants) :

```python
# server.py  (ajouter aux imports)
import argparse
import aiohttp
from engine.config import load_config
from engine.db import Brain
from engine.supa import Supa
from engine.scheduler import run_engine
from engine.bootstrap import make_scrape_fn
from engine.scraper import extract_ads_from_results

# Verrou global : scrape manuel et scrape auto ne naviguent jamais en même temps.
scrape_lock = asyncio.Lock()
```

Ajouter cette fonction de démarrage du moteur (avant `def create_app`) :

```python
# server.py  (nouvelle fonction)
async def start_autonomous_engine(app):
    """Démarre la boucle autonome en tâche de fond (appelée via app.on_startup)."""
    cfg = load_config()
    brain = Brain("lbc_brain.sqlite3")
    session = aiohttp.ClientSession()
    supa = Supa(cfg["SUPABASE_URL"], cfg["SUPABASE_SERVICE_KEY"], session)

    async def get_context():
        await ensure_browser()
        return job_state.context

    scrape_fn = make_scrape_fn(get_context, extract_ads_from_results, scrape_lock)
    stop_event = asyncio.Event()

    app["engine_stop"] = stop_event
    app["engine_session"] = session
    app["engine_brain"] = brain
    app["engine_task"] = asyncio.create_task(
        run_engine(brain, supa, scrape_fn, stop_event, cycle_pause=60.0)
    )
    print("🤖 Moteur autonome démarré (boucle de scrape 24/7).")


async def stop_autonomous_engine(app):
    if "engine_stop" in app:
        app["engine_stop"].set()
    if "engine_task" in app:
        app["engine_task"].cancel()
    if "engine_session" in app:
        await app["engine_session"].close()
    if "engine_brain" in app:
        app["engine_brain"].close()
```

Modifier `create_app()` pour accepter le mode auto :

```python
# server.py  (remplacer la signature et la fin de create_app)
def create_app(auto: bool = False) -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.on_cleanup.append(on_shutdown)
    # ... (toutes les routes existantes INCHANGÉES) ...
    if auto:
        app.on_startup.append(start_autonomous_engine)
        app.on_cleanup.append(stop_autonomous_engine)
    return app
```

Modifier `main()` pour parser `--auto` :

```python
# server.py  (remplacer le début de main())
def main():
    parser = argparse.ArgumentParser(description="Serveur LBC scraper + moteur autonome")
    parser.add_argument("--auto", action="store_true", help="Démarre le moteur autonome 24/7")
    args = parser.parse_args()

    if sys.platform == 'win32':
        # ... (bloc _quiet_shutdown EXISTANT, inchangé) ...
        pass  # garder le bloc existant tel quel

    app = create_app(auto=args.auto)
    print("✨ Le serveur Leboncoin Scraper est lancé !")
    if args.auto:
        print("🤖 Mode autonome ACTIF.")
    print("👉 http://localhost:8080")
    web.run_app(app, host='localhost', port=8080)
```

> ⚠️ Lors de l'édition : conserver intégralement le bloc `_quiet_shutdown` existant dans `main()` ; ne remplacer que l'enrobage argparse + l'appel `create_app(auto=args.auto)`.

- [ ] **Step 6: Run the full test suite (vérifier qu'on n'a rien cassé)**

Run: `python -m pytest tests/ -v`
Expected: PASS (tous les tests, dont les 3 tests existants `test_server.py`)

- [ ] **Step 7: Commit**

```bash
git add server.py engine/bootstrap.py tests/test_engine_bootstrap.py
git commit -m "feat(engine): flag --auto + bootstrap moteur (browser partage + verrou)"
```

---

## Task 13: Résilience — upsert avec repli sur outbox + flush

**Files:**
- Modify: `engine/scheduler.py` (`process_search` utilise un insert sûr + flush)
- Test: `tests/test_engine_resilience.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_resilience.py
import pytest
from engine.db import Brain
from engine.scheduler import safe_insert, flush_outbox


class FlakySupa:
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.inserted = []

    async def insert_opportunity(self, payload):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("réseau down")
        self.inserted.append(payload)


async def test_safe_insert_queues_to_outbox_on_failure():
    brain = Brain(":memory:")
    supa = FlakySupa(fail_times=1)
    ok = await safe_insert(brain, supa, {"ad_id": "1"})
    assert ok is False
    assert len(brain.peek_outbox()) == 1
    assert brain.peek_outbox()[0]["payload"]["ad_id"] == "1"


async def test_flush_outbox_replays_when_back_online():
    brain = Brain(":memory:")
    supa = FlakySupa(fail_times=1)
    await safe_insert(brain, supa, {"ad_id": "1"})  # va en outbox
    # réseau revenu : flush rejoue
    sent = await flush_outbox(brain, supa)
    assert sent == 1
    assert supa.inserted[-1]["ad_id"] == "1"
    assert brain.peek_outbox() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_resilience.py -v`
Expected: FAIL with `ImportError: cannot import name 'safe_insert'`

- [ ] **Step 3: Write minimal implementation (ajouter à `engine/scheduler.py`)**

```python
# engine/scheduler.py  (ajouter en bas)
async def safe_insert(brain, supa, payload: dict) -> bool:
    """Tente l'upsert ; en cas d'échec réseau, met en file d'attente (outbox). Retourne True si envoyé."""
    try:
        await supa.insert_opportunity(payload)
        return True
    except Exception:
        brain.queue_outbox(payload)
        return False


async def flush_outbox(brain, supa) -> int:
    """Rejoue les opportunités en attente. Retourne le nombre rejoué avec succès."""
    sent = 0
    for item in brain.peek_outbox(limit=200):
        try:
            await supa.insert_opportunity(item["payload"])
            brain.delete_outbox(item["id"])
            sent += 1
        except Exception:
            break  # toujours hors ligne : on réessaiera au prochain cycle
    return sent
```

Puis remplacer dans `process_search` la ligne `await supa.insert_opportunity(payload)` par :

```python
        await safe_insert(brain, supa, payload)
```

Et ajouter un flush en début de chaque cycle dans `run_engine`, juste après `searches = dedup_searches(...)` :

```python
            await flush_outbox(brain, supa)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_resilience.py tests/test_engine_scheduler_run.py -v`
Expected: PASS (les 2 nouveaux + les 4 de la Task 9 toujours verts)

- [ ] **Step 5: Commit**

```bash
git add engine/scheduler.py tests/test_engine_resilience.py
git commit -m "feat(engine): resilience - outbox local + flush (Supabase down)"
```

---

## Task 14: Déploiement Windows (autostart)

**Files:**
- Create: `start-agent.bat`
- Create: `docs/DEPLOY-agent-windows.md`

> Pas de test automatisé (setup OS). Le `.bat` doit être exact et relancer en cas de crash.

- [ ] **Step 1: Write `start-agent.bat`**

```bat
@echo off
REM Lanceur du moteur autonome LBC. Relance automatiquement si le process meurt.
cd /d "%~dp0"
:loop
echo [%date% %time%] Demarrage du moteur autonome...
python server.py --auto
echo [%date% %time%] Le process s'est arrete (code %errorlevel%). Relance dans 10s...
timeout /t 10 /nobreak >nul
goto loop
```

- [ ] **Step 2: Write the deployment guide**

```markdown
<!-- docs/DEPLOY-agent-windows.md -->
# Déploiement du moteur autonome (Windows 11, 24/7)

## 1. Pré-requis
- Python 3.11 + dépendances : `pip install -r requirements.txt`
- Chromium Playwright : `python -m playwright install chromium`
- Fichier `.env` créé à partir de `.env.example` (avec la clé `service_role`
  copiée depuis Supabase → Project Settings → API → `service_role` secret).

## 2. Test manuel
Double-cliquer `start-agent.bat`. Une fenêtre Chromium doit s'ouvrir et le terminal
afficher « 🤖 Moteur autonome démarré ». Laisser tourner quelques minutes.

## 3. Autostart à l'ouverture de session
1. Activer l'auto-login Windows du compte habituel :
   - `Win+R` → `netplwiz` → décocher « Les utilisateurs doivent entrer un nom… »
     → entrer le mot de passe du compte.
2. Planificateur de tâches → Créer une tâche :
   - Général : « LBC Agent », cocher « Exécuter seulement si l'utilisateur est connecté ».
   - Déclencheurs : « À l'ouverture de session » (utilisateur courant).
   - Actions : Démarrer un programme → `start-agent.bat` (chemin complet),
     « Commencer dans » = dossier du projet.
   - Paramètres : cocher « Redémarrer en cas d'échec » (toutes les 1 min, 3 fois).
3. (Recommandé) Activer **BitLocker** sur le disque système.

## 4. Vérifier
Redémarrer le PC : la session s'ouvre seule, `start-agent.bat` se lance,
Chromium apparaît. En cas de captcha Datadome, résoudre dans la fenêtre Chromium.
```

- [ ] **Step 3: Commit**

```bash
git add start-agent.bat docs/DEPLOY-agent-windows.md
git commit -m "feat(deploy): lanceur Windows autostart + guide de deploiement"
```

---

## Task 15: Vérification end-to-end manuelle

**Files:** aucun (procédure de validation).

- [ ] **Step 1: Pré-vol**

```bash
python -m pytest tests/ -v
```
Expected: **tous** les tests PASS (existants + ~30 nouveaux).

- [ ] **Step 2: Vérifier que la migration + le seed sont appliqués** (Task 11 faits).

- [ ] **Step 3: Lancer le moteur**

```bash
python server.py --auto
```
Observer : fenêtre Chromium ouverte, logs de cycle, « 🤖 Moteur autonome démarré ».
(Si captcha Datadome : le résoudre dans la fenêtre Chromium.)

- [ ] **Step 4: Vérifier l'écriture dans Supabase**

Dashboard → Table Editor → `opportunities` : des lignes apparaissent avec `category = null`,
`price_dropped = false`, `ad_id` renseigné. Le `scraped_at` est récent.

- [ ] **Step 5: Vérifier la déduplication**

Laisser tourner un 2ᵉ cycle (≥1 min). Le nombre de lignes `opportunities` **ne doit pas
doubler** : seules les nouvelles annonces s'ajoutent.

- [ ] **Step 6: Vérifier la baisse de prix (simulation)**

Dans `lbc_brain.sqlite3` (DB Browser for SQLite, ou shell) forcer un prix plus haut sur une
annonce existante, puis relancer un cycle :
```sql
update seen_ads set last_price = last_price + 100 where ad_id = '<un_ad_id>';
```
Au cycle suivant, la ligne `opportunities` correspondante doit passer `price_dropped = true`
et `previous_price` rempli.

- [ ] **Step 7: Vérifier la résilience (outbox)**

Couper le Wi-Fi/Ethernet 1 min pendant que le moteur tourne, puis le rétablir.
Les opportunités détectées hors-ligne doivent finir par apparaître dans Supabase
(rejouées par le flush au cycle suivant). Vérifier que la table `outbox` se vide.

- [ ] **Step 8: Documenter le résultat** dans le commit message de la Task 16.

---

## Task 16: Mettre à jour CLAUDE.md + commit final

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Documenter l'invariant cassé + le moteur**

Dans `CLAUDE.md`, sous « Architecture clé » ou une nouvelle section « Moteur autonome (Phase A) », ajouter :

```markdown
## Moteur autonome (pipeline de revente — Phase A livrée)
- `server.py --auto` démarre une boucle de fond qui scrape les `watchlist_searches`
  actives, déduplique via SQLite local (`lbc_brain.sqlite3`), détecte les baisses de
  prix, et **écrit des opportunités brutes dans Supabase via la clé `service_role`**.
- ⚠️ **L'invariant « server.py ne touche JAMAIS Supabase » est volontairement levé**
  pour le mode `--auto` (et UNIQUEMENT lui). Le scrape manuel et le frontend restent
  inchangés (anon key + JWT + RLS).
- Package `engine/` : config, parse, db (Brain SQLite), prefilter, supa (REST), scheduler, scraper, bootstrap.
- Secrets dans `.env` (non committé). Déploiement : voir `docs/DEPLOY-agent-windows.md`.
- Spec : `docs/superpowers/specs/2026-05-29-pipeline-revente-opportunites-design.md`.
- Phases suivantes (B→F) : voir la spec.
```

- [ ] **Step 2: Run full suite une dernière fois**

```bash
python -m pytest tests/ -v
```
Expected: tout PASS.

- [ ] **Step 3: Commit final**

```bash
git add CLAUDE.md
git commit -m "docs: documenter le moteur autonome Phase A dans CLAUDE.md"
```

---

## Self-Review (effectuée)

**Couverture de la spec (sections Phase A) :**
- Démon autonome / `--auto` / browser partagé → Tasks 12.
- Write-path service_role via REST aiohttp → Tasks 6-7, 12.
- Scrape results-only → Task 10.
- Ordonnancement round-robin + pull watchlist + dédup recherches → Tasks 8-9, 12.
- Dédup ad_id + historique prix + baisse de prix → Tasks 3-4, 9.
- market_observations (byproduct) → Task 4 (l'alimentation effective par catégorie est branchée en Phase B avec la catégorisation ; la table + l'API existent dès la Phase A).
- Pré-filtre règles → Task 5.
- Résilience outbox → Tasks 4, 13.
- Modèle de données (opportunities + watchlist_searches + RLS) → Task 11.
- Autostart Windows → Task 14.
- Doc invariant cassé → Task 16.

**Hors périmètre Phase A (rappel) :** cascade IA (B), Telegram + feed + onglet Opportunités (C), Mon espace/journal/relances (D), Tendances (E), monitoring/heartbeat/purge auto (F). Conforme à la roadmap de la spec.

**Note `market_observations`** : la table et `record_market_obs` existent dès la Phase A, mais leur **alimentation** dépend de la catégorisation (Phase B). C'est volontaire — pas un trou, un branchement différé documenté ici et dans la spec.

**Placeholders :** aucun. Tout le code est complet et exécutable.

**Cohérence des types :** `ad` dict = `{ad_id,title,price,url,city,image_url}` partout ; `Brain.upsert_ad` retourne `'new'|'price_drop'|'seen'` ; `Supa.insert_opportunity(payload)` et `Supa.fetch_active_searches()` cohérents entre Tasks 7, 9, 12, 13.
