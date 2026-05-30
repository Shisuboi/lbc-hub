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
