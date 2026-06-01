import asyncio
import pytest
from engine.db import Brain
from engine.scheduler import process_search, run_engine


class FakeSupa:
    def __init__(self, searches):
        self._searches = searches
        self.inserted = []

    async def fetch_active_searches(self):
        return list(self._searches)

    async def insert_opportunity(self, payload):
        self.inserted.append(payload)


class FakeSink:
    """Mime engine.sink.LocalSink : SEULEMENT insert_opportunity, pas fetch_active_searches."""
    def __init__(self):
        self.inserted = []

    async def insert_opportunity(self, payload):
        self.inserted.append(payload)


async def test_process_search_inserts_only_new_and_filtered():
    brain = Brain(":memory:")
    supa = FakeSupa([])
    search = {"id": "s1", "source_url": "u", "platform": "leboncoin", "exclude_keywords": "hs"}
    ads = [
        {"ad_id": "1", "title": "PS5 nickel", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None},
        {"ad_id": "2", "title": "PS5 HS", "price": 50.0, "url": "u2", "city": "Lyon", "image_url": None},  # exclu
        {"ad_id": "3", "title": "gratuit", "price": 0.0, "url": "u3", "city": "Nice", "image_url": None},   # prix 0
    ]

    async def scrape_fn(url):
        return ads

    counts = await process_search(scrape_fn, brain, supa, search)
    assert counts["new"] == 1
    assert len(supa.inserted) == 1
    assert supa.inserted[0]["ad_id"] == "1"


async def test_process_search_second_cycle_dedups():
    brain = Brain(":memory:")
    supa = FakeSupa([])
    search = {"id": "s1", "source_url": "u", "platform": "leboncoin"}
    ads = [{"ad_id": "1", "title": "PS5", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None}]

    async def scrape_fn(url):
        return ads

    await process_search(scrape_fn, brain, supa, search)
    counts = await process_search(scrape_fn, brain, supa, search)  # 2e passage
    assert counts["new"] == 0
    assert len(supa.inserted) == 1  # toujours 1 seul insert


async def test_process_search_price_drop_reinserts():
    brain = Brain(":memory:")
    supa = FakeSupa([])
    search = {"id": "s1", "source_url": "u", "platform": "leboncoin"}

    async def scrape_high(url):
        return [{"ad_id": "1", "title": "PS5", "price": 300.0, "url": "u1", "city": "Paris", "image_url": None}]

    async def scrape_low(url):
        return [{"ad_id": "1", "title": "PS5", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None}]

    await process_search(scrape_high, brain, supa, search)
    counts = await process_search(scrape_low, brain, supa, search)
    assert counts["price_drop"] == 1
    assert supa.inserted[-1]["price_dropped"] is True
    assert supa.inserted[-1]["previous_price"] == 300.0


async def test_run_engine_stops_after_max_cycles():
    brain = Brain(":memory:")
    supa = FakeSupa([{"id": "s1", "source_url": "u", "platform": "leboncoin"}])

    async def scrape_fn(url):
        return [{"ad_id": "1", "title": "PS5", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None}]

    stop = asyncio.Event()
    # Phase A : supa sert à la fois de lecteur et de destination d'écriture.
    await run_engine(brain, supa, supa, scrape_fn, stop, cycle_pause=0, max_cycles=2)
    # 1 insert au cycle 1, rien au cycle 2 (dédup)
    assert len(supa.inserted) == 1


async def test_run_engine_reads_from_supa_writes_to_sink():
    """Régression Phase B : les recherches viennent de `supa`, les écritures vont au `sink`.

    Le sink n'a PAS fetch_active_searches (comme le vrai LocalSink) : si run_engine
    confond les deux rôles, il plante avec 'object has no attribute fetch_active_searches'.
    """
    brain = Brain(":memory:")
    supa = FakeSupa([{"id": "s1", "source_url": "u", "platform": "leboncoin"}])
    sink = FakeSink()

    async def scrape_fn(url):
        return [{"ad_id": "1", "title": "PS5", "price": 200.0, "url": "u1", "city": "Paris", "image_url": None}]

    stop = asyncio.Event()
    await run_engine(brain, supa, sink, scrape_fn, stop, cycle_pause=0, max_cycles=1)
    assert len(sink.inserted) == 1            # écriture → file locale (sink)
    assert sink.inserted[0]["ad_id"] == "1"
    assert supa.inserted == []                # supa reste en lecture seule (+ outbox)
