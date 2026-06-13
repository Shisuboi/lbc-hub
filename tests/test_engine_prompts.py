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


def test_triage_prompt_flags_implausibly_low_price_and_for_parts():
    """Un prix dérisoire (PC à 8€) doit être traité comme cassé/pièces, pas comme une affaire."""
    ads = [{"ad_id": "1", "title": "PC portable", "price": 8.0, "city": "Paris"}]
    prompt = build_triage_prompt(ads, {})  # médiane marché INCONNUE
    low = prompt.lower()
    assert ("piège" in low) or ("arnaque" in low)              # warning prix dérisoire
    assert ("illusoire" in low) or ("dérisoire" in low)       # marge illusoire / prix dérisoire
    assert ("pour pièces" in low) or ("pour pieces" in low)   # mots-clés pièces


def test_triage_prompt_has_score_scale():
    prompt = build_triage_prompt([{"ad_id": "1", "title": "x", "price": 10.0, "city": "P"}], {})
    assert "85" in prompt  # échelle de score ancrée


def test_verify_prompt_uses_product_knowledge_when_grounding_unknown():
    ad = {"title": "PC portable", "price": 8.0, "city": "Paris", "category": "informatique"}
    prompt = build_verify_prompt(ad, {})  # médiane INCONNUE
    low = prompt.lower()
    assert "connaiss" in low                              # estimer via connaissances produit
    assert ("illusoire" in low) or ("dérisoire" in low) or ("pièces" in low)


def test_verify_prompt_prioritizes_price_perf_over_aesthetics():
    """Le barème doit valoriser le prix/perf et NE PLUS plafonner sur l'état esthétique."""
    ad = {"title": "HP Envy i7", "price": 100.0, "city": "Bordeaux", "category": "informatique"}
    prompt = build_verify_prompt(ad, {"median_price": 210.0, "sample_size": 8})
    low = prompt.lower()
    # l'ancien plafond dur sur le moindre doute a disparu
    assert "ne peut pas dépasser 79" not in low
    # priorité explicite prix/perf, état esthétique minoré, pas de double peine
    assert "prix/perf" in low
    assert "esthétique" in low
    assert "deux fois" in low
    # seuls les vrais red flags plafonnent bas (anti-arnaque préservé)
    assert "red flag" in low


