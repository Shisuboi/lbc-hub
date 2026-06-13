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


def test_no_urgent_when_grounding_not_confident():
    """Score/marge/tier parfaits mais grounding ni fiable ni de plancher connu → 🟡."""
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=95,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
        grounding_confident=False,
    )
    assert out["category"] == "interesting"  # plafond 🟡 : pas de comparable, pas de plancher


def test_wide_grounding_floor_steal_is_urgent():
    """Distribution large (modèle peu précis) MAIS prix sous le plancher du marché → 🔴 quelle que
    soit la génération, avec une valeur ancrée conservativement au plancher."""
    out = compute_margin_and_category(
        price=90.0, est_market_price=400.0, refined_score=90,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["flash-lite"],
        min_urgent_rank=TIER_RANKS["flash-lite"], urgent_score_threshold=85,
        grounding_confident=False, market_floor=150.0,
    )
    assert out["category"] == "urgent"
    assert out["est_market_price"] == 150.0          # ancré au plancher (≤ estimation IA)
    assert out["est_margin_eur"] == 60.0             # 150 - 90, pas 400 - 90


def test_wide_grounding_price_above_floor_not_urgent():
    """Distribution large + prix au-dessus du plancher → pas une affaire « toutes générations » → 🟡.
    (cas du MacBook Air 2015 à 140€ : plancher ~130 → marge insuffisante)."""
    out = compute_margin_and_category(
        price=140.0, est_market_price=400.0, refined_score=90,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["flash-lite"],
        min_urgent_rank=TIER_RANKS["flash-lite"], urgent_score_threshold=85,
        grounding_confident=False, market_floor=150.0,
    )
    assert out["category"] == "interesting"          # eff=min(400,150)=150 ; marge 10€ < 30€


def test_no_model_grounding_no_floor_stays_interesting():
    """Aucun modèle (donc pas de plancher) → jamais 🔴, même à prix dérisoire."""
    out = compute_margin_and_category(
        price=50.0, est_market_price=200.0, refined_score=95,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["flash-lite"],
        min_urgent_rank=TIER_RANKS["flash-lite"], urgent_score_threshold=85,
        grounding_confident=False, market_floor=None,
    )
    assert out["category"] == "interesting"


# ---- réconciliation score ↔ marge + garde-fou médiane ----

def test_score_crushed_when_margin_negative():
    """Prix demandé > marché estimé (marge négative) → le score LLM élevé est écrasé → passable.
    (cas réel : 'Macbook air' à 180€, marché ~105€, LLM emballé à 95.)"""
    out = compute_margin_and_category(
        price=180.0, est_market_price=147.5, refined_score=95,
        min_margin_eur=0, min_margin_pct=0, tier_rank=TIER_RANKS["flash-lite"],
        min_urgent_rank=TIER_RANKS["flash-lite"], urgent_score_threshold=85,
        grounding_confident=False,
    )
    assert out["est_margin_eur"] < 0
    assert out["resale_score"] <= 30
    assert out["category"] == "passable"


def test_median_guard_caps_effective_price_when_unanchored():
    """Sans ancrage fiable ni plancher, le prix marché ne dépasse JAMAIS une médiane réelle
    observée → anti-hallucination du LLM (qui surestime avec ses prix internes périmés)."""
    out = compute_margin_and_category(
        price=180.0, est_market_price=147.5, refined_score=95,
        min_margin_eur=0, min_margin_pct=0, tier_rank=TIER_RANKS["flash-lite"],
        min_urgent_rank=TIER_RANKS["flash-lite"], urgent_score_threshold=85,
        grounding_confident=False, market_median=105.0,
    )
    assert out["est_market_price"] == 105.0       # borné à la médiane (< estimation LLM 147.5)
    assert out["est_margin_eur"] == -75.0         # 105 - 180


def test_median_guard_ignored_when_grounding_confident():
    """Le garde-fou médiane ne s'applique PAS quand le grounding est fiable : on fait alors
    confiance à l'estimation IA (pas de régression sur l'ancrage modèle resserré)."""
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=90,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
        grounding_confident=True, market_median=300.0,
    )
    assert out["est_market_price"] == 350.0       # estimation IA conservée, pas bornée à 300
    assert out["est_margin_eur"] == 150.0


