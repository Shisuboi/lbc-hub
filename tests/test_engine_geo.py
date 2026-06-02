import pytest
from aiohttp import web, ClientSession
from engine.db import Brain
from engine.geo import geocode_city, fill_latlon


@pytest.fixture
async def mock_ban(aiohttp_server):
    async def search(request):
        q = (request.query.get("q") or "").lower()
        if "bordeaux" in q:
            return web.json_response({"features": [
                {"geometry": {"coordinates": [-0.5792, 44.8378]},
                 "properties": {"label": "Bordeaux"}}
            ]})
        return web.json_response({"features": []})
    app = web.Application()
    app.router.add_get("/search/", search)
    return await aiohttp_server(app)


async def test_geocode_city_success(mock_ban, monkeypatch):
    monkeypatch.setattr("engine.geo.BAN_URL", str(mock_ban.make_url("/search/")))
    async with ClientSession() as s:
        geo = await geocode_city(s, "Bordeaux")
    assert geo is not None
    lat, lon = geo
    assert round(lat, 2) == 44.84 and round(lon, 2) == -0.58


async def test_geocode_city_unknown_returns_none(mock_ban, monkeypatch):
    monkeypatch.setattr("engine.geo.BAN_URL", str(mock_ban.make_url("/search/")))
    async with ClientSession() as s:
        assert await geocode_city(s, "Zzzville") is None


async def test_geocode_city_empty_returns_none():
    assert await geocode_city(None, "") is None  # pas d'appel réseau si ville vide


async def test_fill_latlon_uses_cache(monkeypatch):
    b = Brain(":memory:")
    b.set_city_geo("Lyon", 45.75, 4.85)
    called = {"n": 0}
    async def fake_geocode(session, city):
        called["n"] += 1
        return (0.0, 0.0)
    monkeypatch.setattr("engine.geo.geocode_city", fake_geocode)
    payload = {"location_city": "Lyon"}
    await fill_latlon(b, None, payload)
    assert payload["lat"] == 45.75 and payload["lon"] == 4.85
    assert called["n"] == 0  # cache hit → aucun appel réseau


async def test_fill_latlon_geocodes_and_caches(monkeypatch):
    b = Brain(":memory:")
    async def fake_geocode(session, city):
        return (48.85, 2.35)
    monkeypatch.setattr("engine.geo.geocode_city", fake_geocode)
    payload = {"location_city": "Paris"}
    await fill_latlon(b, None, payload)
    assert payload["lat"] == 48.85 and payload["lon"] == 2.35
    assert b.get_city_geo("Paris") == (48.85, 2.35)  # mis en cache


async def test_fill_latlon_no_city_is_noop():
    b = Brain(":memory:")
    payload = {}
    await fill_latlon(b, None, payload)
    assert "lat" not in payload and "lon" not in payload


async def test_fill_latlon_geocode_fail_leaves_payload_untouched(monkeypatch):
    b = Brain(":memory:")
    async def fake_geocode(session, city):
        return None
    monkeypatch.setattr("engine.geo.geocode_city", fake_geocode)
    payload = {"location_city": "Inconnue"}
    await fill_latlon(b, None, payload)
    assert "lat" not in payload  # échec géocodage → best-effort, rien ajouté
