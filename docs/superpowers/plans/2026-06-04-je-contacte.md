# Signal « Je contacte » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre aux membres de signaler « Je m'en occupe » depuis la page `/item/:id` et depuis le bouton inline du message Telegram, avec pin visuel dans le fil de commentaires et exclusivité un-seul-à-la-fois.

**Architecture:** `item_comments` reçoit les colonnes `type` et `cancelled_at`. Un RPC Supabase gère la création et l'annulation. Le moteur ajoute une coroutine `telegram_poll_worker` qui reçoit les `callback_query` Telegram, insère le signal en service_role, et répond avec un toast. Le frontend affiche le signal en haut du fil avec un style distinct.

**Tech Stack:** Python 3.12, aiohttp, pytest asyncio_mode=auto. Vanilla JS ES6, Supabase SDK v2. Migration SQL manuelle via Dashboard Supabase. Convention : pas de tests frontend — validation manuelle sur `/item/:id`.

**Spec:** `docs/superpowers/specs/2026-06-04-je-contacte-design.md`

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `supabase/migrations/2026-06-04-je-contacte.sql` | Créer | Migration : colonnes type/cancelled_at + index + RPCs |
| `engine/db.py` | Modifier | SCHEMA telegram_poll_offset + 2 méthodes |
| `engine/supa.py` | Modifier | `create_contact_from_telegram` |
| `engine/telegram.py` | Modifier | `get_updates`, `answer_callback`, inline button dans `send_opportunity` |
| `engine/telegram_bot.py` | Créer | `telegram_poll_worker` coroutine |
| `server.py` | Modifier | Démarrer `telegram_poll_worker` si Telegram configuré |
| `js/lib/comments.js` | Modifier | SELECT étendu + `createContactSignal` + `cancelContactSignal` + exclure contacts du count |
| `js/components/comments.js` | Modifier | Pin contact, bouton « Je contacte », annulation |
| `style.css` | Modifier | Styles `.cm-contact-pin`, `.btn-contact`, `.cm-contact-taken` |
| `tests/test_engine_db_telegram_offset.py` | Créer | Tests Brain offset |
| `tests/test_engine_supa_contact.py` | Créer | Tests create_contact_from_telegram |
| `tests/test_engine_telegram_bot.py` | Créer | Tests telegram_poll_worker |

---

## Task 1 : Migration SQL Supabase

**Files:**
- Create: `supabase/migrations/2026-06-04-je-contacte.sql`

- [ ] **Step 1 : Créer le fichier de migration**

```sql
-- Migration : signal de contact dans item_comments

-- 1. Nouvelles colonnes sur item_comments
ALTER TABLE item_comments
  ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'comment',
  ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

-- 2. Index unique partiel : un seul signal actif par opportunité
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_contact
  ON item_comments(opportunity_id)
  WHERE type = 'contact' AND cancelled_at IS NULL;

-- 3. RPC : créer un signal de contact (depuis le hub, utilisateur authentifié)
CREATE OR REPLACE FUNCTION create_contact_signal(p_opportunity_id UUID)
RETURNS SETOF item_comments
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE v_username TEXT;
BEGIN
  SELECT username INTO v_username FROM profiles WHERE id = auth.uid();
  IF v_username IS NULL THEN
    RAISE EXCEPTION 'Profil introuvable.';
  END IF;
  RETURN QUERY
    INSERT INTO item_comments(opportunity_id, user_id, body, type)
    VALUES (
      p_opportunity_id,
      auth.uid(),
      '🤝 ' || v_username || ' s''en occupe',
      'contact'
    )
    RETURNING *;
END;
$$;

-- 4. RPC : annuler un signal de contact (auteur ou admin)
CREATE OR REPLACE FUNCTION cancel_contact_signal(p_comment_id UUID)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM item_comments ic
    WHERE ic.id = p_comment_id
    AND (
      ic.user_id = auth.uid()
      OR EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
    )
  ) THEN
    RAISE EXCEPTION 'Accès refusé.';
  END IF;
  UPDATE item_comments SET cancelled_at = now() WHERE id = p_comment_id;
END;
$$;
```

- [ ] **Step 2 : Appliquer la migration manuellement**

Dans le Dashboard Supabase → **SQL Editor** → coller le contenu du fichier → **Run**.

Vérifier que la table `item_comments` a bien les colonnes `type` et `cancelled_at`, et que les fonctions `create_contact_signal` / `cancel_contact_signal` apparaissent dans **Database → Functions**.

- [ ] **Step 3 : Commit**

