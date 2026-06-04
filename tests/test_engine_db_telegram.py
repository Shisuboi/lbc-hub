from engine.db import Brain


def test_is_telegram_sent_absent_returns_false():
    b = Brain(":memory:")
    assert b.is_telegram_sent("abc") is False


def test_mark_then_is_sent():
    b = Brain(":memory:")
    b.mark_telegram_sent("abc", now=1000)
    assert b.is_telegram_sent("abc") is True


def test_mark_telegram_sent_idempotent():
    """Marquer deux fois le même ad_id ne doit pas lever d'exception."""
    b = Brain(":memory:")
    b.mark_telegram_sent("abc", now=1000)
    b.mark_telegram_sent("abc", now=2000)
    assert b.is_telegram_sent("abc") is True


def test_different_ad_ids_are_independent():
    b = Brain(":memory:")
    b.mark_telegram_sent("aaa", now=1000)
    assert b.is_telegram_sent("bbb") is False
