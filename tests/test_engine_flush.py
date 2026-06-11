import pytest
from aiohttp import web, ClientSession
from engine.db import Brain
from engine.supa import Supa


def test_flush_seen_ads_empties_and_counts():
    b = Brain(":memory:")
    b.upsert_ad("a1", 100.0)
    b.upsert_ad("a2", 200.0)
    assert b.flush_seen_ads() == 2
    # après flush : une annonce re-vue est de nouveau "new" (plus "seen")
    assert b.upsert_ad("a1", 100.0) == "new"


def test_flush_seen_ads_empty_returns_zero():
    b = Brain(":memory:")
    assert b.flush_seen_ads() == 0


async def test_delete_all_opportunities_returns_count(aiohttp_server):
    captured = {}

    async def delete_opps(request):
        captured["params"] = dict(request.query)
        return web.Response(status=204, headers={"Content-Range": "*/37"})

    app = web.Application()
    app.router.add_delete("/rest/v1/opportunities", delete_opps)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        supa = Supa(str(server.make_url("")), "k", session)
        n = await supa.delete_all_opportunities()
    assert n == 37
    assert captured["params"].get("id") == "not.is.null"  # filtre "tout"