```bash
git add supabase/migrations/2026-06-04-je-contacte.sql
git commit -m "feat(db): migration signal Je contacte (type/cancelled_at + RPCs)"
```

---

## Task 2 : Brain SQLite — offset de polling Telegram

**Files:**
- Modify: `engine/db.py`
- Create: `tests/test_engine_db_telegram_offset.py`

- [ ] **Step 1 : Écrire les tests**

```python
# tests/test_engine_db_telegram_offset.py
from engine.db import Brain


def test_get_telegram_offset_default_is_zero():
    b = Brain(":memory:")
    assert b.get_telegram_offset() == 0


def test_set_then_get_telegram_offset():
    b = Brain(":memory:")
    b.set_telegram_offset(42)
    assert b.get_telegram_offset() == 42


def test_set_telegram_offset_overwrites():
    b = Brain(":memory:")
    b.set_telegram_offset(10)
    b.set_telegram_offset(99)
    assert b.get_telegram_offset() == 99
```

- [ ] **Step 2 : Lancer → échec**

```bash
python -m pytest tests/test_engine_db_telegram_offset.py -v
```
Expected : `AttributeError: 'Brain' object has no attribute 'get_telegram_offset'`

- [ ] **Step 3 : Ajouter la table au SCHEMA de `engine/db.py`**

Dans la constante `SCHEMA`, avant la fermeture `"""`, ajouter :

```sql
CREATE TABLE IF NOT EXISTS telegram_poll_offset (
    id INTEGER PRIMARY KEY DEFAULT 1,
    offset INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO telegram_poll_offset (id, offset) VALUES (1, 0);
```

- [ ] **Step 4 : Ajouter les méthodes à la classe `Brain`** (après `mark_telegram_sent`)

```python
    def get_telegram_offset(self) -> int:
        """Retourne l'offset de polling getUpdates (0 si non initialisé)."""
        row = self.conn.execute(
            "SELECT offset FROM telegram_poll_offset WHERE id = 1"
        ).fetchone()
        return row["offset"] if row else 0

    def set_telegram_offset(self, offset: int) -> None:
        """Met à jour l'offset de polling getUpdates."""
        self.conn.execute(
            "INSERT INTO telegram_poll_offset(id, offset) VALUES(1,?) "
            "ON CONFLICT(id) DO UPDATE SET offset=excluded.offset",
            (offset,),
        )
        self.conn.commit()
```

- [ ] **Step 5 : Lancer → succès**

```bash
python -m pytest tests/test_engine_db_telegram_offset.py -v
```
Expected : 3 tests PASS.

- [ ] **Step 6 : Non-régression**

```bash
python -m pytest tests/ -q
```
Expected : tous les tests passent.

- [ ] **Step 7 : Commit**

```bash
git add engine/db.py tests/test_engine_db_telegram_offset.py
git commit -m "feat(engine): Brain offset polling Telegram (telegram_poll_offset)"
```

---

## Task 3 : `Supa.create_contact_from_telegram`

**Files:**
- Modify: `engine/supa.py`
- Create: `tests/test_engine_supa_contact.py`

- [ ] **Step 1 : Écrire les tests**

```python
# tests/test_engine_supa_contact.py
import pytest
from aiohttp import web, ClientSession
from engine.supa import Supa


def _make_app(status: int, captured: dict | None = None):
    if captured is None:
        captured = {}

    async def post_comment(request):
        captured["body"] = await request.json()
        return web.Response(status=status)

    app = web.Application()
    app.router.add_post("/rest/v1/item_comments", post_comment)
    return app, captured


async def test_create_contact_success_returns_true(aiohttp_server):
    app, captured = _make_app(201)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        supa = Supa(str(server.make_url("")), "k", session)
        result = await supa.create_contact_from_telegram("opp-uuid", "Tristan")
    assert result is True
    assert "(via Telegram)" in captured["body"]["body"]
    assert captured["body"]["type"] == "contact"
    assert captured["body"]["user_id"] is None


async def test_create_contact_already_active_returns_false(aiohttp_server):
    """409 Conflict (index unique partiel) → retourne False sans lever."""
    app, _ = _make_app(409)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        supa = Supa(str(server.make_url("")), "k", session)
        result = await supa.create_contact_from_telegram("opp-uuid", "Tristan")
    assert result is False


async def test_create_contact_body_contains_first_name(aiohttp_server):
    app, captured = _make_app(201)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        supa = Supa(str(server.make_url("")), "k", session)
        await supa.create_contact_from_telegram("opp-uuid", "Susanna")
    assert "Susanna" in captured["body"]["body"]
```

