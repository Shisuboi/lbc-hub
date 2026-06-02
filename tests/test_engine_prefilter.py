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


def test_rejects_missing_price_key():
    # scraper peut renvoyer une annonce malformée sans clé "price"
    assert passes_prefilter({"ad_id": "1", "title": "PS5", "url": "u"}, {}) is False


def test_accepts_ad_at_exact_price_max():
    # le plafond price_max est inclusif
    search = {"price_max": 200}
    assert passes_prefilter(ad(price=200.0), search) is True


# --- Blacklist intégrée "pour pièces / HS / cassé" (étage 0, sans réglage utilisateur) ---

import pytest


@pytest.mark.parametrize("title", [
    "PC portable pour pièces",
    "PC portable pour pieces",
    "Carte mère pièce détachée",
    "iPhone HS",
    "iPhone H.S à vendre",
    "Console en panne",
    "Aspirateur ne fonctionne pas",
    "PC ne s'allume plus",
    "Vélo cassé",
    "Lot vélos cassés",
    "Télévision écran cassé",
    "Smartphone écran fissuré",
    "Montre à réparer",
    "Imprimante défectueuse",
    "iPhone bloqué iCloud",
    "Samsung compte google verrouillé",
])
def test_builtin_blacklist_rejects_for_parts(title):
    # search vide : aucune exclude_keywords utilisateur → c'est la blacklist intégrée qui agit
    assert passes_prefilter(ad(title=title), {}) is False


@pytest.mark.parametrize("title", [
    "Cassette audio collector",      # ne doit PAS matcher "cassé"
    "Casserole inox neuve",          # idem
    "Lot de 3 chemises",
    "PS5 très bon état",
    "Casque audio sans fil",
])
def test_builtin_blacklist_accepts_clean_titles(title):
    assert passes_prefilter(ad(title=title), {}) is True
