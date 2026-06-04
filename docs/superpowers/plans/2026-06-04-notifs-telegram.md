# Notifications Telegram — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Envoyer une notification Telegram au groupe quand une opportunité 🔴 est publiée, et un DM à Tristan quand le captcha Datadome bloque le scraping.

**Architecture:** Nouveau module `engine/telegram.py` (TelegramClient + send_opportunity + send_alert). Dédup via table `telegram_sent` dans le Brain SQLite. Hook dans `enrich.py` après l'insert final d'un 🔴. Hook dans `bootstrap.py` à la détection du captcha. Le TelegramClient est créé dans `server.py` et injecté en paramètre optionnel dans les workers (mode silencieux si token absent).

**Tech Stack:** Python 3.12, aiohttp, pytest asyncio_mode=auto, API Telegram Bot (sendMessage). Convention : pytest = backend uniquement ; serveur dev = `python server.py`.

**Spec:** `docs/superpowers/specs/2026-06-04-notifs-telegram-design.md`

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `engine/telegram.py` | Créer | TelegramClient + send_opportunity + send_alert |
| `engine/db.py` | Modifier | Table `telegram_sent` + `is_telegram_sent` + `mark_telegram_sent` |
| `engine/enrich.py` | Modifier | Hook après insert 🔴 + paramètre `telegram` |
| `engine/bootstrap.py` | Modifier | Hook captcha + paramètre `telegram` |
| `server.py` | Modifier | Création TelegramClient + injection dans les workers |
| `.env.example` | Modifier | 3 variables Telegram commentées |
| `tests/test_engine_db_telegram.py` | Créer | Tests Brain telegram_sent |
| `tests/test_engine_telegram.py` | Créer | Tests send_opportunity / send_alert |

---

## Task 1 : Brain SQLite — table `telegram_sent`

**Files:**
- Modify: `engine/db.py`
- Create: `tests/test_engine_db_telegram.py`

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_engine_db_telegram.py` :

```python
from engine.db import Brain


def test_is_telegram_sent_absent_returns_false():
    b = Brain(":memory:")
    assert b.is_telegram_sent("abc") is False


def test_mark_then_is_sent():
    b = Brain(":memory:")
    b.mark_telegram_sent("abc", now=1000)
    assert b.is_telegram_sent("abc") is True


def test_mark_telegram_sent_idempotent():
    """Marquer deux fois le même ad_id ne doit pas lever d'exception."""
    b = Brain(":memory:")
    b.mark_telegram_sent("abc", now=1000)
    b.mark_telegram_sent("abc", now=2000)
    assert b.is_telegram_sent("abc") is True


def test_different_ad_ids_are_independent():
    b = Brain(":memory:")
    b.mark_telegram_sent("aaa", now=1000)
    assert b.is_telegram_sent("bbb") is False
```

- [ ] **Step 2 : Lancer → échec attendu**

```bash
python -m pytest tests/test_engine_db_telegram.py -v
```

Expected : `AttributeError: 'Brain' object has no attribute 'is_telegram_sent'`

- [ ] **Step 3 : Ajouter la table au SCHEMA dans `engine/db.py`**

Dans `engine/db.py`, localise la constante `SCHEMA` (chaîne SQL multi-lignes). Avant la fermeture `"""`, ajouter :

```sql
CREATE TABLE IF NOT EXISTS telegram_sent (
    ad_id TEXT PRIMARY KEY,
    sent_at INTEGER NOT NULL
);
```

- [ ] **Step 4 : Ajouter les méthodes à la classe `Brain`**

Dans la classe `Brain` (à la suite des méthodes existantes, ex. après `set_city_geo`) :

```python
    def is_telegram_sent(self, ad_id: str) -> bool:
        """True si une notification Telegram a déjà été envoyée pour cet ad_id."""
        row = self.conn.execute(
            "SELECT 1 FROM telegram_sent WHERE ad_id = ?", (ad_id,)
        ).fetchone()
        return row is not None

    def mark_telegram_sent(self, ad_id: str, now: int | None = None) -> None:
        """Enregistre qu'une notification Telegram a été envoyée pour cet ad_id."""
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO telegram_sent (ad_id, sent_at) VALUES (?, ?) "
            "ON CONFLICT(ad_id) DO UPDATE SET sent_at = excluded.sent_at",
            (ad_id, now),
        )
        self.conn.commit()
