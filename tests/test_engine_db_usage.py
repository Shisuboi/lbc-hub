"""Test llm_usage table et quota_day helper."""
from engine.db import Brain, quota_day


def test_quota_day_is_pacific_offset_string():
    # 2026-05-30 03:00 UTC → encore le 29 en Pacifique (UTC-8)
    assert quota_day(1748574000) == quota_day(1748574000)  # déterministe
    assert isinstance(quota_day(1748574000), str)
    assert len(quota_day(1748574000)) == 10  # YYYY-MM-DD


def test_inc_and_count_usage():
    b = Brain(":memory:")
    day = "2026-05-30"
    assert b.usage_count("gemini", "flash-lite", day) == 0
    b.inc_usage("gemini", "flash-lite", day, tokens=120)
    b.inc_usage("gemini", "flash-lite", day, tokens=80)
    assert b.usage_count("gemini", "flash-lite", day) == 2


def test_usage_count_isolated_per_model_and_day():
    b = Brain(":memory:")
    b.inc_usage("gemini", "flash-lite", "2026-05-30", tokens=10)
    assert b.usage_count("gemini", "pro", "2026-05-30") == 0
    assert b.usage_count("gemini", "flash-lite", "2026-05-31") == 0
