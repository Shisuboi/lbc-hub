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