```

> `time` est déjà importé en haut de `engine/db.py`.

- [ ] **Step 5 : Lancer → succès**

```bash
python -m pytest tests/test_engine_db_telegram.py tests/test_engine_db.py -v
```

Expected : tous PASS.

- [ ] **Step 6 : Non-régression**

```bash
python -m pytest tests/ -q
```

Expected : tous les tests passent.

- [ ] **Step 7 : Commit**

```bash
git add engine/db.py tests/test_engine_db_telegram.py
git commit -m "feat(engine): table telegram_sent dans le Brain (dedup notifs)"
```

---

## Task 2 : `engine/telegram.py`

**Files:**
- Create: `engine/telegram.py`
- Create: `tests/test_engine_telegram.py`

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_engine_telegram.py` :

```python
import pytest
import engine.telegram as tg_mod
from aiohttp import web, ClientSession
from engine.telegram import TelegramClient, send_opportunity, send_alert, _format_opportunity


def _make_tg_app(captured: dict, status: int = 200):
    """App aiohttp qui simule l'API Telegram Bot."""
    async def sendMessage(request):
        captured["body"] = await request.json()
        if status >= 400:
            return web.Response(status=status, text="error")
        return web.json_response({"ok": True})
    app = web.Application()
    app.router.add_post("/bot{token}/sendMessage", sendMessage)
    return app


# ── Tests _format_opportunity ─────────────────────────────────────────────────

def test_format_opportunity_full():
    opp = {
        "title": "Laptop Dell", "price": 120, "est_margin_eur": 80,
        "location_city": "Paris", "url": "https://www.leboncoin.fr/ad/1", "id": "uuid1",
    }
    msg = _format_opportunity(opp)
    assert "Laptop Dell" in msg
    assert "120 €" in msg
    assert "+80 €" in msg
    assert "Paris" in msg
    assert "uuid1" in msg
    assert "leboncoin.fr" in msg


def test_format_opportunity_no_city_no_margin():
    opp = {"title": "Item", "price": 30, "url": "https://www.leboncoin.fr/ad/2", "id": "uuid2"}
    msg = _format_opportunity(opp)
    assert "📍" not in msg   # pas de ville
    assert "📈" not in msg   # pas de marge


def test_format_opportunity_zero_margin_omitted():
    opp = {"title": "Item", "price": 10, "est_margin_eur": 0, "id": "x"}
    msg = _format_opportunity(opp)
    assert "📈" not in msg   # marge nulle → omise


# ── Tests send_opportunity ────────────────────────────────────────────────────

async def test_send_opportunity_posts_to_group(aiohttp_server, monkeypatch):
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "GROUP123", "TRISTAN456", session)
        await send_opportunity(client, {"title": "T", "price": 10, "id": "x1", "url": "https://lbc.fr/ad/1"})
    assert captured["body"]["chat_id"] == "GROUP123"
    assert "🔴" in captured["body"]["text"]
    assert captured["body"]["parse_mode"] == "Markdown"


async def test_send_alert_posts_to_tristan(aiohttp_server, monkeypatch):
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "GROUP123", "TRISTAN456", session)
        await send_alert(client, "⚠️ Captcha détecté")
    assert captured["body"]["chat_id"] == "TRISTAN456"
    assert "Captcha" in captured["body"]["text"]


async def test_send_opportunity_absorbs_http_error(aiohttp_server, monkeypatch):
    """Erreur HTTP 500 → pas d'exception levée (best-effort)."""
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured, status=500))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "G", "T", session)
        await send_opportunity(client, {"title": "X", "id": "y"})  # ne doit PAS lever


async def test_send_alert_absorbs_network_error(monkeypatch):
    """Erreur réseau → pas d'exception levée (best-effort)."""
    monkeypatch.setattr(tg_mod, "TG_API", "http://localhost:1/bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "G", "T", session)
        await send_alert(client, "test")  # ne doit PAS lever
```

