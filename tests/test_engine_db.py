from engine.db import Brain


def make_brain():
    return Brain(":memory:")


def test_first_time_ad_is_new():
    b = make_brain()
    assert b.upsert_ad("111", 100.0, now=1000) == "new"


def test_same_price_is_seen():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    assert b.upsert_ad("111", 100.0, now=2000) == "seen"


def test_price_drop_detected():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    assert b.upsert_ad("111", 80.0, now=2000) == "price_drop"


def test_price_increase_is_seen():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    assert b.upsert_ad("111", 120.0, now=2000) == "seen"


def test_last_price_is_updated_after_drop():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    b.upsert_ad("111", 80.0, now=2000)
    # une nouvelle baisse repart bien de 80, pas de 100
    assert b.upsert_ad("111", 70.0, now=3000) == "price_drop"
    assert b.upsert_ad("111", 80.0, now=4000) == "seen"


def test_price_observations_recorded_on_change_only():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)   # 1 obs (création)
    b.upsert_ad("111", 100.0, now=2000)   # pas d'obs (inchangé)
    b.upsert_ad("111", 80.0, now=3000)    # 1 obs (baisse)
    rows = b.conn.execute(
        "select price from price_observations where ad_id='111' order by observed_at"
    ).fetchall()
    assert [r["price"] for r in rows] == [100.0, 80.0]


def test_previous_price_helper():
    b = make_brain()
    b.upsert_ad("111", 100.0, now=1000)
    b.upsert_ad("111", 80.0, now=2000)
    assert b.previous_price("111") == 100.0
