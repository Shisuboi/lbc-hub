from engine.scheduler import normalize_search_url, dedup_searches


def test_normalize_strips_volatile_params_and_lowercases_host():
    a = "https://WWW.leboncoin.fr/recherche?text=ps5&sort=time&page=2"
    b = "https://www.leboncoin.fr/recherche?text=ps5"
    assert normalize_search_url(a) == normalize_search_url(b)


def test_normalize_is_order_independent():
    a = "https://www.leboncoin.fr/recherche?text=ps5&price=10-200"
    b = "https://www.leboncoin.fr/recherche?price=10-200&text=ps5"
    assert normalize_search_url(a) == normalize_search_url(b)


def test_dedup_keeps_one_per_normalized_url():
    searches = [
        {"id": "1", "source_url": "https://www.leboncoin.fr/recherche?text=ps5&sort=time"},
        {"id": "2", "source_url": "https://www.leboncoin.fr/recherche?text=ps5"},
        {"id": "3", "source_url": "https://www.leboncoin.fr/recherche?text=switch"},
    ]
    out = dedup_searches(searches)
    assert len(out) == 2
    urls = {normalize_search_url(s["source_url"]) for s in out}
    assert len(urls) == 2