- [ ] **Step 2 : Lancer → échec attendu**

```bash
python -m pytest tests/test_engine_telegram.py -v
```

Expected : `ModuleNotFoundError: No module named 'engine.telegram'`

- [ ] **Step 3 : Créer `engine/telegram.py`**

```python
"""Notifications Telegram pour le moteur autonome.

Deux fonctions publiques best-effort (jamais bloquantes) :
- send_opportunity(client, opp) → groupe partagé (opportunité 🔴)
- send_alert(client, text)      → DM Tristan (captcha, alertes techniques)
"""
from __future__ import annotations

import aiohttp

HUB_BASE = "https://shisuboi.github.io/lbc-hub"
TG_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramClient:
    """Wrapper minimal vers l'API Telegram Bot."""

    def __init__(self, token: str, group_id: str, tristan_id: str,
                 session: aiohttp.ClientSession):
        self.token = token
        self.group_id = group_id
        self.tristan_id = tristan_id
        self.session = session


def _format_opportunity(opp: dict) -> str:
    """Formate un message Markdown pour une opportunité 🔴."""
    title = opp.get("title") or "Sans titre"
    price = opp.get("price")
    margin = opp.get("est_margin_eur")
    city = opp.get("location_city")
    url = opp.get("url", "")
    opp_id = opp.get("id") or opp.get("ad_id", "")

    lines = [f"🔴 *{title}*", ""]
    if price is not None:
        lines.append(f"💰 Prix : {int(price)} €")
    if margin and float(margin) > 0:
        lines.append(f"📈 Marge estimée : +{int(margin)} €")
    if city:
        lines.append(f"📍 {city}")
    lines.append("")
    if url:
        lines.append(f"🔗 [Voir sur LBC]({url})")
    if opp_id:
        lines.append(f"🏠 [Voir sur le hub]({HUB_BASE}/item/{opp_id})")

    return "\n".join(lines)


async def send_opportunity(client: TelegramClient, opp: dict) -> None:
    """Envoie une notification d'opportunité 🔴 au groupe. Best-effort."""
    try:
        url = TG_API.format(token=client.token)
        async with client.session.post(
            url,
            json={"chat_id": client.group_id, "text": _format_opportunity(opp),
                  "parse_mode": "Markdown"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                print(f"[telegram] erreur envoi opportunité (HTTP {resp.status}): {body[:200]}")
    except Exception as exc:
        print(f"[telegram] erreur envoi opportunité : {exc}")


async def send_alert(client: TelegramClient, text: str) -> None:
    """Envoie une alerte technique en DM à Tristan. Best-effort."""
    try:
        url = TG_API.format(token=client.token)
        async with client.session.post(
            url,
            json={"chat_id": client.tristan_id, "text": text},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                print(f"[telegram] erreur envoi alerte (HTTP {resp.status}): {body[:200]}")
    except Exception as exc:
        print(f"[telegram] erreur envoi alerte : {exc}")
```

- [ ] **Step 4 : Lancer → succès**

```bash
python -m pytest tests/test_engine_telegram.py -v
```

Expected : 7 tests PASS.

- [ ] **Step 5 : Non-régression**

```bash
python -m pytest tests/ -q
```

Expected : tous les tests passent.

- [ ] **Step 6 : Commit**

```bash
git add engine/telegram.py tests/test_engine_telegram.py
git commit -m "feat(engine): telegram.py — TelegramClient + send_opportunity + send_alert"
```

---

## Task 3 : Hook dans `engine/enrich.py`

**Files:**
- Modify: `engine/enrich.py`
- Modify: `tests/test_engine_enrich.py`

- [ ] **Step 1 : Écrire les nouveaux tests (ajouter à la fin de `tests/test_engine_enrich.py`)**

