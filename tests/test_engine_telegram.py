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
    assert "📍" not in msg
    assert "📈" not in msg


def test_format_opportunity_zero_margin_omitted():
    opp = {"title": "Item", "price": 10, "est_margin_eur": 0, "id": "x"}
    msg = _format_opportunity(opp)
    assert "📈" not in msg


async def test_send_opportunity_posts_to_group(aiohttp_server, monkeypatch):
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("/")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "GROUP123", "TRISTAN456", session)
        await send_opportunity(client, {"title": "T", "price": 10, "id": "x1", "url": "https://lbc.fr/ad/1"})
    assert captured["body"]["chat_id"] == "GROUP123"
    assert "🔴" in captured["body"]["text"]
    assert captured["body"]["parse_mode"] == "Markdown"


async def test_send_alert_posts_to_tristan(aiohttp_server, monkeypatch):
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("/")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "GROUP123", "TRISTAN456", session)
        await send_alert(client, "⚠️ Captcha détecté")
    assert captured["body"]["chat_id"] == "TRISTAN456"
    assert "Captcha" in captured["body"]["text"]


async def test_send_opportunity_absorbs_http_error(aiohttp_server, monkeypatch):
    """Erreur HTTP 500 → pas d'exception levée (best-effort)."""
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured, status=500))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("/")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "G", "T", session)
        await send_opportunity(client, {"title": "X", "id": "y"})  # ne doit PAS lever


async def test_send_alert_absorbs_network_error(monkeypatch):
    """Erreur réseau → pas d'exception levée (best-effort)."""
    monkeypatch.setattr(tg_mod, "TG_API", "http://localhost:1/bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "G", "T", session)
        await send_alert(client, "test")  # ne doit PAS lever


async def test_send_opportunity_includes_reply_markup_when_id_present(aiohttp_server, monkeypatch):
    """send_opportunity avec opp['id'] → reply_markup avec bouton 🤝."""
    import json as _json
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("/")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "GROUP", "TRISTAN", session)
        await send_opportunity(client, {"title": "T", "price": 10, "id": "uuid-abc", "url": "https://lbc.fr/ad/1"})
    markup = captured["body"].get("reply_markup")
    assert markup is not None
    parsed = _json.loads(markup) if isinstance(markup, str) else markup
    btn = parsed["inline_keyboard"][0][0]
    assert "occupe" in btn["text"]
    assert "uuid-abc" in btn["callback_data"]


async def test_send_opportunity_no_markup_without_id(aiohttp_server, monkeypatch):
    """send_opportunity sans id → pas de reply_markup."""
    captured = {}
    server = await aiohttp_server(_make_tg_app(captured))
    monkeypatch.setattr(tg_mod, "TG_API", str(server.make_url("/")) + "bot{token}/sendMessage")
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "G", "T", session)
        await send_opportunity(client, {"title": "T"})  # pas d'id
    assert "reply_markup" not in captured.get("body", {})


async def test_answer_callback_posts_to_answer_api(aiohttp_server, monkeypatch):
    """answer_callback → POST à TG_ANSWER_API avec callback_query_id et text."""
    captured = {}
    async def answer_handler(request):
        captured["body"] = await request.json()
        return web.json_response({"ok": True})
    app = web.Application()
    app.router.add_post("/bot{token}/answerCallbackQuery", answer_handler)
    server = await aiohttp_server(app)
    monkeypatch.setattr(tg_mod, "TG_ANSWER_API", str(server.make_url("/")) + "bot{token}/answerCallbackQuery")
    from engine.telegram import answer_callback
    async with ClientSession() as session:
        client = TelegramClient("TOKEN", "G", "T", session)
        await answer_callback(client, "cq-42", "🤝 Enregistré !")
    assert captured["body"]["callback_query_id"] == "cq-42"
    assert "Enregistré" in captured["body"]["text"]
