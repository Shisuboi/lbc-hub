# Phase C-3 — Watchlist (gestion + monitoring live) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformer le placeholder `/watchlist` en page qui montre en temps réel ce que le moteur scrape (état PC, annonces/min, dernière passe, cumul) et permet de gérer les recherches (ajout / activer / pause / éditer / supprimer).

**Architecture:** Le moteur `--auto` publie une télémétrie légère dans une nouvelle table Supabase `scrape_heartbeats` (clé `search_id`, écrite via `service_role`, lue en realtime). Une 3ᵉ coroutine `heartbeat_worker` calcule les stats depuis le Brain SQLite local et upsert toutes les ~15 s. Le front lit/abonne cette table + gère les recherches via RPC `set_active_watchlist`.

**Tech Stack:** Python 3.12 (aiohttp, sqlite3, pytest avec `asyncio_mode=auto`), Vanilla JS ES6 + Supabase JS SDK v2, PostgreSQL/Supabase (RLS + Realtime).

**Spec:** `docs/superpowers/specs/2026-06-02-phase-c3-watchlist-monitoring-design.md`

**Convention projet importante :** pytest couvre **uniquement** le backend (`engine/`, `server.py`). **Aucun test frontend automatisé** — la validation JS se fait par chargement de page + console F12 (Node n'est pas installé ; le site se sert via `python server.py`). Les tâches frontend (7-9) n'ont donc pas d'étape pytest, mais une étape de vérification manuelle explicite.

---

## File Structure

| Fichier | Création / Modif | Responsabilité |
|---|---|---|
| `supabase/migrations/2026-06-02-phase-c3-watchlist.sql` | Create | Table `scrape_heartbeats` + RLS + realtime + RPC `set_active_watchlist` + override admin |
| `engine/db.py` | Modify | Colonne `scrape_log.new_ads` + migration + `log_scrape(new_ads)` + lectures stats |
| `engine/scheduler.py` | Modify (`process_search`, ~ligne 69) | Faire remonter le nb d'annonces neuves dans `log_scrape` |
| `engine/supa.py` | Modify | Méthode `upsert_heartbeat` |
| `engine/telemetry.py` | Create | `build_heartbeat_payload` (pur) + coroutine `heartbeat_worker` |
| `server.py` | Modify (`start_autonomous_engine`, ~ligne 567-591) | Lancer `heartbeat_worker` comme 3ᵉ tâche |
| `tests/test_engine_db_heartbeat.py` | Create | Tests des lectures stats + `log_scrape(new_ads)` |
| `tests/test_engine_scheduler_newads.py` | Create | Test : `process_search` logge le bon `new_ads` |
| `tests/test_engine_supa_heartbeat.py` | Create | Test : `upsert_heartbeat` poste sur la bonne table |
| `tests/test_engine_telemetry.py` | Create | Tests `build_heartbeat_payload` + `heartbeat_worker` |
| `js/lib/watchlist.js` | Create | Accès données : list/create/update/delete/setActive/pause + heartbeats realtime |
| `js/pages/watchlist.js` | Replace placeholder | Page : panneau live + gestion + formulaire d'ajout |
| `style.css` | Modify (append) | Styles panneau live + lignes de gestion (tokens DA existants) |

---

## Task 1 : Migration Supabase (table + RLS + realtime + RPC + admin)

**Files:**
- Create: `supabase/migrations/2026-06-02-phase-c3-watchlist.sql`

Pas de test automatisé (SQL appliqué à la main, convention projet). Vérification = application dans le SQL Editor + requête de contrôle.

- [ ] **Step 1: Écrire le fichier de migration**

```sql
-- Phase C-3 : télémétrie watchlist (scrape_heartbeats) + RPC "une seule active" + override admin.
-- À appliquer À LA MAIN dans Supabase > SQL Editor (convention projet).

-- 1) Table de télémétrie (volatile). Écrite UNIQUEMENT par le moteur via service_role.
create table if not exists public.scrape_heartbeats (
  search_id        uuid primary key references public.watchlist_searches(id) on delete cascade,
  heartbeat_at     timestamptz not null,
  last_pass_at     timestamptz,
  new_ads_per_min  float default 0,
  ads_seen_total   int   default 0,
  blocked_recent   int   default 0,
  updated_at       timestamptz not null default now()
);

alter table public.scrape_heartbeats enable row level security;

-- Lecture pour tous les membres authentifiés. AUCUNE policy d'écriture → seul service_role écrit.
drop policy if exists "heartbeats_select_authenticated" on public.scrape_heartbeats;
create policy "heartbeats_select_authenticated"
  on public.scrape_heartbeats for select
  to authenticated using (true);

-- Realtime : ⚠️ si "is already member of publication", ignorer l'erreur (déjà ajoutée).
alter publication supabase_realtime add table public.scrape_heartbeats;

-- 2) RPC : une seule recherche active à la fois (atomique).
create or replace function public.set_active_watchlist(p_search_id uuid)
returns void language plpgsql security definer as $$
begin
  update public.watchlist_searches set active = false where active;
  update public.watchlist_searches set active = true  where id = p_search_id;
end; $$;

-- 3) Override admin sur update/delete de watchlist_searches (en plus des policies own existantes).
drop policy if exists "watchlist_update_admin" on public.watchlist_searches;
create policy "watchlist_update_admin"
  on public.watchlist_searches for update to authenticated
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));

drop policy if exists "watchlist_delete_admin" on public.watchlist_searches;
create policy "watchlist_delete_admin"
  on public.watchlist_searches for delete to authenticated
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));
```

- [ ] **Step 2: Commit**

```bash
git add supabase/migrations/2026-06-02-phase-c3-watchlist.sql
git commit -m "feat(db): migration Phase C-3 (scrape_heartbeats + RPC active + override admin)"
```

> ⚠️ RAPPEL à donner à Tristan au moment du test : appliquer ce SQL à la main dans Supabase, et vérifier que `scrape_heartbeats` est dans la publication `supabase_realtime` :
> ```sql
> select * from pg_publication_tables where pubname='supabase_realtime' and tablename='scrape_heartbeats';
> ```

---

## Task 2 : Brain — colonne `new_ads`, migration, lectures de stats

**Files:**
- Modify: `engine/db.py` (SCHEMA ~ligne 31-36, `__init__` ~ligne 77-81, `log_scrape` ~ligne 140-146 ; ajout de méthodes)
- Test: `tests/test_engine_db_heartbeat.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Create `tests/test_engine_db_heartbeat.py`:

```python
from engine.db import Brain


def make_brain():
    return Brain(":memory:")


def test_log_scrape_stores_new_ads():
    b = make_brain()
    b.log_scrape("s1", "ok", blocked=2, new_ads=5, now=1000)
    row = b.conn.execute("select new_ads, blocked_count from scrape_log").fetchone()
    assert row["new_ads"] == 5
    assert row["blocked_count"] == 2


def test_log_scrape_new_ads_defaults_zero():
    b = make_brain()
    b.log_scrape("s1", "ok", now=1000)
    row = b.conn.execute("select new_ads from scrape_log").fetchone()
    assert row["new_ads"] == 0


def test_ads_seen_total_sums_new_ads_for_search():
    b = make_brain()
    b.log_scrape("s1", "ok", new_ads=3, now=1000)
    b.log_scrape("s1", "ok", new_ads=4, now=2000)
    b.log_scrape("s2", "ok", new_ads=9, now=2000)  # autre recherche, ignorée
    assert b.ads_seen_total("s1") == 7
    assert b.ads_seen_total("inconnue") == 0


def test_new_ads_rate_per_minute_over_window():
    b = make_brain()
    now = 10_000
    # fenêtre 600s = 10 min. 20 annonces neuves dans la fenêtre -> 2.0 / min.
    b.log_scrape("s1", "ok", new_ads=12, now=now - 100)
    b.log_scrape("s1", "ok", new_ads=8,  now=now - 200)
    b.log_scrape("s1", "ok", new_ads=99, now=now - 5000)  # hors fenêtre, ignorée
    assert b.new_ads_rate("s1", window_s=600, now=now) == 2.0


def test_last_pass_at_returns_latest():
    b = make_brain()
    b.log_scrape("s1", "ok", now=1000)
    b.log_scrape("s1", "ok", now=3000)
    assert b.last_pass_at("s1") == 3000
    assert b.last_pass_at("inconnue") is None


def test_blocked_recent_sums_within_window():
    b = make_brain()
    now = 10_000
    b.log_scrape("s1", "error", blocked=1, now=now - 100)
    b.log_scrape("s1", "error", blocked=2, now=now - 200)
    b.log_scrape("s1", "error", blocked=5, now=now - 5000)  # hors fenêtre
    assert b.blocked_recent("s1", window_s=600, now=now) == 3
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_engine_db_heartbeat.py -v`
Expected: FAIL (`log_scrape() got an unexpected keyword argument 'new_ads'` / `AttributeError: 'Brain' object has no attribute 'ads_seen_total'`).

- [ ] **Step 3: Ajouter la colonne au SCHEMA**

Dans `engine/db.py`, remplacer le bloc `scrape_log` du SCHEMA :

```python
CREATE TABLE IF NOT EXISTS scrape_log (
    search_id TEXT,
    last_run_at INTEGER NOT NULL,
    status TEXT,
    blocked_count INTEGER DEFAULT 0,
    new_ads INTEGER DEFAULT 0
);
```

- [ ] **Step 4: Ajouter la migration idempotente pour les bases existantes**

Dans `engine/db.py`, modifier `__init__` et ajouter `_migrate` :

```python
    def __init__(self, path: str = "lbc_brain.sqlite3"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Migrations légères des bases déjà créées (CREATE TABLE IF NOT EXISTS ne les altère pas)."""
        cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(scrape_log)").fetchall()]
        if "new_ads" not in cols:
            self.conn.execute("ALTER TABLE scrape_log ADD COLUMN new_ads INTEGER DEFAULT 0")
```

- [ ] **Step 5: Étendre `log_scrape` et ajouter les lectures**

Dans `engine/db.py`, remplacer `log_scrape` et ajouter les 4 méthodes juste après :

```python
    def log_scrape(self, search_id: str, status: str, blocked: int = 0,
                   new_ads: int = 0, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO scrape_log (search_id, last_run_at, status, blocked_count, new_ads) "
            "VALUES (?, ?, ?, ?, ?)",
            (search_id, now, status, blocked, new_ads),
        )
        self.conn.commit()

    def new_ads_rate(self, search_id: str, window_s: int = 600, now: int | None = None) -> float:
        """Annonces neuves par minute sur la fenêtre glissante (moyenne)."""
        now = int(now if now is not None else time.time())
        row = self.conn.execute(
            "SELECT COALESCE(SUM(new_ads), 0) AS s FROM scrape_log "
            "WHERE search_id = ? AND last_run_at >= ?",
            (search_id, now - window_s),
        ).fetchone()
        minutes = window_s / 60.0
        return (float(row["s"] or 0) / minutes) if minutes else 0.0

    def ads_seen_total(self, search_id: str) -> int:
        """Cumul d'annonces uniques que cette recherche a fait remonter (somme des new_ads)."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(new_ads), 0) AS s FROM scrape_log WHERE search_id = ?",
            (search_id,),
        ).fetchone()
        return int(row["s"] or 0)

    def last_pass_at(self, search_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT MAX(last_run_at) AS m FROM scrape_log WHERE search_id = ?",
            (search_id,),
        ).fetchone()
        return row["m"] if row and row["m"] is not None else None

    def blocked_recent(self, search_id: str, window_s: int = 600, now: int | None = None) -> int:
        now = int(now if now is not None else time.time())
        row = self.conn.execute(
            "SELECT COALESCE(SUM(blocked_count), 0) AS s FROM scrape_log "
            "WHERE search_id = ? AND last_run_at >= ?",
            (search_id, now - window_s),
        ).fetchone()
        return int(row["s"] or 0)
```

- [ ] **Step 6: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_engine_db_heartbeat.py tests/test_engine_db.py -v`
Expected: PASS (les nouveaux + les anciens tests db, non-régression).

- [ ] **Step 7: Commit**

```bash
git add engine/db.py tests/test_engine_db_heartbeat.py
git commit -m "feat(engine): scrape_log.new_ads + lectures stats (rate/total/last/blocked)"
```

---

## Task 3 : Scheduler — remonter le nb d'annonces neuves

**Files:**
- Modify: `engine/scheduler.py` (`process_search`, ligne 69)
- Test: `tests/test_engine_scheduler_newads.py`

- [ ] **Step 1: Écrire le test qui échoue**

Create `tests/test_engine_scheduler_newads.py`:

```python
from engine.db import Brain
from engine.scheduler import process_search


class FakeSink:
    def __init__(self):
        self.inserted = []
    async def insert_opportunity(self, payload):
        self.inserted.append(payload)


async def test_process_search_logs_new_ads_count():
    brain = Brain(":memory:")
    sink = FakeSink()
    search = {"id": "s1", "source_url": "https://lbc/u1", "platform": "leboncoin"}

    async def scrape_fn(url):
        return [
            {"ad_id": "a1", "title": "Vélo", "price": 100.0, "url": "u1", "city": None, "image_url": None},
            {"ad_id": "a2", "title": "Console", "price": 200.0, "url": "u2", "city": None, "image_url": None},
        ]

    counts = await process_search(scrape_fn, brain, sink, search)
    assert counts["new"] == 2
    row = brain.conn.execute("select new_ads, status from scrape_log").fetchone()
    assert row["status"] == "ok"
    assert row["new_ads"] == 2
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_engine_scheduler_newads.py -v`
Expected: FAIL (`assert row["new_ads"] == 2` échoue, vaut 0 — le scheduler ne logge pas encore new_ads).

- [ ] **Step 3: Modifier `process_search`**

Dans `engine/scheduler.py`, remplacer la ligne 69 :

```python
    brain.log_scrape(search.get("id", "?"), "ok")
```

par :

```python
    brain.log_scrape(search.get("id", "?"), "ok", new_ads=counts["new"])
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_engine_scheduler_newads.py tests/test_engine_scheduler_run.py tests/test_engine_scheduler_dedup.py -v`
Expected: PASS (nouveau + non-régression scheduler).

- [ ] **Step 5: Commit**

```bash
git add engine/scheduler.py tests/test_engine_scheduler_newads.py
git commit -m "feat(engine): process_search logge le nb d'annonces neuves par passe"
```

---

## Task 4 : Supa — `upsert_heartbeat`

**Files:**
- Modify: `engine/supa.py` (ajout méthode dans la classe `Supa`, après `insert_opportunity`)
- Test: `tests/test_engine_supa_heartbeat.py`

- [ ] **Step 1: Écrire le test qui échoue**

Create `tests/test_engine_supa_heartbeat.py`:

```python
import pytest
from aiohttp import web, ClientSession
from engine.supa import Supa


@pytest.fixture
async def mock_supabase(aiohttp_server):
    captured = {"posts": [], "headers": [], "query": []}

    async def post_heartbeat(request):
        captured["posts"].append(await request.json())
        captured["headers"].append(dict(request.headers))
        captured["query"].append(dict(request.query))
        return web.json_response({}, status=201)

    app = web.Application()
    app.router.add_post("/rest/v1/scrape_heartbeats", post_heartbeat)
    server = await aiohttp_server(app)
    server.captured = captured
    return server


async def test_upsert_heartbeat_posts_to_table(mock_supabase):
    base = str(mock_supabase.make_url("")).rstrip("/")
    async with ClientSession() as session:
        supa = Supa(base, "service-key", session)
        await supa.upsert_heartbeat({"search_id": "s1", "new_ads_per_min": 2.0})
    assert mock_supabase.captured["posts"][-1]["search_id"] == "s1"
    assert mock_supabase.captured["query"][-1].get("on_conflict") == "search_id"
    hdr = mock_supabase.captured["headers"][-1]
    assert hdr.get("Prefer") == "resolution=merge-duplicates,return=minimal"
    assert hdr.get("apikey") == "service-key"
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_engine_supa_heartbeat.py -v`
Expected: FAIL (`AttributeError: 'Supa' object has no attribute 'upsert_heartbeat'`).

- [ ] **Step 3: Ajouter la méthode**

Dans `engine/supa.py`, ajouter à la fin de la classe `Supa` (après `insert_opportunity`) :

```python
    async def upsert_heartbeat(self, payload: dict) -> None:
        """Upsert de la télémétrie de scrape (clé search_id). Appelée en best-effort."""
        url = f"{self.base}/rest/v1/scrape_heartbeats"
        params = {"on_conflict": "search_id"}
        headers = self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"})
        async with self.session.post(url, params=params, json=payload, headers=headers) as resp:
            resp.raise_for_status()
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_engine_supa_heartbeat.py tests/test_engine_supa_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/supa.py tests/test_engine_supa_heartbeat.py
git commit -m "feat(engine): Supa.upsert_heartbeat (télémétrie scrape_heartbeats)"
```

---

## Task 5 : Module télémétrie — payload + worker

**Files:**
- Create: `engine/telemetry.py`
- Test: `tests/test_engine_telemetry.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Create `tests/test_engine_telemetry.py`:

```python
import asyncio
from datetime import datetime, timezone
from engine.db import Brain
from engine.telemetry import build_heartbeat_payload, heartbeat_worker


def test_build_heartbeat_payload_fields():
    b = Brain(":memory:")
    now = 10_000
    b.log_scrape("s1", "ok", blocked=1, new_ads=10, now=now - 60)
    b.log_scrape("s1", "ok", blocked=0, new_ads=10, now=now - 120)
    payload = build_heartbeat_payload(b, "s1", now=now)

    assert payload["search_id"] == "s1"
    assert payload["ads_seen_total"] == 20
    assert payload["new_ads_per_min"] == 2.0          # 20 sur fenêtre 10 min
    assert payload["blocked_recent"] == 1
    # heartbeat_at / last_pass_at sérialisés en ISO UTC
    assert payload["heartbeat_at"] == datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    assert payload["last_pass_at"] == datetime.fromtimestamp(now - 60, tz=timezone.utc).isoformat()


def test_build_heartbeat_payload_no_passes_yet():
    b = Brain(":memory:")
    payload = build_heartbeat_payload(b, "s1", now=10_000)
    assert payload["ads_seen_total"] == 0
    assert payload["new_ads_per_min"] == 0
    assert payload["last_pass_at"] is None


class FakeSupa:
    def __init__(self, searches):
        self._searches = searches
        self.upserts = []
    async def fetch_active_searches(self):
        return self._searches
    async def upsert_heartbeat(self, payload):
        self.upserts.append(payload)


async def test_heartbeat_worker_upserts_active_search():
    b = Brain(":memory:")
    b.log_scrape("s1", "ok", new_ads=4, now=10_000)
    supa = FakeSupa([{"id": "s1"}])
    stop = asyncio.Event()
    await heartbeat_worker(b, supa, stop, interval=0, max_loops=1)
    assert len(supa.upserts) == 1
    assert supa.upserts[0]["search_id"] == "s1"


async def test_heartbeat_worker_swallows_upsert_errors():
    """Un échec d'upsert (Supabase down) ne doit pas faire remonter d'exception."""
    b = Brain(":memory:")
    class BoomSupa(FakeSupa):
        async def upsert_heartbeat(self, payload):
            raise RuntimeError("supabase down")
    supa = BoomSupa([{"id": "s1"}])
    stop = asyncio.Event()
    # ne doit PAS lever
    await heartbeat_worker(b, supa, stop, interval=0, max_loops=1)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_engine_telemetry.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'engine.telemetry'`).

- [ ] **Step 3: Écrire `engine/telemetry.py`**

```python
"""Télémétrie du moteur : publie un heartbeat de la recherche active dans Supabase.

Best-effort : ne doit JAMAIS faire planter le scraping. Lit les stats du Brain local
et les pousse dans `scrape_heartbeats` (lue en temps réel par la page /watchlist).
"""
import asyncio
import time
from datetime import datetime, timezone


def _iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def build_heartbeat_payload(brain, search_id: str, now: int | None = None) -> dict:
    """Construit la ligne `scrape_heartbeats` pour une recherche, à partir du Brain local."""
    now = int(now if now is not None else time.time())
    return {
        "search_id": search_id,
        "heartbeat_at": _iso(now),
        "last_pass_at": _iso(brain.last_pass_at(search_id)),
        "new_ads_per_min": round(brain.new_ads_rate(search_id, now=now), 2),
        "ads_seen_total": brain.ads_seen_total(search_id),
        "blocked_recent": brain.blocked_recent(search_id, now=now),
    }


async def heartbeat_worker(brain, supa, stop_event, interval: float = 15.0, max_loops=None) -> None:
    """Tick périodique : pour chaque recherche active, upsert sa télémétrie. Best-effort.

    `supa` doit exposer `fetch_active_searches()` et `upsert_heartbeat(payload)`.
    `max_loops` (tests) limite le nombre de tours ; None = infini.
    """
    loops = 0
    while not stop_event.is_set():
        try:
            searches = await supa.fetch_active_searches()
            now = int(time.time())
            for s in searches:
                sid = s.get("id")
                if not sid:
                    continue
                payload = build_heartbeat_payload(brain, sid, now)
                try:
                    await supa.upsert_heartbeat(payload)
                except Exception as exc:
                    print(f"[heartbeat] upsert échoué ({type(exc).__name__}) — best-effort, on continue")
        except Exception as exc:
            print(f"[heartbeat] erreur cycle: {type(exc).__name__}: {exc}")
        loops += 1
        if max_loops is not None and loops >= max_loops:
            return
        if interval:
            await asyncio.sleep(interval)
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_engine_telemetry.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/telemetry.py tests/test_engine_telemetry.py
git commit -m "feat(engine): module telemetry (build_heartbeat_payload + heartbeat_worker)"
```

---

## Task 6 : server.py — lancer le heartbeat sous `--auto`

**Files:**
- Modify: `server.py` (import ~ligne 19-22 ; `start_autonomous_engine` ~ligne 567-591)

Pas de nouveau test unitaire (câblage de coroutine ; couvert par `test_server.py` qui vérifie que l'app se construit). Vérification = `test_server.py` passe + démarrage manuel `--auto`.

- [ ] **Step 1: Ajouter l'import**

Dans `server.py`, après la ligne `from engine.scheduler import run_engine` (ligne 20), ajouter :

```python
from engine.telemetry import heartbeat_worker
```

- [ ] **Step 2: Lancer la coroutine heartbeat (indépendante de l'IA)**

Dans `server.py`, dans `start_autonomous_engine`, juste **avant** la ligne `app["engine_tasks"] = tasks` (ligne 591), ajouter :

```python
    # Heartbeat de télémétrie : tourne TOUJOURS sous --auto (indépendant de la clé IA).
    tasks.append(asyncio.create_task(heartbeat_worker(brain, supa, stop_event)))
    print("📡 Heartbeat de télémétrie démarré (scrape_heartbeats).")
```

- [ ] **Step 3: Vérifier que l'app se construit toujours**

Run: `python -m pytest tests/test_server.py -v`
Expected: PASS (non-régression du câblage serveur).

- [ ] **Step 4: Vérifier la suite complète backend**

Run: `python -m pytest tests/ -v`
Expected: PASS (toute la suite, aucune régression).

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat(server): lance heartbeat_worker comme 3e tache sous --auto"
```

---

## Task 7 : Frontend — lib d'accès `js/lib/watchlist.js`

**Files:**
- Create: `js/lib/watchlist.js`

Pas de test auto (convention). Vérification à la Task 8 (chargement de page).

- [ ] **Step 1: Écrire la lib**

Create `js/lib/watchlist.js`:

```javascript
// js/lib/watchlist.js
// Accès aux recherches surveillées (watchlist_searches) + télémétrie (scrape_heartbeats).
// "Une seule active à la fois" passe par la RPC set_active_watchlist (atomique).
import { supa } from '../supabase-client.js';

const SELECT = 'id, owner_id, title, source_url, platform, price_max, exclude_keywords, ' +
  'min_margin_eur, min_margin_pct, active, created_at, author:profiles(username, avatar_color)';

/** Déduit la plateforme depuis l'URL (badge + colonne platform). */
export function deducePlatform(url) {
  const u = (url || '').toLowerCase();
  if (u.includes('leboncoin.')) return 'leboncoin';
  if (u.includes('ebay.')) return 'ebay';
  if (u.includes('vinted.')) return 'vinted';
  return 'other';
}

/** Toutes les recherches surveillées, plus récente d'abord. */
export async function listSearches() {
  const { data, error } = await supa
    .from('watchlist_searches')
    .select(SELECT)
    .order('created_at', { ascending: false });
  if (error) throw new Error('Chargement des recherches impossible : ' + error.message);
  return data || [];
}

/** Crée une recherche (owner_id = moi). */
export async function createSearch(ownerId, { title, source_url, price_max, exclude_keywords }) {
  const t = (title || '').trim();
  const url = (source_url || '').trim();
  if (!t) throw new Error('Titre requis.');
  if (!url) throw new Error('URL de recherche requise.');
  const row = {
    owner_id: ownerId,
    title: t,
    source_url: url,
    platform: deducePlatform(url),
    price_max: price_max != null && price_max !== '' ? Number(price_max) : null,
    exclude_keywords: (exclude_keywords || '').trim(),
    active: false, // on n'active jamais à la création (l'utilisateur clique "Activer")
  };
  const { data, error } = await supa
    .from('watchlist_searches').insert(row).select(SELECT).single();
  if (error) throw new Error('Création impossible : ' + error.message);
  return data;
}

/** Édite une recherche (sienne, ou n'importe laquelle si admin via RLS). */
export async function updateSearch(id, fields) {
  const patch = {};
  if (fields.title != null) patch.title = String(fields.title).trim();
  if (fields.source_url != null) {
    patch.source_url = String(fields.source_url).trim();
    patch.platform = deducePlatform(patch.source_url);
  }
  if (fields.price_max !== undefined)
    patch.price_max = fields.price_max === '' || fields.price_max == null ? null : Number(fields.price_max);
  if (fields.exclude_keywords != null) patch.exclude_keywords = String(fields.exclude_keywords).trim();
  const { data, error } = await supa
    .from('watchlist_searches').update(patch).eq('id', id).select(SELECT).single();
  if (error) throw new Error('Modification impossible : ' + error.message);
  return data;
}

/** Supprime une recherche (sienne, ou n'importe laquelle si admin). */
export async function deleteSearch(id) {
  const { error } = await supa.from('watchlist_searches').delete().eq('id', id);
  if (error) throw new Error('Suppression impossible : ' + error.message);
}

/** Active CETTE recherche et met toutes les autres en pause (RPC atomique). */
export async function setActive(searchId) {
  const { error } = await supa.rpc('set_active_watchlist', { p_search_id: searchId });
  if (error) throw new Error('Activation impossible : ' + error.message);
}

/** Met une recherche en pause (active=false sur la sienne via RLS update-own). */
export async function pauseSearch(id) {
  const { error } = await supa.from('watchlist_searches').update({ active: false }).eq('id', id);
  if (error) throw new Error('Mise en pause impossible : ' + error.message);
}

/** Télémétrie : Map<search_id, heartbeat-row>. */
export async function getHeartbeats() {
  const map = new Map();
  const { data, error } = await supa.from('scrape_heartbeats').select('*');
  if (error || !data) return map; // best-effort : on n'empêche pas la gestion
  for (const row of data) map.set(row.search_id, row);
  return map;
}

/** Abonnement realtime à scrape_heartbeats. onChange() sur tout INSERT/UPDATE/DELETE.
 * Renvoie le canal (à passer à supa.removeChannel au démontage). */
export function subscribeHeartbeats(onChange) {
  return supa
    .channel('scrape-heartbeats')
    .on('postgres_changes',
      { event: '*', schema: 'public', table: 'scrape_heartbeats' },
      () => onChange())
    .subscribe();
}
```

- [ ] **Step 2: Commit**

```bash
git add js/lib/watchlist.js
git commit -m "feat(watchlist): lib acces recherches + telemetrie realtime (phase C-3)"
```

---

## Task 8 : Frontend — page `js/pages/watchlist.js`

**Files:**
- Replace: `js/pages/watchlist.js` (placeholder → page complète)

Pas de test auto (convention). Vérification = chargement de page + console F12.

- [ ] **Step 1: Remplacer le placeholder par la page complète**

Replace `js/pages/watchlist.js`:

```javascript
// js/pages/watchlist.js
// Page /watchlist : panneau LIVE (ce que le PC scrape : état, annonces/min, dernière passe, cumul)
// + gestion des recherches (ajout / activer (1 seule) / pause / éditer / supprimer).
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import { supa } from '../supabase-client.js';
import {
  listSearches, createSearch, updateSearch, deleteSearch,
  setActive, pauseSearch, getHeartbeats, subscribeHeartbeats,
} from '../lib/watchlist.js';

const ONLINE_THRESHOLD_S = 45; // au-delà → PC considéré hors ligne
const PLATFORM_BADGE = { leboncoin: '🟠', ebay: '🔵', vinted: '🟢', other: '⚪' };

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function ago(seconds) {
  if (seconds < 60) return `il y a ${Math.max(0, Math.round(seconds))} s`;
  if (seconds < 3600) return `il y a ${Math.round(seconds / 60)} min`;
  return `il y a ${Math.round(seconds / 3600)} h`;
}

export async function render() {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;
  const me = await getProfile();
  if (navState.token !== myToken) return;

  const root = document.getElementById('appRoot');
  root.innerHTML = `
    <section class="feed-page">
      <h2>📡 Recherches surveillées</h2>
      <p class="muted">Ce que le PC scrape en continu (une seule recherche active à la fois).</p>
      <div id="wlLive"></div>
      <div id="wlAdd"></div>
      <div id="wlList"><div class="page-loading">⏳ Chargement…</div></div>
    </section>`;

  let searches = [];
  let beats = new Map();

  async function reload() {
    [searches, beats] = await Promise.all([listSearches(), getHeartbeats()]);
    if (navState.token !== myToken) return;
    paintLive();
    paintList();
  }

  // ---- Panneau LIVE (recherche active) ----
  function paintLive() {
    const el = document.getElementById('wlLive');
    if (!el) return;
    const active = searches.find(s => s.active);
    if (!active) {
      el.innerHTML = `<div class="wl-live card wl-live-idle">😴 Aucune recherche active. Active-en une ci-dessous pour lancer le PC.</div>`;
      return;
    }
    const hb = beats.get(active.id);
    const lastBeat = hb && hb.heartbeat_at ? new Date(hb.heartbeat_at).getTime() : null;
    const elapsed = lastBeat != null ? (Date.now() - lastBeat) / 1000 : Infinity;
    const online = elapsed <= ONLINE_THRESHOLD_S;
    const stateHtml = online
      ? `<span class="wl-dot wl-on"></span> PC actif (${ago(elapsed)})`
      : `<span class="wl-dot wl-off"></span> PC hors ligne${lastBeat != null ? ` (${ago(elapsed)})` : ''}`;
    const rate = hb && hb.new_ads_per_min != null ? hb.new_ads_per_min : 0;
    const lastPass = hb && hb.last_pass_at ? ago((Date.now() - new Date(hb.last_pass_at).getTime()) / 1000) : '—';
    const seen = hb && hb.ads_seen_total != null ? hb.ads_seen_total : 0;
    const blocked = hb && hb.blocked_recent != null ? hb.blocked_recent : 0;
    el.innerHTML = `
      <div class="wl-live card">
        <div class="wl-live-head">
          <div class="wl-live-title">${PLATFORM_BADGE[active.platform] || '⚪'} ${esc(active.title)}</div>
          <div class="wl-state ${online ? 'on' : 'off'}">${stateHtml}</div>
        </div>
        <div class="wl-live-by">par @${esc(active.author?.username || '?')}
          ${active.source_url ? `· <a href="${esc(active.source_url)}" target="_blank" rel="noopener noreferrer">voir la recherche ↗</a>` : ''}</div>
        <div class="wl-metrics">
          <div class="wl-metric"><div class="wl-mval">${rate}</div><div class="wl-mlabel">annonces / min</div></div>
          <div class="wl-metric"><div class="wl-mval">${lastPass}</div><div class="wl-mlabel">dernière passe</div></div>
          <div class="wl-metric"><div class="wl-mval">${seen}</div><div class="wl-mlabel">annonces vues</div></div>
          <div class="wl-metric"><div class="wl-mval">${blocked}</div><div class="wl-mlabel">blocages récents</div></div>
        </div>
      </div>`;
  }

  // ---- Liste de gestion ----
  function paintList() {
    const el = document.getElementById('wlList');
    if (!el) return;
    if (!searches.length) {
      el.innerHTML = `<div class="card" style="padding:18px;text-align:center;color:var(--c-mut)">Aucune recherche pour l'instant. Ajoute-en une ci-dessus.</div>`;
      return;
    }
    el.innerHTML = `<div class="wl-rows">${searches.map(s => {
      const mine = s.owner_id === me.id;
      const canEdit = mine || me.role === 'admin';
      return `<div class="wl-row card" data-id="${s.id}">
        <div class="wl-row-main">
          <div class="wl-row-title">${PLATFORM_BADGE[s.platform] || '⚪'} ${esc(s.title)}
            ${s.active ? '<span class="wl-tag wl-tag-on">✅ en cours</span>' : '<span class="wl-tag wl-tag-off">⏸️ en pause</span>'}</div>
          <div class="wl-row-by muted">par @${esc(s.author?.username || '?')}</div>
        </div>
        <div class="wl-row-actions">
          ${s.active
            ? `<button class="btn-mini" data-act="pause" data-id="${s.id}">Mettre en pause</button>`
            : `<button class="btn-mini btn-mini-go" data-act="activate" data-id="${s.id}">Activer</button>`}
          ${canEdit ? `<button class="btn-mini" data-act="edit" data-id="${s.id}">Éditer</button>
                       <button class="btn-mini btn-mini-del" data-act="delete" data-id="${s.id}">Supprimer</button>` : ''}
        </div>
      </div>`;
    }).join('')}</div>`;
  }

  // ---- Formulaire d'ajout ----
  function paintAdd() {
    const el = document.getElementById('wlAdd');
    if (!el) return;
    el.innerHTML = `
      <form id="wlForm" class="wl-add card">
        <div class="wl-add-title">➕ Ajouter une recherche</div>
        <input name="title" placeholder="Titre (ex. PS5 d'occasion)" required>
        <input name="source_url" placeholder="URL de recherche Leboncoin" required>
        <div class="wl-add-row">
          <input name="price_max" type="number" min="0" placeholder="Prix max (€, optionnel)">
          <input name="exclude_keywords" placeholder="Mots exclus, séparés par des virgules (optionnel)">
        </div>
        <div class="wl-add-foot">
          <button type="submit" class="btn-primary">Ajouter</button>
          <span id="wlAddMsg" class="muted"></span>
        </div>
      </form>`;
    document.getElementById('wlForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = e.target;
      const msg = document.getElementById('wlAddMsg');
      msg.textContent = '⏳ Ajout…';
      try {
        await createSearch(me.id, {
          title: f.title.value, source_url: f.source_url.value,
          price_max: f.price_max.value, exclude_keywords: f.exclude_keywords.value,
        });
        f.reset();
        msg.textContent = '✅ Ajoutée.';
        await reload();
      } catch (err) {
        msg.textContent = '❌ ' + err.message;
      }
    });
  }

  // ---- Actions de la liste (délégation) ----
  document.getElementById('wlList').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const id = btn.dataset.id;
    const act = btn.dataset.act;
    btn.disabled = true;
    try {
      if (act === 'activate') await setActive(id);
      else if (act === 'pause') await pauseSearch(id);
      else if (act === 'delete') {
        if (!confirm('Supprimer cette recherche ?')) { btn.disabled = false; return; }
        await deleteSearch(id);
      } else if (act === 'edit') {
        const s = searches.find(x => x.id === id);
        const title = prompt('Titre :', s.title);
        if (title === null) { btn.disabled = false; return; }
        const url = prompt('URL de recherche :', s.source_url);
        if (url === null) { btn.disabled = false; return; }
        await updateSearch(id, { title, source_url: url });
      }
      await reload();
    } catch (err) {
      alert(err.message);
      btn.disabled = false;
    }
  });

  paintAdd();
  await reload();
  if (navState.token !== myToken) return;

  // ---- Temps réel + timer de fraîcheur (auto-nettoyés à la navigation) ----
  const channel = subscribeHeartbeats(async () => {
    if (navState.token !== myToken) return;
    beats = await getHeartbeats();
    if (navState.token === myToken) paintLive();
  });
  const timer = setInterval(() => {
    if (navState.token !== myToken) {        // on a quitté la page : on nettoie
      clearInterval(timer);
      try { supa.removeChannel(channel); } catch (_) {}
      return;
    }
    paintLive(); // recalcule "il y a X s" et bascule online→offline tout seul
  }, 5000);
}
```

- [ ] **Step 2: Démarrer le serveur et vérifier le chargement**

Run: `python server.py` (dans un terminal séparé), puis ouvrir `http://localhost:8080/watchlist` après login.
Expected: la page s'affiche (panneau live « aucune recherche active » si rien d'actif, formulaire d'ajout, liste). **Console F12 sans erreur rouge.**

