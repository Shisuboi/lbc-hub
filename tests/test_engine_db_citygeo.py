from engine.db import Brain


def test_city_geo_absent_returns_none():
    b = Brain(":memory:")
    assert b.get_city_geo("Paris") is None


def test_city_geo_set_then_get():
    b = Brain(":memory:")
    b.set_city_geo("Paris", 48.8566, 2.3522, now=1000)
    assert b.get_city_geo("Paris") == (48.8566, 2.3522)


def test_city_geo_upsert_overwrites():
    b = Brain(":memory:")
    b.set_city_geo("Paris", 1.0, 2.0)
    b.set_city_geo("Paris", 48.8566, 2.3522)
    assert b.get_city_geo("Paris") == (48.8566, 2.3522)
