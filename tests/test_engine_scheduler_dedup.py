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


def test_normalize_empty_and_none_return_empty_string():
    assert normalize_search_url("") == ""
    assert normalize_search_url(None) == ""


def test_normalize_no_query_has_no_trailing_question_mark():
    assert normalize_search_url("https://www.leboncoin.fr/recherche") == "https://www.leboncoin.fr/recherche"


def test_normalize_strips_order_param():
    a = "https://www.leboncoin.fr/recherche?text=ps5&order=desc"
    b = "https://www.leboncoin.fr/recherche?text=ps5"
    assert normalize_search_url(a) == normalize_search_url(b)


def test_dedup_skips_searches_without_url():
    searches = [
        {"id": "1", "source_url": "https://www.leboncoin.fr/recherche?text=ps5"},
        {"id": "2", "source_url": None},
        {"id": "3", "source_url": ""},
    ]
    out = dedup_searches(searches)
    assert [s["id"] for s in out] == ["1"]


def test_dedup_keeps_first_occurrence():
    searches = [
        {"id": "1", "source_url": "https://www.leboncoin.fr/recherche?text=ps5&sort=time"},
        {"id": "2", "source_url": "https://www.leboncoin.fr/recherche?text=ps5"},
    ]
    out = dedup_searches(searches)
    assert out[0]["id"] == "1"
