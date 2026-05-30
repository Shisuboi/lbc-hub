# tests/test_engine_enrich.py
import pytest
from engine.db import Brain
from engine.enrich import enrich_once
from engine.router import TIER_RANKS, QuotaExhausted


class FakeSupa:
    def __init__(self):
        self.upserts = []

    async def insert_opportunity(self, payload):
        self.upserts.append(dict(payload))


class ScriptedRouter:
    """Router simulé : réponses par stage, tier configurable, exceptions optionnelles."""
    def __init__(self, triage_items, verify=None, photo=None,
                 verify_tier=TIER_RANKS["flash"], triage_exc=None, verify_exc=None):
        self.triage_items = triage_items
        self.verify = verify
        self.photo = photo
        self.verify_tier = verify_tier
        self.triage_exc = triage_exc
        self.verify_exc = verify_exc
        self.min_urgent_rank = TIER_RANKS["pro"]

    async def generate(self, stage, prompt, schema, image_bytes=None):
        if stage == "triage":
            if self.triage_exc:
                raise self.triage_exc
            return {"items": self.triage_items}, "flash-lite", TIER_RANKS["flash-lite"]
        if stage == "verify":
            if self.verify_exc:
                raise self.verify_exc
            return self.verify, "verify-model", self.verify_tier
        if stage == "photo":
            return self.photo, "photo-model", TIER_RANKS["flash-lite"]
        raise ValueError(stage)


def queue_ad(brain, ad_id, price=200.0, image_url=None,
             url="https://www.leboncoin.fr/ad/consoles_jeux_video/1"):
    payload = {
        "ad_id": ad_id, "source_search_id": "s1", "title": f"PS5 {ad_id}", "price": price,
        "url": url, "image_url": image_url, "location_city": "Paris",
        "category": None, "resale_score": None, "status": "active",
    }
    brain.queue_pending(payload, search_id="s1", ad_id=ad_id, now=1000)


async def test_enrich_once_writes_triaged_opportunity():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    router = ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "passable", "score": 40, "dig_deeper": False}],
    )
    n = await enrich_once(brain, supa, router, settings={"urgent_score_threshold": 75},
                          searches_by_id={}, image_fetch=None)
    assert n == 1
    assert supa.upserts[-1]["category"] == "passable"
    assert brain.peek_pending(limit=10) == []  # consommé


async def test_enrich_once_verifies_candidate_and_updates():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    router = ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "interesting", "score": 80, "dig_deeper": True}],
        verify={"refined_score": 92, "est_market_price": 350.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["pro"],
    )
    await enrich_once(brain, supa, router,
                      settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None)
    # le dernier upsert reflète la vérif : urgent + marge
    assert supa.upserts[-1]["category"] == "urgent"
    assert supa.upserts[-1]["est_margin_eur"] == 150.0


async def test_enrich_once_quota_exhausted_keeps_items():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")

    class Boom:
        min_urgent_rank = TIER_RANKS["pro"]
        async def generate(self, *a, **k):
            raise QuotaExhausted("epuise")

    n = await enrich_once(brain, supa, Boom(), settings={"urgent_score_threshold": 75},
                          searches_by_id={}, image_fetch=None)
    assert n == 0
    assert len(brain.peek_pending(limit=10)) == 1  # rien perdu, reste en file


async def test_enrich_once_downgrades_urgent_on_high_scam():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1", image_url="https://img.leboncoin.fr/a.jpg")
    router = ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "interesting", "score": 85, "dig_deeper": True}],
        verify={"refined_score": 92, "est_market_price": 350.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["pro"],
        photo={"verdict": "douteux", "scam_risk": "high"},
    )

    async def image_fetch(url):
        return b"\xff\xd8\xff"

    await enrich_once(brain, supa, router,
                      settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=image_fetch)
    # malgré un score+marge dignes d'un 🔴, le scam_risk high rétrograde en 🟡
    assert supa.upserts[-1]["category"] == "interesting"
    assert supa.upserts[-1]["photo_verdict"] == "douteux"


async def test_enrich_once_survives_malformed_verify():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    router = ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "interesting", "score": 80, "dig_deeper": True}],
        verify_exc=ValueError("réponse Gemini malformée"),
    )
    # ne doit PAS crasher : l'annonce reste écrite au niveau triage, l'item est consommé
    n = await enrich_once(brain, supa, router, settings={"urgent_score_threshold": 75},
                          searches_by_id={}, image_fetch=None)
    assert n == 1
    assert supa.upserts[-1]["category"] == "interesting"  # reste au verdict du triage
    assert brain.peek_pending(limit=10) == []  # consommé, pas de boucle infinie


async def test_enrich_once_drops_poison_item_after_max_retries():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    pid = brain.peek_pending(limit=10)[0]["id"]
    for _ in range(5):
        brain.bump_pending_retry(pid)  # retries = 5 → poison

    class Boom:
        min_urgent_rank = TIER_RANKS["pro"]
        async def generate(self, *a, **k):
            raise QuotaExhausted("epuise")

    n = await enrich_once(brain, supa, Boom(), settings={"urgent_score_threshold": 75},
                          searches_by_id={}, image_fetch=None)
    assert n == 0
    assert brain.peek_pending(limit=10) == []  # item poison abandonné, file débloquée


async def test_enrich_once_malformed_triage_bumps_retry():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    router = ScriptedRouter(triage_items=[], triage_exc=ValueError("triage malformé"))
    n = await enrich_once(brain, supa, router, settings={"urgent_score_threshold": 75},
                          searches_by_id={}, image_fetch=None)
    assert n == 0
    item = brain.peek_pending(limit=10)[0]
    assert item["retries"] == 1  # lot reporté, retry incrémenté (pas de crash, pas de perte)
