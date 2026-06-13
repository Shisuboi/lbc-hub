# tests/test_engine_enrich.py
import pytest
from engine.db import Brain
from engine.enrich import enrich_once
from engine.router import TIER_RANKS, QuotaExhausted


class FakeSupa:
    def __init__(self):
        self.upserts = []
        self.session = None  # miroir du vrai Supa ; fill_latlon géocode en best-effort (noop ici)

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
             url="https://www.leboncoin.fr/ad/consoles_jeux_video/1", title=None):
    payload = {
        "ad_id": ad_id, "source_search_id": "s1", "title": title or f"PS5 {ad_id}", "price": price,
        "url": url, "image_url": image_url, "location_city": "Paris",
        "category": None, "resale_score": None, "status": "active",
    }
    brain.queue_pending(payload, search_id="s1", ad_id=ad_id, now=1000)


def seed_model_grounding(brain, model_name, n=6, price=300.0, category="consoles_jeux_video"):
    """Seed ≥5 observations marché du MÊME modèle → grounding 'model' = requis pour un 🔴."""
    for _ in range(n):
        brain.record_market_obs(category, float(price), "Paris", model_name=model_name)


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
    queue_ad(brain, "1", title="MacBook Air M1")
    seed_model_grounding(brain, "MacBook Air M1")  # grounding fiable → 🔴 possible
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
    queue_ad(brain, "1", image_url="https://img.leboncoin.fr/a.jpg", title="MacBook Air M1")
    seed_model_grounding(brain, "MacBook Air M1")  # grounding fiable → 🔴 (avant rétrogradation photo)
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


async def test_enrich_once_unknown_search_uses_default_margins():
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1", price=200.0)
    # recherche introuvable (searches_by_id vide) → doit retomber sur les défauts de config,
    # PAS sur 0 (sinon n'importe quelle marge positive promeut en 🔴 une fois le Pro activé).
    router = ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "interesting", "score": 90, "dig_deeper": True}],
        verify={"refined_score": 90, "est_market_price": 220.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["pro"],   # tier Pro : seule la marge doit pouvoir bloquer le 🔴
    )
    await enrich_once(
        brain, supa, router,
        settings={"urgent_score_threshold": 75,
                  "default_min_margin_eur": 30, "default_min_margin_pct": 30},
        searches_by_id={},   # recherche inconnue
        image_fetch=None,
    )
    # marge 20 € / 10 % < défauts 30/30 → reste 🟡, JAMAIS 🔴 (preuve que les défauts s'appliquent)
    assert supa.upserts[-1]["category"] == "interesting"
    assert supa.upserts[-1]["est_margin_eur"] == 20.0


