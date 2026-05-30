from engine.supa import merge_enrichment


def base_payload():
    return {
        "ad_id": "1", "title": "PS5", "price": 200.0, "url": "u", "image_url": "img",
        "category": None, "resale_score": None, "est_margin_eur": None, "status": "active",
    }


def test_merge_sets_ai_fields():
    ia = {"category": "urgent", "resale_score": 90.0, "est_market_price": 350.0,
          "est_margin_eur": 150.0, "est_margin_pct": 75.0, "max_buy_price": 290.0,
          "is_lot": False, "signals": ["x"], "explanation": "ok", "model_used": "m"}
    out = merge_enrichment(base_payload(), ia)
    assert out["category"] == "urgent"
    assert out["resale_score"] == 90.0
    assert out["est_margin_eur"] == 150.0
    assert out["model_used"] == "m"
    # champs de base préservés
    assert out["ad_id"] == "1" and out["title"] == "PS5"


def test_merge_serializes_signals_to_json_compatible():
    ia = {"category": "interesting", "signals": ["a", "b"]}
    out = merge_enrichment(base_payload(), ia)
    assert out["signals"] == ["a", "b"]


def test_merge_ignores_unknown_keys():
    ia = {"category": "passable", "dig_deeper": True, "reason": "x"}  # pas des colonnes
    out = merge_enrichment(base_payload(), ia)
    assert "dig_deeper" not in out
    assert "reason" not in out
