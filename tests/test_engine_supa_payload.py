from engine.supa import build_opportunity_payload


def sample_ad():
    return {
        "ad_id": "2912345678",
        "title": "PS5 Slim",
        "price": 250.0,
        "url": "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678",
        "city": "Bordeaux",
        "image_url": "https://img.leboncoin.fr/x.jpg",
    }


def sample_search():
    return {"id": "search-uuid", "platform": "leboncoin"}


def test_payload_core_fields():
    p = build_opportunity_payload(sample_ad(), sample_search(), event="new", scraped_at_iso="2026-05-29T10:00:00Z")
    assert p["ad_id"] == "2912345678"
    assert p["title"] == "PS5 Slim"
    assert p["price"] == 250.0
    assert p["url"].endswith("2912345678")
    assert p["source_search_id"] == "search-uuid"
    assert p["platform"] == "leboncoin"
    assert p["location_city"] == "Bordeaux"
    assert p["image_url"].endswith("x.jpg")
    assert p["status"] == "active"
    assert p["scraped_at"] == "2026-05-29T10:00:00Z"


def test_payload_new_event_not_price_dropped():
    p = build_opportunity_payload(sample_ad(), sample_search(), event="new", scraped_at_iso="t", previous_price=None)
    assert p["price_dropped"] is False
    assert p["previous_price"] is None


def test_payload_price_drop_event():
    p = build_opportunity_payload(sample_ad(), sample_search(), event="price_drop", scraped_at_iso="t", previous_price=300.0)
    assert p["price_dropped"] is True
    assert p["previous_price"] == 300.0


def test_payload_ai_fields_are_null():
    p = build_opportunity_payload(sample_ad(), sample_search(), event="new", scraped_at_iso="t")
    assert p["category"] is None
    assert p["resale_score"] is None
    assert p["est_margin_eur"] is None