- [ ] **Step 2 : Lancer → échec**

```bash
python -m pytest tests/test_engine_supa_contact.py -v
```
Expected : `AttributeError: 'Supa' object has no attribute 'create_contact_from_telegram'`

- [ ] **Step 3 : Ajouter la méthode dans `engine/supa.py`** (dans la classe `Supa`, après `upsert_heartbeat`)

```python
    async def create_contact_from_telegram(self, opportunity_id: str, first_name: str) -> bool:
        """Insère un signal de contact via Telegram (service_role, bypass RLS).

        Retourne True si créé, False si déjà actif (conflit 409 sur l'index unique).
        Lève une exception pour toute autre erreur HTTP.
        """
        url = f"{self.base}/rest/v1/item_comments"
        payload = {
            "opportunity_id": opportunity_id,
            "user_id": None,
            "body": f"🤝 {first_name} s'en occupe (via Telegram)",
            "type": "contact",
        }
        headers = self._headers({"Prefer": "return=minimal"})
        async with self.session.post(url, json=payload, headers=headers) as resp:
            if resp.status == 409:
                return False
            resp.raise_for_status()
            return True
```

- [ ] **Step 4 : Lancer → succès**

```bash
python -m pytest tests/test_engine_supa_contact.py -v
```
Expected : 3 tests PASS.

- [ ] **Step 5 : Non-régression**

```bash
python -m pytest tests/ -q
```
Expected : tous les tests passent.

- [ ] **Step 6 : Commit**

```bash
git add engine/supa.py tests/test_engine_supa_contact.py
git commit -m "feat(engine): Supa.create_contact_from_telegram (signal depuis Telegram)"
```

---

## Task 4 : `TelegramClient` — `get_updates`, `answer_callback`, bouton inline

**Files:**
- Modify: `engine/telegram.py`
- Modify: `tests/test_engine_telegram.py` (ajouter 3 tests à la fin)

- [ ] **Step 1 : Écrire les 3 nouveaux tests** (à ajouter à la fin de `tests/test_engine_telegram.py`)

```python
async def test_send_opportunity_includes_inline_button(aiohttp_server, monkeypatch):
    """send_opportunity avec opp['id'] → reply_markup avec bouton 🤝 inclus."""
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("/")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "GROUP", "TRISTAN", session)
        await send_opportunity(client, {"title": "T", "price": 10, "id": "uuid-abc", "url": "https://lbc.fr/ad/1"})
    import json as _json
    markup = captured["body"].get("reply_markup")
    assert markup is not None, "reply_markup doit être présent quand opp a un id"
    parsed = _json.loads(markup) if isinstance(markup, str) else markup
    text = parsed["inline_keyboard"][0][0]["text"]
    data = parsed["inline_keyboard"][0][0]["callback_data"]
    assert "occupe" in text
    assert "uuid-abc" in data


async def test_get_updates_returns_updates(aiohttp_server, monkeypatch):
    """get_updates appelle getUpdates avec l'offset et retourne la liste."""
    import engine.telegram as tg_mod2

    captured = {}
    async def getUpdates(request):
        captured["body"] = await request.json()
        return web.json_response({"ok": True, "result": [{"update_id": 10}]})

    app = web.Application()
    app.router.add_post("/bot{token}/getUpdates", getUpdates)
    server = await aiohttp_server(app)
    monkeypatch.setattr(tg_mod2, "TG_API", str(server.make_url("/")) + "bot{token}/sendMessage")
    # On patch directement la base URL pour getUpdates
    import engine.telegram as tmod
    orig_base = "https://api.telegram.org"
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "G", "T", session)
        # Monkey-patch l'URL de getUpdates
        server_base = str(server.make_url(""))
        orig = client.token
        client._base_url = server_base  # propriété virtuelle pour le test
        # Test direct via méthode
        updates = await tmod._get_updates_raw(session, "TOKEN", 5, server_base)
    assert len(updates) == 1
    assert updates[0]["update_id"] == 10
    assert captured["body"]["offset"] == 5


async def test_answer_callback_posts_to_telegram(aiohttp_server, monkeypatch):
    """answer_callback envoie answerCallbackQuery. Best-effort."""
    import engine.telegram as tg_mod3

    captured = {}
    async def answerCQ(request):
        captured["body"] = await request.json()
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_post("/bot{token}/answerCallbackQuery", answerCQ)
    server = await aiohttp_server(app)

    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "G", "T", session)

        async def fake_post(url, **kwargs):
            ...

        # Test via monkey-patch de la méthode interne
        orig_answer = tg_mod3.TG_ANSWER_API
        tg_mod3.TG_ANSWER_API = str(server.make_url("/")) + "bot{token}/answerCallbackQuery"
        try:
            await answer_callback(client, "cq-id-123", "🤝 Enregistré !")
        finally:
            tg_mod3.TG_ANSWER_API = orig_answer

    assert captured.get("body", {}).get("callback_query_id") == "cq-id-123"
    assert "Enregistré" in captured["body"]["text"]
```