```python
async def test_enrich_once_sends_telegram_for_urgent(monkeypatch):
    """Opp urgente + telegram configuré → send_opportunity appelée, ad_id marqué."""
    sent = []
    async def fake_send(client, opp):
        sent.append(opp.get("ad_id"))
    monkeypatch.setattr("engine.enrich.send_opportunity", fake_send)

    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "urgent-1", price=200.0)
    router = ScriptedRouter(
        triage_items=[{"ad_id": "urgent-1", "category": "interesting", "score": 85, "dig_deeper": True}],
        verify={"refined_score": 92, "est_market_price": 350.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["pro"],
    )
    telegram_stub = object()  # objet quelconque non-None pour activer le hook
    await enrich_once(brain, supa, router,
                      settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, telegram=telegram_stub)
    assert "urgent-1" in sent, "send_opportunity doit être appelée pour une opp urgente"
    assert brain.is_telegram_sent("urgent-1"), "ad_id doit être marqué comme envoyé"


async def test_enrich_once_no_duplicate_telegram(monkeypatch):
    """Si ad_id déjà marqué comme envoyé → send_opportunity pas rappelée."""
    sent = []
    async def fake_send(client, opp):
        sent.append(opp.get("ad_id"))
    monkeypatch.setattr("engine.enrich.send_opportunity", fake_send)

    brain = Brain(":memory:")
    brain.mark_telegram_sent("urgent-2")  # pré-marquer
    supa = FakeSupa()
    queue_ad(brain, "urgent-2", price=200.0)
    router = ScriptedRouter(
        triage_items=[{"ad_id": "urgent-2", "category": "interesting", "score": 85, "dig_deeper": True}],
        verify={"refined_score": 92, "est_market_price": 350.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["pro"],
    )
    telegram_stub = object()
    await enrich_once(brain, supa, router,
                      settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, telegram=telegram_stub)
    assert sent == [], "send_opportunity NE doit PAS être rappelée si déjà marqué"
```

- [ ] **Step 2 : Lancer → échec attendu**

```bash
python -m pytest tests/test_engine_enrich.py::test_enrich_once_sends_telegram_for_urgent tests/test_engine_enrich.py::test_enrich_once_no_duplicate_telegram -v
```

Expected : `TypeError: enrich_once() got an unexpected keyword argument 'telegram'`

- [ ] **Step 3 : Modifier `engine/enrich.py`**

**3a. Ajouter l'import** en haut (après `from engine.geo import fill_latlon`) :

```python
from engine.telegram import send_opportunity
```

**3b. Modifier la signature de `enrich_once`** (ligne 32) :

```python
async def enrich_once(brain, supa, router, settings, searches_by_id, image_fetch, batch_size=15, telegram=None) -> int:
```

**3c. Ajouter le hook Telegram** après le bloc `try/except` de l'insert final (lignes 114-117). Remplacer :

```python
            try:
                await supa.insert_opportunity(payload)  # mise à jour post-vérif/photo
            except Exception:
                brain.queue_outbox(payload)

        brain.delete_pending(item["id"])
```

par :

```python
            try:
                await supa.insert_opportunity(payload)  # mise à jour post-vérif/photo
            except Exception:
                brain.queue_outbox(payload)

            # Notification Telegram 🔴 (best-effort, après vérif/photo finale)
            if telegram and payload.get("category") == "urgent":
                ad_id_str = payload.get("ad_id", "")
                if ad_id_str and not brain.is_telegram_sent(ad_id_str):
                    await send_opportunity(telegram, payload)
                    brain.mark_telegram_sent(ad_id_str)

        brain.delete_pending(item["id"])
```

**3d. Ajouter `telegram=None` à `enrichment_worker`** (ligne 124) :

```python
async def enrichment_worker(brain, supa, router, settings, fetch_searches, image_fetch,
                            stop_event, pause: float = 5.0, max_loops=None, telegram=None) -> None:
```

Et passer `telegram` à `enrich_once` (ligne 131) :

```python
            await enrich_once(brain, supa, router, settings, searches_by_id, image_fetch,
                              telegram=telegram)
```

- [ ] **Step 4 : Lancer → succès**

```bash
python -m pytest tests/test_engine_enrich.py -v
```

Expected : 10 tests PASS (8 existants + 2 nouveaux).

- [ ] **Step 5 : Non-régression**

```bash
python -m pytest tests/ -q
```

Expected : tous les tests passent.

- [ ] **Step 6 : Commit**

```bash
git add engine/enrich.py tests/test_engine_enrich.py
git commit -m "feat(engine): hook Telegram apres insert urgent dans enrich.py"
```

