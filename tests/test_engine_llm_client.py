import json
import pytest
from aiohttp import web, ClientSession
from engine.llm_client import GeminiClient


@pytest.fixture
async def mock_gemini(aiohttp_server):
    captured = {"bodies": [], "paths": []}

    async def generate(request):
        captured["paths"].append(request.path)
        captured["bodies"].append(await request.json())
        payload = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"refined_score": 88})}]}}],
            "usageMetadata": {"totalTokenCount": 142},
        }
        return web.json_response(payload)

    app = web.Application()
    app.router.add_post("/v1beta/models/{model}:generateContent", generate)
    server = await aiohttp_server(app)
    server.captured = captured
    return server


async def test_generate_json_parses_structured_output(mock_gemini):
    base = str(mock_gemini.make_url("")).rstrip("/")
    async with ClientSession() as session:
        client = GeminiClient("test-key", session, base_url=base)
        data, tokens = await client.generate_json(
            "gemini-3.1-flash-lite", "prompt", {"type": "object"}
        )
    assert data["refined_score"] == 88
    assert tokens == 142
    # le schéma et le prompt sont bien envoyés
    body = mock_gemini.captured["bodies"][-1]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["contents"][0]["parts"][0]["text"] == "prompt"


async def test_generate_json_includes_image_inline(mock_gemini):
    base = str(mock_gemini.make_url("")).rstrip("/")
    async with ClientSession() as session:
        client = GeminiClient("test-key", session, base_url=base)
        await client.generate_json(
            "gemini-3.1-flash-lite", "prompt", {"type": "object"}, image_bytes=b"\xff\xd8\xff"
        )
    parts = mock_gemini.captured["bodies"][-1]["contents"][0]["parts"]
    assert any("inline_data" in p for p in parts)