> **Note :** Ces tests montrent les assertions attendues. Si l'implémentation choisit une structure légèrement différente pour les URL (ex. en réutilisant `TG_API` avec un suffixe `Method`), adapte les patches en conséquence — l'important est que la logique soit couverte.

- [ ] **Step 2 : Lancer → échec attendu**

```bash
python -m pytest tests/test_engine_telegram.py -k "inline_button or get_updates or answer_callback" -v
```
Expected : échecs liés aux attributs manquants.

- [ ] **Step 3 : Modifier `engine/telegram.py`**

**3a. Ajouter les constantes d'URL et l'import json** en haut (après `import aiohttp`) :

```python
import json as _json

HUB_BASE = "https://shisuboi.github.io/lbc-hub"
TG_API = "https://api.telegram.org/bot{token}/sendMessage"
TG_UPDATES_API = "https://api.telegram.org/bot{token}/getUpdates"
TG_ANSWER_API = "https://api.telegram.org/bot{token}/answerCallbackQuery"
```

> Retire l'ancienne définition de `TG_API` si elle est déjà là (il ne doit en exister qu'une seule).

**3b. Modifier `send_opportunity`** pour inclure le bouton inline :

```python
async def send_opportunity(client: TelegramClient, opp: dict) -> None:
    """Envoie une notification d'opportunité 🔴 au groupe. Best-effort."""
    try:
        opp_id = opp.get("id") or opp.get("ad_id", "")
        body = {
            "chat_id": client.group_id,
            "text": _format_opportunity(opp),
            "parse_mode": "Markdown",
        }
        if opp_id:
            body["reply_markup"] = _json.dumps({
                "inline_keyboard": [[{
                    "text": "🤝 Je m'en occupe",
                    "callback_data": f"contact:{opp_id}",
                }]]
            })
        url = TG_API.format(token=client.token)
        async with client.session.post(
            url, json=body,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status >= 400:
                body_text = await resp.text()
                print(f"[telegram] erreur envoi opportunité (HTTP {resp.status}): {body_text[:200]}")
    except Exception as exc:
        print(f"[telegram] erreur envoi opportunité : {exc}")
```

**3c. Ajouter `_get_updates_raw` (fonction interne testable) et `get_updates` (méthode)** :

```python
async def _get_updates_raw(session, token: str, offset: int, base_url: str | None = None) -> list[dict]:
    """Appelle getUpdates. `base_url` permet de rediriger vers un mock dans les tests."""
    url = (base_url.rstrip("/") + f"/bot{token}/getUpdates") if base_url else TG_UPDATES_API.format(token=token)
    try:
        async with session.post(
            url,
            json={"offset": offset, "timeout": 5, "allowed_updates": ["callback_query"]},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("result", [])
    except Exception:
        return []


# Méthode sur TelegramClient (à ajouter à la classe)
# Dans la classe TelegramClient :
```

Ajouter dans la classe `TelegramClient` :

```python
    async def get_updates(self, offset: int = 0) -> list[dict]:
        """Récupère les callback_query depuis l'offset. Best-effort."""
        return await _get_updates_raw(self.session, self.token, offset)

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        """Répond à un callback_query (toast Telegram). Best-effort."""
        try:
            url = TG_ANSWER_API.format(token=self.token)
            async with self.session.post(
                url,
                json={"callback_query_id": callback_query_id, "text": text},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status >= 400:
                    print(f"[telegram] erreur answer_callback (HTTP {resp.status})")
        except Exception as exc:
            print(f"[telegram] erreur answer_callback : {exc}")
```

- [ ] **Step 4 : Ajuster les tests si besoin et lancer**

```bash
python -m pytest tests/test_engine_telegram.py -v
```
Expected : 10 tests PASS (7 existants + 3 nouveaux).

- [ ] **Step 5 : Non-régression**

```bash
python -m pytest tests/ -q
```
Expected : tous les tests passent.

- [ ] **Step 6 : Commit**

```bash
git add engine/telegram.py tests/test_engine_telegram.py
git commit -m "feat(engine): TelegramClient get_updates + answer_callback + bouton inline 🤝"
```