---

## Task 4 : Hook captcha dans `engine/bootstrap.py`

**Files:**
- Modify: `engine/bootstrap.py`

- [ ] **Step 1 : Modifier `make_scrape_fn`**

Dans `engine/bootstrap.py`, modifier la signature de `make_scrape_fn` pour ajouter `telegram=None` :

```python
def make_scrape_fn(
    get_context,
    extract_fn,
    scrape_lock: asyncio.Lock,
    ready_selector: str | None = None,
    ready_timeout_ms: int = 8000,
    captcha_wait_ms: int = 120000,
    telegram=None,
):
```

Ajouter l'import au début du fichier (après `import asyncio`) :

```python
from engine.telegram import send_alert
```

Dans le corps de `scrape_fn`, remplacer le bloc de log captcha (lignes ~39-45) :

```python
                    except Exception as exc:
                        # Pas d'annonces tout de suite : blocage Datadome probable.
                        # On garde l'onglet ouvert et on laisse à l'humain le temps de résoudre.
                        print(
                            f"⚠️ [AUTO] Pas d'annonces après {ready_timeout_ms} ms "
                            f"({type(exc).__name__}). Blocage/captcha probable — résous-le dans "
                            "la fenêtre Chromium (attente jusqu'à 2 min)..."
                        )
                        try:
                            await page.wait_for_selector(ready_selector, timeout=captcha_wait_ms)
```

par :

```python
                    except Exception as exc:
                        # Pas d'annonces tout de suite : blocage Datadome probable.
                        # On garde l'onglet ouvert et on laisse à l'humain le temps de résoudre.
                        print(
                            f"⚠️ [AUTO] Pas d'annonces après {ready_timeout_ms} ms "
                            f"({type(exc).__name__}). Blocage/captcha probable — résous-le dans "
                            "la fenêtre Chromium (attente jusqu'à 2 min)..."
                        )
                        if telegram:
                            await send_alert(
                                telegram,
                                "⚠️ Captcha Datadome détecté — scraping bloqué. "
                                "Résous-le dans la fenêtre Chromium."
                            )
                        try:
                            await page.wait_for_selector(ready_selector, timeout=captcha_wait_ms)
```

- [ ] **Step 2 : Non-régression**

```bash
python -m pytest tests/ -q
```

Expected : tous les tests passent.

- [ ] **Step 3 : Commit**

```bash
git add engine/bootstrap.py
git commit -m "feat(engine): hook captcha Datadome dans bootstrap.py (alerte Telegram)"
```

---

## Task 5 : Intégration `server.py` + `.env.example`

**Files:**
- Modify: `server.py`
- Modify: `.env.example`

- [ ] **Step 1 : Ajouter l'import dans `server.py`**

Après la ligne `from engine.maintenance import run_maintenance` (ou à la suite des imports engine) :

```python
from engine.telegram import TelegramClient
```

- [ ] **Step 2 : Créer le TelegramClient dans `start_autonomous_engine`**

Dans `start_autonomous_engine`, après la ligne `supa = Supa(...)` (ligne ~555) et avant `sink = LocalSink(brain)`, ajouter :

```python
    # Telegram (optionnel) : notifications opportunités 🔴 + alertes captcha
    telegram = None
    if (cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_GROUP_ID")
            and cfg.get("TELEGRAM_TRISTAN_ID")):
        telegram = TelegramClient(
            cfg["TELEGRAM_BOT_TOKEN"],
            cfg["TELEGRAM_GROUP_ID"],
            cfg["TELEGRAM_TRISTAN_ID"],
            session,
        )
        print("📨 Notifications Telegram activées.")
    else:
        print("📨 Telegram non configuré — notifications désactivées.")
```

- [ ] **Step 3 : Injecter `telegram` dans `make_scrape_fn`**

Remplacer l'appel existant à `make_scrape_fn` (lignes ~562-565) :

```python
    scrape_fn = make_scrape_fn(
        get_context, extract_ads_from_results, scrape_lock,
        ready_selector=RESULTS_CONTAINER_SELECTOR,
    )
```

par :

