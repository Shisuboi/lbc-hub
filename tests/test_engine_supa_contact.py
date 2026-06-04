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
