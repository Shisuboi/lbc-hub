"""Cache SQLite de l'analyse marché (Market Researcher) : lecture/écriture, expiration, invalidation."""
from engine.db import Brain

_DAY = 86400


def make_brain():
    return Brain(":memory:")


def test_get_returns_none_when_empty():
    b = make_brain()
    assert b.get_market_context("s1", "iPhone 13") is None


def test_set_then_get_roundtrip():
    b = make_brain()
    b.set_market_context("s1", "iPhone 13", "Prix moyen ~350€", now=1000)
    assert b.get_market_context("s1", "iPhone 13", now=1000 + _DAY) == "Prix moyen ~350€"


def test_expired_after_max_age():
    b = make_brain()
    b.set_market_context("s1", "iPhone 13", "Prix moyen ~350€", now=1000)
    # > 3 jours plus tard → expiré
    assert b.get_market_context("s1", "iPhone 13", max_age_days=3, now=1000 + 4 * _DAY) is None


def test_fresh_within_max_age():
    b = make_brain()
    b.set_market_context("s1", "iPhone 13", "ctx", now=1000)
    assert b.get_market_context("s1", "iPhone 13", max_age_days=3, now=1000 + 2 * _DAY) == "ctx"


def test_title_change_invalidates_cache():
    b = make_brain()
    b.set_market_context("s1", "iPhone 13", "ctx 13", now=1000)
    # même search_id mais titre différent → cache invalide (None), pas de vieux contexte servi
    assert b.get_market_context("s1", "iPhone 14", now=1000) is None


def test_set_overwrites_same_search_id():
    b = make_brain()
    b.set_market_context("s1", "iPhone 13", "ctx 13", now=1000)
    b.set_market_context("s1", "iPhone 14", "ctx 14", now=2000)
    # une seule ligne par search_id : le nouveau titre/contexte remplace l'ancien
    assert b.get_market_context("s1", "iPhone 13", now=2000) is None
    assert b.get_market_context("s1", "iPhone 14", now=2000) == "ctx 14"