async def test_enrich_once_sends_telegram_for_urgent(monkeypatch):
    """Opp urgente + telegram configuré → send_opportunity appelée, ad_id marqué."""
    sent = []
    async def fake_send(client, opp):
        sent.append(opp.get("ad_id"))
        return True  # contrat : True = envoyé → l'appelant marque comme notifié
    monkeypatch.setattr("engine.enrich.send_opportunity", fake_send)

    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "urgent-1", price=200.0, title="MacBook Air M1")
    seed_model_grounding(brain, "MacBook Air M1")  # grounding fiable → 🔴 → notif
    router = ScriptedRouter(
        triage_items=[{"ad_id": "urgent-1", "category": "interesting", "score": 85, "dig_deeper": True}],
        verify={"refined_score": 92, "est_market_price": 350.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["pro"],
    )
    telegram_stub = object()  # non-None pour activer le hook
    await enrich_once(brain, supa, router,
                      settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, telegram=telegram_stub)
    assert "urgent-1" in sent, "send_opportunity doit être appelée pour une opp urgente"
    assert brain.is_telegram_sent("urgent-1"), "ad_id doit être marqué comme envoyé"


def _today_iso():
    from datetime import date
    return date.today().isoformat()


class FakeComparator:
    """Simule la closure comparator_fetch de server.py : compte les appels, renvoie des annonces.

    - exc  : lève une exception (vrai échec : captcha/timeout) → l'appelant doit poser le cooldown.
    - skip : renvoie None (le scrape tenait le verrou, recherche NON faite) → pas de cooldown.
    """
    def __init__(self, prices=(300.0, 320.0, 280.0, 310.0, 290.0), exc=None, skip=False):
        self.calls = []
        self.prices = prices
        self.exc = exc
        self.skip = skip

    async def __call__(self, model_name, category=None):
        self.calls.append({"model": model_name, "category": category})
        if self.exc:
            raise self.exc
        if self.skip:
            return None
        return [{"title": f"{model_name} {i}", "price": p, "city": "Paris",
                 "url": "https://www.leboncoin.fr/ad/informatique/1"} for i, p in enumerate(self.prices)]


def _candidate_router():
    return ScriptedRouter(
        triage_items=[{"ad_id": "1", "category": "interesting", "score": 80, "dig_deeper": True}],
        verify={"refined_score": 70, "est_market_price": 300.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["flash"],
    )


async def test_enrich_fetches_comparables_and_records_observations(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1", url="https://www.leboncoin.fr/ad/informatique/1")
    comp = FakeComparator()
    await enrich_once(brain, supa, _candidate_router(), settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"title": "PC", "source_url": "https://www.leboncoin.fr/recherche?category=15&text=pc",
                                             "min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, comparator_fetch=comp)
    assert len(comp.calls) == 1
    assert comp.calls[0]["model"] == "PS5 Slim"
    assert comp.calls[0]["category"] == "15"
    assert brain.model_lookup_due("PS5 Slim") is False
    rows = brain.conn.execute("SELECT COUNT(*) AS c FROM market_observations WHERE prix > 0").fetchone()
    assert rows["c"] >= 5


async def test_enrich_skips_comparator_when_no_model(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: None)
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    comp = FakeComparator()
    await enrich_once(brain, supa, _candidate_router(), settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"title": "PC", "min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, comparator_fetch=comp)
    assert comp.calls == []


async def test_enrich_uses_cache_no_second_comparator_call(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    queue_ad(brain, "2")
    comp = FakeComparator()
    await enrich_once(brain, supa, ScriptedRouter(
        triage_items=[
            {"ad_id": "1", "category": "interesting", "score": 80, "dig_deeper": True},
            {"ad_id": "2", "category": "interesting", "score": 80, "dig_deeper": True},
        ],
        verify={"refined_score": 70, "est_market_price": 300.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["flash"],
    ), settings={"urgent_score_threshold": 75},
        searches_by_id={"s1": {"title": "PS5", "min_margin_eur": 30, "min_margin_pct": 30}},
        image_fetch=None, comparator_fetch=comp)
    assert len(comp.calls) == 1


async def test_enrich_survives_comparator_failure(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    comp = FakeComparator(exc=RuntimeError("captcha Datadome"))
    n = await enrich_once(brain, supa, _candidate_router(), settings={"urgent_score_threshold": 75},
                          searches_by_id={"s1": {"title": "PS5", "min_margin_eur": 30, "min_margin_pct": 30}},
                          image_fetch=None, comparator_fetch=comp)
    assert n == 1
    assert brain.model_lookup_due("PS5 Slim") is False


async def test_enrich_comparator_skip_lock_does_not_cooldown(monkeypatch):
    """Si le comparateur renvoie None (scrape tenait le verrou → recherche NON faite), on ne pose
    PAS le cooldown 3 j : le modèle doit rester éligible au prochain cycle (sinon gelé sans données).
    """
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    comp = FakeComparator(skip=True)  # renvoie None = « pas pu tourner »
    await enrich_once(brain, supa, _candidate_router(), settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"title": "PS5", "min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, comparator_fetch=comp)
    assert len(comp.calls) == 1                      # on a bien tenté
    assert brain.model_lookup_due("PS5 Slim") is True  # mais PAS de cooldown posé
    assert enrich_mod._comparator_count.get(_today_iso(), 0) == 0  # ni de quota consommé


async def test_enrich_respects_daily_cap(monkeypatch):
    monkeypatch.setattr("engine.enrich.extract_model_name", lambda t: "PS5 Slim")
    import engine.enrich as enrich_mod
    enrich_mod._comparator_count.clear()
    brain = Brain(":memory:")
    supa = FakeSupa()
    queue_ad(brain, "1")
    comp = FakeComparator()
    await enrich_once(brain, supa, _candidate_router(),
                      settings={"urgent_score_threshold": 75, "comparator_daily_cap": 0},
                      searches_by_id={"s1": {"title": "PS5", "min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, comparator_fetch=comp)
    assert comp.calls == []


async def test_enrich_once_no_duplicate_telegram(monkeypatch):
    """Si ad_id déjà marqué → send_opportunity pas rappelée."""
    sent = []
    async def fake_send(client, opp):
        sent.append(opp.get("ad_id"))
    monkeypatch.setattr("engine.enrich.send_opportunity", fake_send)

    brain = Brain(":memory:")
    brain.mark_telegram_sent("urgent-2")  # pré-marquer
    supa = FakeSupa()
    queue_ad(brain, "urgent-2", price=200.0, title="MacBook Air M1")
    seed_model_grounding(brain, "MacBook Air M1")  # grounding fiable → 🔴
    router = ScriptedRouter(
        triage_items=[{"ad_id": "urgent-2", "category": "interesting", "score": 85, "dig_deeper": True}],
        verify={"refined_score": 92, "est_market_price": 350.0, "signals": [], "is_lot": False,
                "explanation": "ok"},
        verify_tier=TIER_RANKS["pro"],
    )
    telegram_stub = object()
    await enrich_once(brain, supa, router,
                      settings={"urgent_score_threshold": 75},
                      searches_by_id={"s1": {"min_margin_eur": 30, "min_margin_pct": 30}},
                      image_fetch=None, telegram=telegram_stub)
    assert sent == [], "send_opportunity NE doit PAS être rappelée si déjà marqué"
