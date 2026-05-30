from engine.prefilter import passes_prefilter


def ad(title="PS5 occasion", price=200.0):
    return {"ad_id": "1", "title": title, "price": price, "url": "u", "city": "Paris", "image_url": None}


def test_rejects_zero_price():
    assert passes_prefilter(ad(price=0.0), {}) is False


def test_rejects_negative_price():
    assert passes_prefilter(ad(price=-5.0), {}) is False


def test_accepts_normal_ad_with_no_constraints():
    assert passes_prefilter(ad(), {}) is True


def test_rejects_excluded_keyword_case_insensitive():
    search = {"exclude_keywords": "pour pieces, hs, cassé"}
    assert passes_prefilter(ad(title="PS5 HS pour pieces"), search) is False


def test_accepts_when_no_excluded_keyword_matches():
    search = {"exclude_keywords": "pour pieces, hs"}
    assert passes_prefilter(ad(title="PS5 nickel"), search) is True


def test_rejects_above_price_max():
    search = {"price_max": 150}
    assert passes_prefilter(ad(price=200.0), search) is False


def test_accepts_below_price_max():
    search = {"price_max": 300}
    assert passes_prefilter(ad(price=200.0), search) is True