---

## Task 5 : `engine/telegram_bot.py` — worker de polling

**Files:**
- Create: `engine/telegram_bot.py`
- Create: `tests/test_engine_telegram_bot.py`

- [ ] **Step 1 : Écrire les tests**

```python
# tests/test_engine_telegram_bot.py
import asyncio
import pytest
from engine.db import Brain
from engine.telegram_bot import telegram_poll_worker


class FakeTelegram:
    def __init__(self, updates_sequence):
        self._seq = iter(updates_sequence)
        self.answered = []

    async def get_updates(self, offset=0):
        try:
            return next(self._seq)
        except StopIteration:
            return []

    async def answer_callback(self, callback_query_id, text):
        self.answered.append((callback_query_id, text))


class FakeSupa:
    def __init__(self, create_result=True):
        self.calls = []
        self._result = create_result

    async def create_contact_from_telegram(self, opp_id, first_name):
        self.calls.append((opp_id, first_name))
        return self._result


async def _run_worker(brain, supa, telegram, poll_pause=0):
    """Exécute le worker jusqu'à ce que get_updates ne retourne plus rien."""
    stop = asyncio.Event()
    task = asyncio.create_task(
        telegram_poll_worker(brain, supa, telegram, stop, poll_pause=poll_pause)
    )
    await asyncio.sleep(0.05)
    stop.set()
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass


async def test_contact_callback_creates_signal_and_answers_enregistre():
    """callback_query 'contact:uuid' → create_contact + réponse 'Enregistré!'."""
    brain = Brain(":memory:")
    supa = FakeSupa(create_result=True)
    telegram = FakeTelegram([
        [{"update_id": 1, "callback_query": {
            "id": "cq-1", "data": "contact:opp-abc",
            "from": {"first_name": "Tristan"},
        }}],
    ])
    await _run_worker(brain, supa, telegram)
    assert ("opp-abc", "Tristan") in supa.calls
    assert any("Enregistré" in t for _, t in telegram.answered)
    assert brain.get_telegram_offset() == 2  # 1 + 1


async def test_contact_already_active_answers_deja_pris():
    """409 (déjà actif) → réponse 'Quelqu'un s'en occupe déjà'."""
    brain = Brain(":memory:")
    supa = FakeSupa(create_result=False)
    telegram = FakeTelegram([
        [{"update_id": 5, "callback_query": {
            "id": "cq-2", "data": "contact:opp-xyz",
            "from": {"first_name": "Susanna"},
        }}],
    ])
    await _run_worker(brain, supa, telegram)
    assert any("occupe" in t.lower() and "déjà" in t.lower() for _, t in telegram.answered)


async def test_unknown_callback_data_answered_empty():
    """callback_data non 'contact:...' → réponse vide (sans créer de signal)."""
    brain = Brain(":memory:")
    supa = FakeSupa()
    telegram = FakeTelegram([
        [{"update_id": 3, "callback_query": {
            "id": "cq-3", "data": "autre_commande",
            "from": {"first_name": "X"},
        }}],
    ])
    await _run_worker(brain, supa, telegram)
    assert supa.calls == []
    assert any(t == "" for _, t in telegram.answered)


async def test_offset_advances_through_updates():
    """L'offset est incrémenté après chaque update traité."""
    brain = Brain(":memory:")
    supa = FakeSupa()
    telegram = FakeTelegram([
        [{"update_id": 10, "callback_query": {"id": "c1", "data": "contact:x", "from": {"first_name": "A"}}}],
        [{"update_id": 11, "callback_query": {"id": "c2", "data": "contact:y", "from": {"first_name": "B"}}}],
    ])
    await _run_worker(brain, supa, telegram)
    assert brain.get_telegram_offset() >= 12  # au moins 11 + 1
```

- [ ] **Step 2 : Lancer → échec**

```bash
python -m pytest tests/test_engine_telegram_bot.py -v
```
Expected : `ModuleNotFoundError: No module named 'engine.telegram_bot'`

- [ ] **Step 3 : Créer `engine/telegram_bot.py`**