```python
    scrape_fn = make_scrape_fn(
        get_context, extract_ads_from_results, scrape_lock,
        ready_selector=RESULTS_CONTAINER_SELECTOR,
        telegram=telegram,
    )
```

- [ ] **Step 4 : Injecter `telegram` dans `enrichment_worker`**

Remplacer l'appel existant à `enrichment_worker` (lignes ~590-592) :

```python
        tasks.append(asyncio.create_task(
            enrichment_worker(brain, supa, router, ai, fetch_searches, image_fetch, stop_event)
        ))
```

par :

```python
        tasks.append(asyncio.create_task(
            enrichment_worker(brain, supa, router, ai, fetch_searches, image_fetch, stop_event,
                              telegram=telegram)
        ))
```

- [ ] **Step 5 : Mettre à jour `.env.example`**

Remplacer la ligne :

```
# Optionnel (Phase C) : TELEGRAM_BOT_TOKEN=...
```

par :

```
# --- Telegram (optionnel) : notifications opportunités 🔴 + alertes captcha ---
# TELEGRAM_BOT_TOKEN=...         # Token du bot (@BotFather)
# TELEGRAM_GROUP_ID=...          # chat_id du groupe partagé (ex. -1001234567890)
# TELEGRAM_TRISTAN_ID=...        # chat_id DM Tristan (ex. 123456789)
```

- [ ] **Step 6 : Vérifier que le serveur démarre sans erreur**

```bash
python server.py
```

Expected : démarrage normal, `📨 Telegram non configuré — notifications désactivées.` n'apparaît PAS en mode non-auto (le bloc est dans `start_autonomous_engine`). Pas d'erreur d'import.

- [ ] **Step 7 : Non-régression**

```bash
python -m pytest tests/ -q
```

Expected : tous les tests passent.

- [ ] **Step 8 : Commit**

```bash
git add server.py .env.example
git commit -m "feat(server): injection TelegramClient dans les workers (notifs Telegram)"
```

---

## Validation finale

1. `python -m pytest tests/ -q` → suite complète PASS
2. (optionnel) Configurer `TELEGRAM_BOT_TOKEN` + `TELEGRAM_GROUP_ID` + `TELEGRAM_TRISTAN_ID` dans `.env`, lancer `python server.py --auto` → log `📨 Notifications Telegram activées.`
3. (optionnel) Déclencher manuellement `send_opportunity` en console pour vérifier le format du message

---

## Self-Review

**Couverture spec :**
- `TelegramClient` + `send_opportunity` + `send_alert` → Task 2 ✅
- Table `telegram_sent` + `is_telegram_sent` + `mark_telegram_sent` → Task 1 ✅
- Hook enrich.py après insert 🔴, avec dédup → Task 3 ✅
- Hook captcha bootstrap.py → Task 4 ✅
- Création TelegramClient dans server.py + injection → Task 5 ✅
- `.env.example` avec 3 variables → Task 5 ✅
- Mode silencieux si token absent → Task 5 (condition `if cfg.get(...)`) ✅
- Best-effort (absorbe exceptions) → Task 2 (`send_opportunity`/`send_alert`) ✅
- Message format : titre, prix, marge, ville, liens LBC + hub → Task 2 (`_format_opportunity`) ✅
- URL hub prod : `https://shisuboi.github.io/lbc-hub/item/{id}` → Task 2 (`HUB_BASE`) ✅

**Types/signatures cohérents :**
- `TelegramClient(token, group_id, tristan_id, session)` → défini Task 2, instancié Task 5 ✅
- `send_opportunity(client, opp)` → défini Task 2, monkeypatché Task 3, appelé dans enrich.py ✅
- `send_alert(client, text)` → défini Task 2, importé Task 4, appelé Task 4 ✅
- `is_telegram_sent(ad_id)` / `mark_telegram_sent(ad_id)` → définis Task 1, utilisés Task 3 ✅
- `enrich_once(..., telegram=None)` → signature Task 3, tests Task 3 ✅
- `enrichment_worker(..., telegram=None)` → signature Task 3, appel Task 5 ✅
- `make_scrape_fn(..., telegram=None)` → signature Task 4, appel Task 5 ✅
