import pytest
from aiohttp import web, ClientSession
from engine.supa import Supa
from engine.maintenance import purge_old_opportunities, run_maintenance


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_app(favorites: list, n_deleted: int) -> tuple[web.Application, dict]:
    """Crée une app aiohttp qui simule PostgREST pour la purge."""
    captured = {}

    async def get_favs(request):
        return web.json_response(favorites)

    async def delete_opps(request):
        captured["params"] = dict(request.query)
        return web.Response(
            status=204,
            headers={"Content-Range": f"*/{n_deleted}"},
        )

    app = web.Application()
    app.router.add_get("/rest/v1/item_favorites", get_favs)
    app.router.add_delete("/rest/v1/opportunities", delete_opps)
    return app, captured


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_purge_no_favorites(aiohttp_server):
    """0 favori → DELETE sans filtre id=not.in., retourne le nombre supprimé."""
    app, captured = _make_app(favorites=[], n_deleted=3)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        supa = Supa(str(server.make_url("")), "fake-key", session)
        n = await purge_old_opportunities(supa, days=30)
    assert n == 3
    assert "id" not in captured.get("params", {}), "ne doit pas avoir de filtre not.in. sans favori"


async def test_purge_with_favorites(aiohttp_server):
    """Avec favoris → DELETE exclut leurs IDs via id=not.in.(…)."""
    favs = [{"opportunity_id": "aaa"}, {"opportunity_id": "bbb"}]
    app, captured = _make_app(favorites=favs, n_deleted=7)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        supa = Supa(str(server.make_url("")), "fake-key", session)
        n = await purge_old_opportunities(supa, days=30)
    assert n == 7
    id_param = captured.get("params", {}).get("id", "")
    assert "not.in." in id_param
    assert "aaa" in id_param
    assert "bbb" in id_param


async def test_purge_nothing_to_delete(aiohttp_server):
    """0 ligne à supprimer → retourne 0 sans erreur."""
    app, captured = _make_app(favorites=[], n_deleted=0)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        supa = Supa(str(server.make_url("")), "fake-key", session)
        n = await purge_old_opportunities(supa, days=30)
    assert n == 0


async def test_run_maintenance_resilient(aiohttp_server, monkeypatch):
    """run_maintenance absorbe les exceptions : ne lève jamais, logue l'erreur."""
    async def _fail(supa, days):
        raise RuntimeError("réseau mort")
    monkeypatch.setattr("engine.maintenance.purge_old_opportunities", _fail)

    app, _ = _make_app(favorites=[], n_deleted=0)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        supa = Supa(str(server.make_url("")), "fake-key", session)
        # Ne doit PAS lever
        await run_maintenance(supa, cfg={})