- [ ] **Step 3: Commit**

```bash
git add js/pages/watchlist.js
git commit -m "feat(watchlist): page gestion + panneau live temps reel (phase C-3)"
```

---

## Task 9 : Styles `/watchlist`

**Files:**
- Modify: `style.css` (append d'un bloc, dans la continuité des tokens DA existants)

- [ ] **Step 1: Ajouter le bloc de styles**

Append à la fin de `style.css`:

```css
/* ===== Phase C-3 : Watchlist (panneau live + gestion) ===== */
.wl-live { padding: 18px 20px; margin: 14px 0 22px; }
.wl-live-idle { text-align: center; color: var(--c-mut); }
.wl-live-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.wl-live-title { font-weight: 700; font-size: 1.1rem; }
.wl-live-by { color: var(--c-mut); font-size: .85rem; margin-top: 2px; }
.wl-live-by a { color: var(--c-accent, #8b7cf6); }
.wl-state { display: inline-flex; align-items: center; gap: 7px; font-size: .9rem; font-weight: 600; }
.wl-state.on { color: #4ade80; }
.wl-state.off { color: #9ca3af; }
.wl-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.wl-dot.wl-on { background: #4ade80; box-shadow: 0 0 8px #4ade80; animation: wlpulse 1.6s infinite; }
.wl-dot.wl-off { background: #6b7280; }
@keyframes wlpulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
.wl-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px; }
.wl-metric { text-align: center; padding: 10px 6px; border-radius: 12px; background: rgba(255,255,255,.04); }
.wl-mval { font-size: 1.25rem; font-weight: 800; }
.wl-mlabel { font-size: .72rem; color: var(--c-mut); margin-top: 3px; }
@media (max-width: 560px) { .wl-metrics { grid-template-columns: repeat(2, 1fr); } }

.wl-add { padding: 16px 18px; margin-bottom: 18px; display: flex; flex-direction: column; gap: 10px; }
.wl-add-title { font-weight: 700; }
.wl-add input { width: 100%; padding: 9px 12px; border-radius: 10px;
  border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.04); color: inherit; }
.wl-add-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 560px) { .wl-add-row { grid-template-columns: 1fr; } }
.wl-add-foot { display: flex; align-items: center; gap: 12px; }

.wl-rows { display: flex; flex-direction: column; gap: 10px; }
.wl-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; flex-wrap: wrap; }
.wl-row-title { font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.wl-row-by { font-size: .8rem; margin-top: 2px; }
.wl-tag { font-size: .72rem; padding: 2px 8px; border-radius: 999px; font-weight: 700; }
.wl-tag-on { background: rgba(74,222,128,.16); color: #4ade80; }
.wl-tag-off { background: rgba(156,163,175,.16); color: #9ca3af; }
.wl-row-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-mini { padding: 6px 12px; border-radius: 9px; border: 1px solid rgba(255,255,255,.14);
  background: rgba(255,255,255,.05); color: inherit; cursor: pointer; font-size: .82rem; }
.btn-mini:hover { background: rgba(255,255,255,.1); }
.btn-mini-go { border-color: rgba(74,222,128,.4); color: #4ade80; }
.btn-mini-del { border-color: rgba(248,113,113,.35); color: #f87171; }
.btn-mini:disabled { opacity: .5; cursor: default; }
```

> Note : si une variable (`--c-mut`, `--c-accent`) n'existe pas exactement sous ce nom dans `style.css`, utiliser le nom réel défini en haut du fichier (les fallbacks `#…` couvrent déjà le cas).

- [ ] **Step 2: Recharger et vérifier le rendu**

Recharger `http://localhost:8080/watchlist`.
Expected: panneau live stylé (pastille d'état, 4 métriques en grille), formulaire et lignes de gestion cohérents avec la DA. **Console F12 propre.**

- [ ] **Step 3: Commit**

```bash
git add style.css
git commit -m "feat(watchlist): styles panneau live + gestion (phase C-3)"
```

---

## Validation finale (E2E manuel — à dérouler avec Tristan)

> ⚠️ Prérequis : migration Task 1 appliquée à la main dans Supabase + `scrape_heartbeats` dans `supabase_realtime`.

1. **Moteur off** → `/watchlist` : si une recherche est active, le badge doit être `⚫ PC hors ligne` ; sinon « aucune recherche active ».
2. **Ajout** : ajouter une recherche LBC → apparaît dans la liste en `⏸️ en pause`.
3. **Activer** : cliquer « Activer » → passe `✅ en cours`, les autres repassent en pause (invariant ≤ 1 active).
4. **Moteur on** (`python server.py --auto`) → après ~15-30 s : badge `🟢 PC actif (il y a … s)`, `annonces/min` se remplit, `dernière passe` avance, `annonces vues` grimpe.
5. **Couper le moteur** → en < 1 min le badge bascule tout seul en `⚫ PC hors ligne` (timer client).
6. **RLS** : un membre non-admin ne voit PAS les boutons Éditer/Supprimer sur la recherche d'un autre ; un admin les voit sur toutes.
7. **Non-régression** : feed, item (+ commentaires C-2), dashboard inchangés.

---

## Self-Review (rempli par l'auteur du plan)

**Couverture spec :**
- Table `scrape_heartbeats` + RLS + realtime → Task 1 ✅
- RPC `set_active_watchlist` + override admin → Task 1 ✅
- `scrape_log.new_ads` + lectures (`new_ads_rate`, `ads_seen_total`, `last_pass_at`, `blocked_recent`) → Task 2 ✅
- `process_search` remonte les neuves → Task 3 ✅
- `Supa.upsert_heartbeat` → Task 4 ✅
- `engine/telemetry.py` (`build_heartbeat_payload` + `heartbeat_worker`) → Task 5 ✅
- `heartbeat_worker` lancé sous `--auto` → Task 6 ✅
- `js/lib/watchlist.js` (list/create/update/delete/setActive/pause/heartbeats/subscribe) → Task 7 ✅
- `js/pages/watchlist.js` (panneau live + gestion + ajout) → Task 8 ✅
- online/offline recalculé client + timer auto-nettoyé → Task 8 ✅
- styles → Task 9 ✅

**Cohérence des types/signatures :** `log_scrape(search_id, status, blocked=0, new_ads=0, now=None)` cohérent entre Task 2 (def), Task 3 (appel `new_ads=counts["new"]`) et tests. `build_heartbeat_payload(brain, search_id, now=None)` et `heartbeat_worker(brain, supa, stop_event, interval=15.0, max_loops=None)` cohérents entre Task 5 (def), Task 6 (appel `heartbeat_worker(brain, supa, stop_event)`) et tests. `supa` expose bien `fetch_active_searches` + `upsert_heartbeat` (Task 4) utilisés par le worker (Task 5/6).

**Placeholders :** aucun TBD/TODO ; tout le code est fourni.

**Note import (Task 8) :** `supa` est importé une seule fois, en tête du fichier (`import { supa } from '../supabase-client.js';`), utilisé par le timer pour `supa.removeChannel(channel)`. Pas de doublon.
