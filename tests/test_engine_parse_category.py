"""Tests pour la fonction extract_category."""
from engine.parse import extract_category


def test_category_standard_url():
    url = "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678"
    assert extract_category(url) == "consoles_jeux_video"


def test_category_with_query_and_slash():
    url = "https://www.leboncoin.fr/ad/informatique/2999000111/?foo=bar"
    assert extract_category(url) == "informatique"


def test_category_legacy_htm_path():
    # ancien format /<categorie>/<id>.htm
    url = "https://www.leboncoin.fr/velos/1234567890.htm"
    assert extract_category(url) == "velos"


def test_category_none_when_absent():
    assert extract_category("https://www.leboncoin.fr/recherche?text=ps5") is None
    assert extract_category("") is None
