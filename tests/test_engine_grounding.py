# tests/test_engine_grounding.py
from engine.db import Brain
from engine.grounding import market_grounding


def test_grounding_empty_category_returns_none_median():
    brain = Brain(":memory:")
    g = market_grounding(brain, "consoles_jeux_video")
    assert g["sample_size"] == 0
    assert g["median_price"] is None


def test_grounding_computes_median_and_sample():
    brain = Brain(":memory:")
    for p in (100.0, 200.0, 300.0):
        brain.record_market_obs("consoles_jeux_video", p, "Paris", now=1000)
    g = market_grounding(brain, "consoles_jeux_video")
    assert g["sample_size"] == 3
    assert g["median_price"] == 200.0


def test_grounding_even_sample_averages_two_middles():
    brain = Brain(":memory:")
    for p in (100.0, 200.0, 300.0, 500.0):
        brain.record_market_obs("velos", p, None, now=1000)
    g = market_grounding(brain, "velos")
    assert g["median_price"] == 250.0


def test_grounding_unknown_category_isolated():
    brain = Brain(":memory:")
    brain.record_market_obs("velos", 100.0, None, now=1000)
    assert market_grounding(brain, "informatique")["sample_size"] == 0
