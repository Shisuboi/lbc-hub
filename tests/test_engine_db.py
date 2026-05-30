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


def test_record_market_obs_and_count():
    b = make_brain()
    b.record_market_obs("consoles", 100.0, "Bordeaux", now=1000)
    b.record_market_obs("consoles", 120.0, "Lyon", now=1001)
    rows = b.conn.execute(
        "select prix from market_observations where categorie='consoles' order by observed_at"
    ).fetchall()
    assert [r["prix"] for r in rows] == [100.0, 120.0]
    villes = b.conn.execute(
        "select ville from market_observations where categorie='consoles' order by observed_at"
    ).fetchall()
    assert [r["ville"] for r in villes] == ["Bordeaux", "Lyon"]


def test_log_scrape_writes_row():
    b = make_brain()
    b.log_scrape("search-1", "ok", blocked=0, now=1000)
    row = b.conn.execute("select * from scrape_log").fetchone()
    assert row["search_id"] == "search-1"
    assert row["status"] == "ok"
    assert row["last_run_at"] == 1000
    assert row["blocked_count"] == 0


def test_outbox_queue_and_pop_fifo():
    b = make_brain()
    b.queue_outbox({"a": 1}, now=1000)
    b.queue_outbox({"b": 2}, now=1001)
    items = b.peek_outbox(limit=10)
    assert [it["payload"] for it in items] == [{"a": 1}, {"b": 2}]
    b.delete_outbox(items[0]["id"])
    remaining = b.peek_outbox(limit=10)
    assert [it["payload"] for it in remaining] == [{"b": 2}]
