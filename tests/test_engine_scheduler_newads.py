from engine.db import Brain
from engine.scheduler import process_search


class FakeSink:
    def __init__(self):
        self.inserted = []
    async def insert_opportunity(self, payload):
        self.inserted.append(payload)


async def test_process_search_logs_new_ads_count():
    brain = Brain(":memory:")
    sink = FakeSink()
    search = {"id": "s1", "source_url": "https://lbc/u1", "platform": "leboncoin"}

    async def scrape_fn(url):
        return [
            {"ad_id": "a1", "title": "Vélo", "price": 100.0, "url": "u1", "city": None, "image_url": None},
            {"ad_id": "a2", "title": "Console", "price": 200.0, "url": "u2", "city": None, "image_url": None},
        ]

    counts = await process_search(scrape_fn, brain, sink, search)
    assert counts["new"] == 2
    row = brain.conn.execute("select new_ads, status from scrape_log").fetchone()
    assert row["status"] == "ok"
    assert row["new_ads"] == 2
