"""Tests pour les endpoints HTTP de server.py.

Ces tests utilisent la factory `server.create_app()` (sans `await`) afin
que le harness pytest-aiohttp puisse instancier le serveur dans son propre
event loop.
"""
import pytest

import server


@pytest.fixture
async def client(aiohttp_client):
    app = server.create_app()
    return await aiohttp_client(app)


# === /api/ping ===

async def test_ping_returns_ok(client):
    resp = await client.get('/api/ping')
    assert resp.status == 200
    data = await resp.json()
    assert data == {'status': 'ok'}


# === CORS / Private Network Access ===

async def test_cors_headers_on_get(client):
    resp = await client.get('/api/ping')
    assert resp.headers.get('Access-Control-Allow-Origin') == '*'
    assert resp.headers.get('Access-Control-Allow-Private-Network') == 'true'


async def test_cors_preflight_options(client):
    resp = await client.options('/api/ping', headers={
        'Origin': 'https://shisuboi.github.io',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Private-Network': 'true',
    })
    assert resp.status in (200, 204)
    assert resp.headers.get('Access-Control-Allow-Origin') == '*'
    assert resp.headers.get('Access-Control-Allow-Private-Network') == 'true'
    assert 'GET' in resp.headers.get('Access-Control-Allow-Methods', '')