def test_score_capped_when_margin_below_threshold():
    """Marge positive mais sous le seuil → plafond modéré (interesting bas, pas tête de feed)."""
    out = compute_margin_and_category(
        price=300.0, est_market_price=320.0, refined_score=95,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    assert out["resale_score"] <= 60
    assert out["category"] == "interesting"


def test_score_preserved_when_margin_healthy():
    """Marge confortable → le score du LLM est conservé tel quel."""
    out = compute_margin_and_category(
        price=200.0, est_market_price=350.0, refined_score=90,
        min_margin_eur=30, min_margin_pct=30, tier_rank=TIER_RANKS["pro"],
        min_urgent_rank=TIER_RANKS["pro"], urgent_score_threshold=75,
    )
    assert out["resale_score"] == 90


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

def _seed_model_grounding(brain, model_name, n=6, price=300.0, category="ordinateurs"):
    """Seed ≥5 observations marché du MÊME modèle → grounding 'model' (requis pour 🔴)."""
    for _ in range(n):
        brain.record_market_obs(category, float(price), "Paris", model_name=model_name)


async def test_verify_one_promotes_urgent_with_pro():
    # titre parsable + ≥5 comparables réels du même modèle → grounding fiable → 🔴 possible
    ad = {"ad_id": "1", "title": "MacBook Air M1", "price": 200.0, "city": "Paris",
          "category": "ordinateurs"}
    search = {"min_margin_eur": 30, "min_margin_pct": 30}
    router = FakeRouter(
        {"refined_score": 92, "est_market_price": 350.0, "signals": ["sous-coté"],
         "is_lot": False, "explanation": "ok"},
        tier_rank=TIER_RANKS["pro"],
    )
    brain = Brain(":memory:")
    _seed_model_grounding(brain, "MacBook Air M1")
    out = await verify_one(ad, search, router, brain, urgent_score_threshold=75)
    assert out["category"] == "urgent"
    assert out["est_margin_eur"] == 150.0
    assert out["model_used"] == "fake-model"


async def test_verify_one_no_urgent_without_model_grounding():
    """Score/marge/tier parfaits mais AUCUN comparable réel du modèle → plafond 🟡 (pas de 🔴)."""
    ad = {"ad_id": "1", "title": "MacBook Air M1", "price": 200.0, "city": "Paris",
          "category": "ordinateurs"}
    search = {"min_margin_eur": 30, "min_margin_pct": 30}
    router = FakeRouter(
        {"refined_score": 95, "est_market_price": 350.0, "signals": [],
         "is_lot": False, "explanation": "ok"},
        tier_rank=TIER_RANKS["pro"],
    )
    brain = Brain(":memory:")  # vide → grounding non fiable
    out = await verify_one(ad, search, router, brain, urgent_score_threshold=75)
    assert out["category"] == "interesting"


async def test_verify_one_reconciles_score_and_caps_to_median():
    """Reproduit l'item réel : titre vague 'Macbook air' à 180€, marché catégorie ~105€, LLM
    emballé (score 95, marché surestimé à 147.5€). Attendu : prix marché borné à la médiane réelle,
    marge négative, score écrasé, catégorie passable — pas un 95 trompeur en tête de feed."""
    ad = {"ad_id": "1", "title": "Macbook air", "price": 180.0, "city": "Annecy",
          "category": "ordinateurs"}
    search = {"min_margin_eur": 0, "min_margin_pct": 0}
    router = FakeRouter(
        {"refined_score": 95, "est_market_price": 147.5, "signals": [],
         "is_lot": False, "explanation": "emballé"},
        tier_rank=TIER_RANKS["flash-lite"],
    )
    brain = Brain(":memory:")
    # observations catégorie (modèle non identifiable) : médiane réelle 105€, < 5 du modèle exact
    for p in (80.0, 95.0, 105.0, 115.0, 130.0):
        brain.record_market_obs("ordinateurs", p, "Paris", model_name=None)
    out = await verify_one(ad, search, router, brain, urgent_score_threshold=85)
    assert out["est_market_price"] <= 105.0
    assert out["est_margin_eur"] < 0
    assert out["resale_score"] <= 30
    assert out["category"] == "passable"


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
