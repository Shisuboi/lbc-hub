"""Tests pour la configuration IA (engine/config.py)."""
from engine.config import ai_settings


def test_ai_settings_defaults():
    s = ai_settings({})
    assert s["triage_model"] == "gemini-3.1-flash-lite"
    assert s["photo_model"] == "gemini-3.1-flash-lite"
    assert s["min_tier_for_urgent"] == "pro"   # Pro = seul juge du 🔴 (B-04)
    assert s["pro_enabled"] is False            # Pro suspendu par défaut
    assert s["urgent_score_threshold"] == 75.0
    assert s["default_min_margin_eur"] == 30.0
    assert s["default_min_margin_pct"] == 30.0
    assert s["api_key"] is None


def test_ai_settings_pro_enabled_when_key_and_flag():
    s = ai_settings({
        "GEMINI_API_KEY": "k",
        "GEMINI_PRO_ENABLED": "true",
        "GEMINI_VERIFY_MODEL": "gemini-3.1-pro-preview",
    })
    assert s["api_key"] == "k"
    assert s["pro_enabled"] is True
    assert s["verify_model"] == "gemini-3.1-pro-preview"


def test_ai_settings_overrides_thresholds():
    s = ai_settings({"URGENT_SCORE_THRESHOLD": "80", "DEFAULT_MIN_MARGIN_EUR": "50"})
    assert s["urgent_score_threshold"] == 80.0
    assert s["default_min_margin_eur"] == 50.0
