from engine.db import Brain


def test_get_telegram_offset_default_is_zero():
    b = Brain(":memory:")
    assert b.get_telegram_offset() == 0


def test_set_then_get_telegram_offset():
    b = Brain(":memory:")
    b.set_telegram_offset(42)
    assert b.get_telegram_offset() == 42


def test_set_telegram_offset_overwrites():
    b = Brain(":memory:")
    b.set_telegram_offset(10)
    b.set_telegram_offset(99)
    assert b.get_telegram_offset() == 99
