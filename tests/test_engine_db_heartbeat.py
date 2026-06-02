from engine.db import Brain


def make_brain():
    return Brain(":memory:")


def test_log_scrape_stores_new_ads():
    b = make_brain()
    b.log_scrape("s1", "ok", blocked=2, new_ads=5, now=1000)
    row = b.conn.execute("select new_ads, blocked_count from scrape_log").fetchone()
    assert row["new_ads"] == 5
    assert row["blocked_count"] == 2


def test_log_scrape_new_ads_defaults_zero():
    b = make_brain()
    b.log_scrape("s1", "ok", now=1000)
    row = b.conn.execute("select new_ads from scrape_log").fetchone()
    assert row["new_ads"] == 0


def test_ads_seen_total_sums_new_ads_for_search():
    b = make_brain()
    b.log_scrape("s1", "ok", new_ads=3, now=1000)
    b.log_scrape("s1", "ok", new_ads=4, now=2000)
    b.log_scrape("s2", "ok", new_ads=9, now=2000)  # autre recherche, ignorée
    assert b.ads_seen_total("s1") == 7
    assert b.ads_seen_total("inconnue") == 0


def test_new_ads_rate_per_minute_over_window():
    b = make_brain()
    now = 10_000
    # fenêtre 600s = 10 min. 20 annonces neuves dans la fenêtre -> 2.0 / min.
    b.log_scrape("s1", "ok", new_ads=12, now=now - 100)
    b.log_scrape("s1", "ok", new_ads=8,  now=now - 200)
    b.log_scrape("s1", "ok", new_ads=99, now=now - 5000)  # hors fenêtre, ignorée
    assert b.new_ads_rate("s1", window_s=600, now=now) == 2.0


def test_last_pass_at_returns_latest():
    b = make_brain()
    b.log_scrape("s1", "ok", now=1000)
    b.log_scrape("s1", "ok", now=3000)
    assert b.last_pass_at("s1") == 3000
    assert b.last_pass_at("inconnue") is None


def test_blocked_recent_sums_within_window():
    b = make_brain()
    now = 10_000
    b.log_scrape("s1", "error", blocked=1, now=now - 100)
    b.log_scrape("s1", "error", blocked=2, now=now - 200)
    b.log_scrape("s1", "error", blocked=5, now=now - 5000)  # hors fenêtre
    assert b.blocked_recent("s1", window_s=600, now=now) == 3
