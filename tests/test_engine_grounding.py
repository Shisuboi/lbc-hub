# tests/test_engine_grounding.py
from engine.db import Brain
from engine.grounding import market_grounding, is_grounding_confident


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


# ── Confiance du grounding (gate 🔴) : niveau 'model' ET distribution resserrée ──

def test_model_grounding_exposes_dispersion():
    brain = Brain(":memory:")
    for p in (290, 300, 300, 300, 310, 300):
        brain.record_market_obs("ordinateurs", float(p), "Paris", model_name="MacBook Air M1")
    g = market_grounding(brain, "ordinateurs", model_name="MacBook Air M1")
    assert g["grounding_level"] == "model"
    assert g["price_dispersion"] is not None and g["price_dispersion"] < 0.2  # resserré


def test_tight_model_grounding_is_confident():
    brain = Brain(":memory:")
    for p in (480, 500, 500, 520, 510, 490):
        brain.record_market_obs("ordinateurs", float(p), "Paris", model_name="MacBook Air M1")
    assert is_grounding_confident(market_grounding(brain, "ordinateurs", model_name="MacBook Air M1"))


def test_wide_model_grounding_not_confident():
    """Libellé trop large mélangeant des générations (Intel 2015 + M1/M2/M3) → IQR/médiane élevé → pas 🔴."""
    brain = Brain(":memory:")
    for p in (40, 120, 200, 250, 300, 400, 560, 750, 850, 3490):
        brain.record_market_obs("ordinateurs", float(p), "Paris", model_name="MacBook Air 13")
    g = market_grounding(brain, "ordinateurs", model_name="MacBook Air 13")
    assert g["grounding_level"] == "model"
    assert g["price_dispersion"] > 0.6
    assert is_grounding_confident(g) is False


def test_category_grounding_never_confident():
    brain = Brain(":memory:")
    for p in (100, 200, 300, 400, 500, 600):
        brain.record_market_obs("ordinateurs", float(p), "Paris")  # pas de model_name
    g = market_grounding(brain, "ordinateurs")
    assert g["grounding_level"] == "category"
    assert is_grounding_confident(g) is False


def test_empty_grounding_not_confident():
    assert is_grounding_confident({"median_price": None, "sample_size": 0}) is False
