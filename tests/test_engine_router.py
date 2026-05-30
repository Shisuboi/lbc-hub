import pytest
from engine.db import Brain
from engine.router import LLMRouter, QuotaExhausted, TIER_RANKS


class FakeProvider:
    name = "gemini"

    def __init__(self):
        self.calls = []

    async def generate_json(self, model_id, prompt, schema, image_bytes=None):
        self.calls.append(model_id)
        return ({"ok": True, "model": model_id}, 100)  # (data, tokens)


def make_router(provider, settings=None, brain=None):
    settings = settings or {
        "triage_model": "gemini-3.1-flash-lite",
        "verify_model": "gemini-3.1-flash-lite",
        "photo_model": "gemini-3.1-flash-lite",
        "pro_model": "gemini-3.1-pro-preview",
        "pro_enabled": False,
        "min_tier_for_urgent": "pro",
    }
    return LLMRouter(provider, settings, brain or Brain(":memory:"))


async def test_route_triage_uses_flash_lite():
    p = FakeProvider()
    r = make_router(p)
    data, model_id, tier = await r.generate("triage", "prompt", {"x": 1})
    assert data["ok"] is True
    assert model_id == "gemini-3.1-flash-lite"
    assert tier == TIER_RANKS["flash-lite"]


async def test_verify_uses_flash_when_pro_disabled():
    p = FakeProvider()
    r = make_router(p)
    _, model_id, tier = await r.generate("verify", "prompt", {"x": 1})
    assert model_id == "gemini-3.1-flash-lite"
    assert tier == TIER_RANKS["flash-lite"]  # < pro → pas de 🔴 possible


async def test_verify_prefers_pro_when_enabled():
    p = FakeProvider()
    settings = {
        "triage_model": "gemini-3.1-flash-lite", "verify_model": "gemini-3.5-flash",
        "photo_model": "gemini-3.1-flash-lite", "pro_model": "gemini-3.1-pro-preview",
        "pro_enabled": True, "min_tier_for_urgent": "pro",
    }
    r = make_router(p, settings)
    _, model_id, tier = await r.generate("verify", "prompt", {"x": 1})
    assert model_id == "gemini-3.1-pro-preview"
    assert tier == TIER_RANKS["pro"]


async def test_usage_is_counted():
    p = FakeProvider()
    brain = Brain(":memory:")
    r = make_router(p, brain=brain)
    await r.generate("triage", "prompt", {"x": 1})
    await r.generate("triage", "prompt", {"x": 1})
    from engine.db import quota_day
    assert brain.usage_count("gemini", "gemini-3.1-flash-lite", quota_day()) == 2


async def test_quota_exhausted_raises_when_cap_reached():
    p = FakeProvider()
    brain = Brain(":memory:")
    # cap artificiel via settings: 1 req/jour pour le modèle de triage
    r = make_router(p, brain=brain)
    r.caps["gemini-3.1-flash-lite"] = 1
    await r.generate("triage", "prompt", {"x": 1})  # ok (1/1)
    with pytest.raises(QuotaExhausted):
        await r.generate("triage", "prompt", {"x": 1})  # dépasse


def test_min_tier_rank_helper():
    p = FakeProvider()
    r = make_router(p)
    assert r.min_urgent_rank == TIER_RANKS["pro"]