```python
"""Polling des callback_query Telegram (bouton 🤝 Je m'en occupe).

Coroutine permanente lancée par server.py --auto si Telegram est configuré.
Lit les callback_query via getUpdates (long-poll 5s), gère les 'contact:{opp_id}',
insère le signal dans Supabase, répond avec un toast.
"""
from __future__ import annotations

import asyncio


async def telegram_poll_worker(
    brain, supa, telegram, stop_event,
    poll_pause: float = 3.0,
) -> None:
    """Boucle de polling des callback_query Telegram.

    best-effort : toute erreur est loguée sans arrêter la coroutine.
    poll_pause : secondes entre deux appels getUpdates (0 dans les tests).
    """
    while not stop_event.is_set():
        try:
            offset = brain.get_telegram_offset()
            updates = await telegram.get_updates(offset=offset)
            for u in updates:
                update_id = u.get("update_id", 0)
                brain.set_telegram_offset(update_id + 1)

                cq = u.get("callback_query")
                if not cq:
                    continue

                data = cq.get("data", "")
                cq_id = cq.get("id", "")

                if not data.startswith("contact:"):
                    await telegram.answer_callback(cq_id, "")
                    continue

                opp_id = data[len("contact:"):]
                first_name = (cq.get("from") or {}).get("first_name") or "Quelqu'un"

                try:
                    created = await supa.create_contact_from_telegram(opp_id, first_name)
                    text = "🤝 Enregistré !" if created else "⚠️ Quelqu'un s'en occupe déjà."
                except Exception as exc:
                    text = f"❌ Erreur ({type(exc).__name__})"
                    print(f"[telegram_bot] erreur création signal : {exc}")

                await telegram.answer_callback(cq_id, text)

        except Exception as exc:
            print(f"[telegram_bot] erreur polling : {exc}")

        if poll_pause:
            await asyncio.sleep(poll_pause)
```

- [ ] **Step 4 : Lancer → 4 tests PASS**

```bash
python -m pytest tests/test_engine_telegram_bot.py -v
```
Expected : 4 PASS.

- [ ] **Step 5 : Non-régression**

```bash
python -m pytest tests/ -q
```
Expected : tous les tests passent.

- [ ] **Step 6 : Commit**

```bash
git add engine/telegram_bot.py tests/test_engine_telegram_bot.py
git commit -m "feat(engine): telegram_poll_worker — callbacks Je m'en occupe"
```

---

## Task 6 : Intégration `server.py`

**Files:**
- Modify: `server.py`

- [ ] **Step 1 : Ajouter l'import**

Après `from engine.telegram import TelegramClient` :

```python
from engine.telegram_bot import telegram_poll_worker
```

- [ ] **Step 2 : Démarrer le worker dans `start_autonomous_engine`**

Localise le bloc `if telegram:` qui contient déjà `print("📨 Notifications Telegram activées.")`. Remplace-le par :

```python
    if telegram:
        print("📨 Notifications Telegram activées.")
        tasks.append(asyncio.create_task(
            telegram_poll_worker(brain, supa, telegram, stop_event)
        ))
        print("🤝 Polling callbacks Telegram démarré.")
    else:
        print("📨 Telegram non configuré — notifications désactivées.")
```

- [ ] **Step 3 : Non-régression**

```bash
python -m pytest tests/ -q
```
Expected : tous les tests passent.

- [ ] **Step 4 : Commit**

```bash
git add server.py
git commit -m "feat(server): démarrer telegram_poll_worker au boot --auto"
```

---

## Task 7 : Frontend — `js/lib/comments.js`

**Files:**
- Modify: `js/lib/comments.js`

> Convention : pas de tests frontend — validation manuelle sur `/item/:id`.

- [ ] **Step 1 : Étendre le SELECT** (ligne 6)

Remplacer :

```javascript
const SELECT = 'id, opportunity_id, user_id, body, edited_at, created_at, author:profiles(username, avatar_color)';
```

par :

```javascript
const SELECT = 'id, opportunity_id, user_id, body, edited_at, created_at, type, cancelled_at, author:profiles(username, avatar_color)';
```

- [ ] **Step 2 : Ajouter `createContactSignal` et `cancelContactSignal`**

À la fin du fichier, avant `subscribeComments`, ajouter :

```javascript
/** Crée un signal de contact via RPC (auteur = profil hub connecté). */
export async function createContactSignal(opportunityId) {
  const { data, error } = await supa.rpc('create_contact_signal', { p_opportunity_id: opportunityId });
  if (error) throw new Error(error.message);
  return data;
}

/** Annule un signal de contact via RPC (auteur ou admin). */
export async function cancelContactSignal(commentId) {
  const { error } = await supa.rpc('cancel_contact_signal', { p_comment_id: commentId });
  if (error) throw new Error(error.message);
}
```

- [ ] **Step 3 : Exclure les signaux de contact du count dans `loadCommentMeta`**

Dans la boucle `for (const row of data)`, ajouter un `continue` pour les contacts :

