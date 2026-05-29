from engine.parse import extract_ad_id, clean_price


def test_extract_ad_id_standard_url():
    url = "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678"
    assert extract_ad_id(url) == "2912345678"


def test_extract_ad_id_with_trailing_slash_and_query():
    url = "https://www.leboncoin.fr/ad/informatique/2999000111/?foo=bar"
    assert extract_ad_id(url) == "2999000111"


def test_extract_ad_id_htm_suffix():
    url = "https://www.leboncoin.fr/velos/1234567890.htm"
    assert extract_ad_id(url) == "1234567890"


def test_extract_ad_id_none_when_no_digits():
    assert extract_ad_id("https://www.leboncoin.fr/recherche") is None


def test_clean_price_french_format():
    assert clean_price("1 200 €") == 1200.0


def test_clean_price_decimal_comma():
    assert clean_price("1 000,50 €") == 1000.5


def test_clean_price_empty_returns_zero():
    assert clean_price("") == 0.0
