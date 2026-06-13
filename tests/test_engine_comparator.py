from engine.comparator import lbc_category_from_url, build_comparator_url


def test_category_extracted_from_source_url():
    url = "https://www.leboncoin.fr/recherche?category=15&text=ordinateur&sort=time"
    assert lbc_category_from_url(url) == "15"


def test_category_none_when_absent_or_empty():
    assert lbc_category_from_url("https://www.leboncoin.fr/recherche?text=ordinateur") is None
    assert lbc_category_from_url(None) is None
    assert lbc_category_from_url("") is None


def test_build_url_encodes_model_text():
    url = build_comparator_url("ThinkPad X1 Carbon")
    assert url.startswith("https://www.leboncoin.fr/recherche?")
    assert "text=ThinkPad+X1+Carbon" in url or "text=ThinkPad%20X1%20Carbon" in url
    assert "category=" not in url


def test_build_url_scopes_category_when_provided():
    url = build_comparator_url("ThinkPad X1", category="15")
    assert "category=15" in url
    assert "text=ThinkPad+X1" in url or "text=ThinkPad%20X1" in url