```javascript
  for (const row of data) {
    if (row.type === 'contact') continue;   // ← ajouter cette ligne
    const m = meta.get(row.opportunity_id) || { count: 0, participated: false, latest: null };
```

- [ ] **Step 4 : Vérifier (console F12)**

Serveur lancé, connecté, sur `/feed` :
```js
const m = await import('/js/lib/comments.js?v=' + Date.now());
console.log(typeof m.createContactSignal, typeof m.cancelContactSignal); // "function" "function"
```

- [ ] **Step 5 : Commit**

```bash
git add js/lib/comments.js
git commit -m "feat(comments): SELECT type+cancelled_at + RPCs contact + exclure contacts du count"
```

---

## Task 8 : Frontend — `js/components/comments.js` + `style.css`

**Files:**
- Modify: `js/components/comments.js`
- Modify: `style.css`

- [ ] **Step 1 : Ajouter les imports dans `comments.js`**

En haut, après `import { markSeen } from '../lib/comment-seen.js';` :

```javascript
import { createContactSignal, cancelContactSignal } from '../lib/comments.js';
```

- [ ] **Step 2 : Modifier le HTML initial dans `mountComments`**

Dans la chaîne `container.innerHTML = ...`, ajouter `<div id="cmContact"></div>` entre `#cmList` et `#cmForm` :

```javascript
  container.innerHTML = `
    <section class="cm-section">
      <h3 class="cm-title">💬 Commentaires <span id="cmCount" class="cm-count"></span></h3>
      <div id="cmList" class="cm-list"><div class="muted">Chargement…</div></div>
      <div id="cmContact"></div>
      <form id="cmForm" class="cm-form">
        <textarea id="cmInput" class="cm-input" rows="2" maxlength="2000"
          placeholder="Ajouter un commentaire…"></textarea>
        <button type="submit" class="btn-acc">Publier</button>
      </form>
    </section>`;
```

- [ ] **Step 3 : Ajouter la référence `contactEl` après les autres querySelector**

Après `const input = container.querySelector('#cmInput');` :

```javascript
  const contactEl = container.querySelector('#cmContact');
```

- [ ] **Step 4 : Modifier `renderList` pour le pin + le bouton**

Remplacer la fonction `renderList` existante par :

```javascript
  function renderList() {
    // Séparer : contact actif (pinnned) vs commentaires normaux
    const contact = comments.find(c => c.type === 'contact' && !c.cancelled_at);
    const regular = comments.filter(c => !(c.type === 'contact' && !c.cancelled_at));

    // Rendu du pin contact
    if (contact) {
      contactEl.innerHTML = `
        <div class="cm-contact-pin" data-id="${contact.id}">
          <span class="cm-contact-icon">🤝</span>
          <div class="cm-body">
            <span class="cm-contact-text">${esc(contact.body)}</span>
            <span class="cm-time"> · ${timeAgo(contact.created_at)}</span>
          </div>
          ${(contact.user_id === me?.id || isAdmin)
            ? `<button class="cm-link cm-cancel-contact" data-cancel-contact="${contact.id}">✋ Annuler</button>`
            : ''}
        </div>`;
    } else {
      contactEl.innerHTML = `<button id="cmContactBtn" class="btn-contact">🤝 Je contacte cette annonce</button>`;
    }

    // Rendu du fil normal (sans les contacts annulés non plus)
    const visible = regular.filter(c => c.type === 'comment');
    if (!visible.length) {
      listEl.innerHTML = `<div class="cm-empty muted">Aucun commentaire. Soyez le premier !</div>`;
    } else {
      listEl.innerHTML = visible.map(rowHtml).join('');
    }
    countEl.textContent = visible.length ? `(${visible.length})` : '';

    // Marque le dernier commentaire visible
    const allSorted = [...comments].filter(c => c.type === 'comment');
    if (allSorted.length) markSeen(opportunityId, allSorted[allSorted.length - 1].created_at);
  }
```

- [ ] **Step 5 : Ajouter la gestion du clic « Annuler » dans `listEl.addEventListener`**

Dans le handler de clics délégués (la fonction `listEl.addEventListener('click', async e => {...})`), ajouter avant `if (delBtn)` :

```javascript
    const cancelContactBtn = e.target.closest('[data-cancel-contact]');
    if (cancelContactBtn) {
      try {
        await cancelContactSignal(cancelContactBtn.dataset.cancelContact);
        await reload();
      } catch (err) { alert(err.message); }
      return;
    }
```

- [ ] **Step 6 : Ajouter la gestion du clic « Je contacte » via délégation sur `container`**

