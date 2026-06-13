"""Cache « modèle déjà cherché récemment » pour borner les recherches comparatives LBC."""
from engine.db import Brain

_DAY = 86400


def make_brain():
    return Brain(":memory:")


def test_due_when_never_searched():
    b = make_brain()
    assert b.model_lookup_due("ThinkPad X1") is True


def test_not_due_right_after_mark():
    b = make_brain()
    b.mark_model_lookup("ThinkPad X1", now=1000)
    assert b.model_lookup_due("ThinkPad X1", now=1000) is False


def test_due_again_after_max_age():
    b = make_brain()
    b.mark_model_lookup("ThinkPad X1", now=1000)
    assert b.model_lookup_due("ThinkPad X1", max_age_days=3, now=1000 + 4 * _DAY) is True


def test_not_due_within_max_age():
    b = make_brain()
    b.mark_model_lookup("ThinkPad X1", now=1000)
    assert b.model_lookup_due("ThinkPad X1", max_age_days=3, now=1000 + 2 * _DAY) is False


def test_mark_is_idempotent_upsert():
    b = make_brain()
    b.mark_model_lookup("ThinkPad X1", now=1000)
    b.mark_model_lookup("ThinkPad X1", now=5000)  # ré-écrit fetched_at
    assert b.model_lookup_due("ThinkPad X1", max_age_days=3, now=5000) is False
    assert b.model_lookup_due("ThinkPad X1", max_age_days=3, now=1000 + 2 * _DAY) is False
