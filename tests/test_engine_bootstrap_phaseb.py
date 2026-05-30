import asyncio
from engine.db import Brain
from engine.bootstrap import build_searches_lookup


async def test_build_searches_lookup_maps_thresholds():
    class FakeSupa:
        async def fetch_active_searches(self):
            return [
                {"id": "s1", "min_margin_eur": 50, "min_margin_pct": 40, "source_url": "u"},
                {"id": "s2", "min_margin_eur": None, "min_margin_pct": None, "source_url": "u2"},
            ]

    lookup = await build_searches_lookup(FakeSupa(), defaults={"min_margin_eur": 30, "min_margin_pct": 30})
    assert lookup["s1"]["min_margin_eur"] == 50
    assert lookup["s1"]["min_margin_pct"] == 40
    # défauts appliqués quand null
    assert lookup["s2"]["min_margin_eur"] == 30
    assert lookup["s2"]["min_margin_pct"] == 30