Après le listener sur `form` (après `form.addEventListener('submit', ...)`), ajouter :

```javascript
  // Délégation pour le bouton dynamique "Je contacte"
  contactEl.addEventListener('click', async e => {
    if (e.target.id !== 'cmContactBtn') return;
    e.target.disabled = true;
    try {
      await createContactSignal(opportunityId);
      await reload();
    } catch (err) {
      alert(err.message);
      e.target.disabled = false;
    }
  });
```

- [ ] **Step 7 : Ajouter les styles CSS** (append à la fin de `style.css`)

```css
/* ===== Signal « Je contacte » ===== */
.cm-contact-pin {
  display: flex; align-items: center; gap: 10px;
  background: rgba(99,102,241,.15); border: 1px solid rgba(99,102,241,.3);
  border-radius: 10px; padding: 10px 14px; margin-bottom: 10px;
}
.cm-contact-icon { font-size: 1.3rem; flex-shrink: 0; }
.cm-contact-text { font-weight: 600; }
.cm-cancel-contact { margin-left: auto; opacity: .5; font-size: .8rem; white-space: nowrap; }
.btn-contact {
  width: 100%; margin-top: 8px; padding: 9px; border-radius: 8px;
  font-size: .9rem; background: rgba(99,102,241,.2);
  border: 1px solid rgba(99,102,241,.3); color: inherit; cursor: pointer;
  transition: background .15s;
}
.btn-contact:hover:not(:disabled) { background: rgba(99,102,241,.35); }
.btn-contact:disabled { opacity: .4; cursor: not-allowed; }
```

- [ ] **Step 8 : Valider manuellement sur `/item/:id`**

Serveur lancé, connecté, sur une page `/item/:id` :
1. Le bouton **🤝 Je contacte cette annonce** apparaît sous la zone de commentaire
2. Clic → pin `🤝 <pseudo> s'en occupe` apparaît en haut du fil, bouton disparaît
3. Autre onglet (autre compte) → bouton grisé (épuisé avant reload si session différente, sinon test depuis téléphone)
4. Bouton **✋ Annuler** visible pour l'auteur → clic → pin disparaît, bouton revient
5. Console F12 propre

- [ ] **Step 9 : Non-régression backend**

```bash
python -m pytest tests/ -q
```
Expected : tous les tests passent.

- [ ] **Step 10 : Commit**

```bash
git add js/components/comments.js js/lib/comments.js style.css
git commit -m "feat(frontend): signal Je contacte — pin + bouton + annulation"
```

---

## Validation finale E2E

1. **Hub** : `/item/:id` → bouton 🤝 → pin → annulation → OK
2. **Telegram** : lancer `python server.py --auto` (avec `.env` configuré) → une opportunité 🔴 → appuyer sur le bouton Telegram → toast "🤝 Enregistré !" → pin visible sur le hub en temps réel
3. **Exclusivité** : un 2ᵉ appui depuis Telegram → toast "⚠️ Quelqu'un s'en occupe déjà."
4. **Suite tests** : `python -m pytest tests/ -q` → PASS complet

---

## Self-Review

**Couverture spec :**
- Migration SQL (type + cancelled_at + index unique + RPCs) → Task 1 ✅
- Brain offset (get/set telegram_poll_offset) → Task 2 ✅
- `Supa.create_contact_from_telegram` (201→True, 409→False) → Task 3 ✅
- `TelegramClient.get_updates` + `answer_callback` → Task 4 ✅
- Bouton inline `reply_markup` dans `send_opportunity` → Task 4 ✅
- `telegram_poll_worker` (callback → create → answer) → Task 5 ✅
- `server.py` démarre le worker si Telegram configuré → Task 6 ✅
- `js/lib/comments.js` SELECT + RPCs + exclure contacts du count → Task 7 ✅
- `js/components/comments.js` pin + bouton + cancel → Task 8 ✅
- CSS styles → Task 8 ✅

**Types cohérents :**
- `get_telegram_offset() -> int` / `set_telegram_offset(int)` → Task 2, utilisés Task 5 ✅
- `create_contact_from_telegram(opp_id, first_name) -> bool` → Task 3, appelé Task 5 ✅
- `telegram.get_updates(offset) -> list` / `telegram.answer_callback(id, text)` → Task 4, utilisés Task 5 ✅
- `createContactSignal(opportunityId)` / `cancelContactSignal(commentId)` → Task 7, importés Task 8 ✅
- `contact.user_id` (peut être None pour contacts Telegram) → rendu adapté Task 8 ✅
