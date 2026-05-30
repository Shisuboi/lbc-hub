import pytest
from engine.db import Brain
from engine.cascade import (
    compute_margin_and_category, triage_batch, verify_one, photo_one,
)
from engine.router import TIER_RANKS, QuotaExhausted


# ---- compute_margin_and_category (pur) ----

def test_margin_basic():
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=90,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    assert out["est_margin_eur"] == 150.0
    assert out["est_margin_pct"] == 75.0
    # max_buy = 350 - max(30, 200*0.30=60) = 350 - 60 = 290
    assert out["max_buy_price"] == 290.0
    assert out["category"] == "urgent"   # score>=75, marge OK, tier Pro


def test_no_urgent_when_tier_below_min():
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=95,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["flash"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    assert out["category"] == "interesting"  # plafond 🟡 car tier < pro (Pro suspendu)


def test_no_urgent_when_margin_too_low():
    out = compute_margin_and_category(
        price=300.0, est_market_price=320.0, refined_score=95,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    # marge 20€ < 30€ ET 6.7% < 30% → pas urgent
    assert out["category"] == "interesting"


def test_passable_when_low_score():
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=40,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    assert out["category"] == "passable"


# ---- triage_batch (FakeRouter) ----

class FakeRouter:
    def __init__(self, data, tier_rank=TIER_RANKS["flash-lite"]):
        self._data = data
        self._tier = tier_rank
        self.min_urgent_rank = TIER_RANKS["pro"]

    async def generate(self, stage, prompt, schema, image_bytes=None):
        return self._data, "fake-model", self._tier


async def test_triage_batch_maps_results_and_blocks_urgent():
    ads = [{"ad_id": "1", "title": "PS5", "price": 200.0, "city": "Paris"}]
    # le routeur (ici fake) renvoie 'urgent' à tort → doit être rabaissé à 'interesting'
    router = FakeRouter({"items": [
        {"ad_id": "1", "category": "urgent", "score": 90, "dig_deeper": True, "reason": "x"},
    ]})
    brain = Brain(":memory:")
    out = await triage_batch(ads, router, brain)
    assert out["1"]["category"] == "interesting"  # jamais urgent au triage
    assert out["1"]["dig_deeper"] is True


async def test_triage_batch_records_market_obs():
    ads = [{"ad_id": "1", "title": "PS5", "price": 200.0, "city": "Paris",
            "category": "consoles_jeux_video"}]
    router = FakeRouter({"items": [
        {"ad_id": "1", "category": "interesting", "score": 60, "dig_deeper": False, "reason": "x"},
    ]})
    brain = Brain(":memory:")
    await triage_batch(ads, router, brain)
    rows = brain.conn.execute("select prix from market_observations").fetchall()
    assert rows[0]["prix"] == 200.0


# ---- verify_one (FakeRouter) ----

async def test_verify_one_promotes_urgent_with_pro():
    ad = {"ad_id": "1", "title": "PS5", "price": 200.0, "city": "Paris",
          "category": "consoles_jeux_video"}
    search = {"min_margin_eur": 30, "min_margin_pct": 30}
    router = FakeRouter(
        {"refined_score": 92, "est_market_price": 350.0, "signals": ["sous-coté"],
         "is_lot": False, "explanation": "ok"},
        tier_rank=TIER_RANKS["pro"],
    )
    brain = Brain(":memory:")
    out = await verify_one(ad, search, router, brain, urgent_score_threshold=75)
    assert out["category"] == "urgent"
    assert out["est_margin_eur"] == 150.0
    assert out["model_used"] == "fake-model"


async def test_verify_one_capped_at_interesting_without_pro():
    ad = {"ad_id": "1", "title": "PS5", "price": 200.0, "city": "Paris",
          "category": "consoles_jeux_video"}
    search = {"min_margin_eur": 30, "min_margin_pct": 30}
    router = FakeRouter(
        {"refined_score": 92, "est_market_price": 350.0, "signals": [],
         "is_lot": False, "explanation": "ok"},
        tier_rank=TIER_RANKS["flash"],   # pas Pro
    )
    brain = Brain(":memory:")
    out = await verify_one(ad, search, router, brain, urgent_score_threshold=75)
    assert out["category"] == "interesting"  # plafond 🟡


# ---- photo_one (FakeRouter) ----

async def test_photo_one_returns_verdict():
    ad = {"ad_id": "1", "title": "PS5"}
    router = FakeRouter({"verdict": "bon état", "scam_risk": "low"})
    out = await photo_one(ad, b"\xff\xd8\xff", router)
    assert out["photo_verdict"] == "bon état"
    assert out["scam_risk"] == "low"
