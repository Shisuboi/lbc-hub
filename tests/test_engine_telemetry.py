import asyncio
from datetime import datetime, timezone
from engine.db import Brain
from engine.telemetry import build_heartbeat_payload, heartbeat_worker


def test_build_heartbeat_payload_fields():
    b = Brain(":memory:")
    now = 10_000
    b.log_scrape("s1", "ok", blocked=1, new_ads=10, now=now - 60)
    b.log_scrape("s1", "ok", blocked=0, new_ads=10, now=now - 120)
    payload = build_heartbeat_payload(b, "s1", now=now)

    assert payload["search_id"] == "s1"
    assert payload["ads_seen_total"] == 20
    assert payload["new_ads_per_min"] == 2.0          # 20 sur fenêtre 10 min
    assert payload["blocked_recent"] == 1
    # heartbeat_at / last_pass_at sérialisés en ISO UTC
    assert payload["heartbeat_at"] == datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    assert payload["last_pass_at"] == datetime.fromtimestamp(now - 60, tz=timezone.utc).isoformat()


def test_build_heartbeat_payload_no_passes_yet():
    b = Brain(":memory:")
    payload = build_heartbeat_payload(b, "s1", now=10_000)
    assert payload["ads_seen_total"] == 0
    assert payload["new_ads_per_min"] == 0
    assert payload["last_pass_at"] is None


class FakeSupa:
    def __init__(self, searches):
        self._searches = searches
        self.upserts = []
    async def fetch_active_searches(self):
        return self._searches
    async def upsert_heartbeat(self, payload):
        self.upserts.append(payload)


async def test_heartbeat_worker_upserts_active_search():
    b = Brain(":memory:")
    b.log_scrape("s1", "ok", new_ads=4, now=10_000)
    supa = FakeSupa([{"id": "s1"}])
    stop = asyncio.Event()
    await heartbeat_worker(b, supa, stop, interval=0, max_loops=1)
    assert len(supa.upserts) == 1
    assert supa.upserts[0]["search_id"] == "s1"


async def test_heartbeat_worker_swallows_upsert_errors():
    """Un échec d'upsert (Supabase down) ne doit pas faire remonter d'exception."""
    b = Brain(":memory:")
    class BoomSupa(FakeSupa):
        async def upsert_heartbeat(self, payload):
            raise RuntimeError("supabase down")
    supa = BoomSupa([{"id": "s1"}])
    stop = asyncio.Event()
    # ne doit PAS lever
    await heartbeat_worker(b, supa, stop, interval=0, max_loops=1)
