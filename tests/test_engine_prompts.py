# tests/test_engine_prompts.py
from engine.prompts import (
    TRIAGE_SCHEMA, VERIFY_SCHEMA, PHOTO_SCHEMA,
    build_triage_prompt, build_verify_prompt, build_photo_prompt,
)


def test_triage_schema_excludes_urgent():
    cat_enum = TRIAGE_SCHEMA["properties"]["items"]["items"]["properties"]["category"]["enum"]
    assert "urgent" not in cat_enum
    assert set(cat_enum) == {"interesting", "passable"}


def test_build_triage_prompt_lists_all_ads_and_grounding():
    ads = [
        {"ad_id": "1", "title": "PS5 Slim", "price": 250.0, "city": "Paris"},
        {"ad_id": "2", "title": "PC portable", "price": 1200.0, "city": "Lyon"},
    ]
    grounding = {"median_price": 300.0, "sample_size": 12}
    prompt = build_triage_prompt(ads, grounding)
    assert "PS5 Slim" in prompt and "PC portable" in prompt
    assert "300" in prompt  # médiane injectée
    assert "urgent" not in prompt.lower() or "jamais" in prompt.lower()


def test_build_verify_prompt_includes_price_and_grounding():
    ad = {"title": "PS5 Slim", "price": 250.0, "city": "Paris", "category": "consoles_jeux_video"}
    grounding = {"median_price": 380.0, "sample_size": 8}
    prompt = build_verify_prompt(ad, grounding)
    assert "250" in prompt and "380" in prompt


def test_build_photo_prompt_mentions_arnaque():
    prompt = build_photo_prompt({"title": "PS5 Slim"})
    assert "arnaque" in prompt.lower() or "état" in prompt.lower()


def test_verify_schema_has_market_price_field():
    assert "est_market_price" in VERIFY_SCHEMA["properties"]
    assert "refined_score" in VERIFY_SCHEMA["properties"]
