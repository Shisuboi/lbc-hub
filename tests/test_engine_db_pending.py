"""Tests pour la file pending_enrichment du Brain."""
from engine.db import Brain


def test_queue_and_peek_pending_fifo():
    b = Brain(":memory:")
    b.queue_pending({"ad_id": "1", "title": "A"}, search_id="s1", ad_id="1", now=1000)
    b.queue_pending({"ad_id": "2", "title": "B"}, search_id="s1", ad_id="2", now=1001)
    items = b.peek_pending(limit=10)
    assert [it["ad_id"] for it in items] == ["1", "2"]
    assert items[0]["payload"]["title"] == "A"
    assert items[0]["search_id"] == "s1"


def test_delete_pending_removes_item():
    b = Brain(":memory:")
    b.queue_pending({"ad_id": "1"}, search_id="s1", ad_id="1", now=1000)
    items = b.peek_pending(limit=10)
    b.delete_pending(items[0]["id"])
    assert b.peek_pending(limit=10) == []


def test_bump_pending_retry_increments():
    b = Brain(":memory:")
    b.queue_pending({"ad_id": "1"}, search_id="s1", ad_id="1", now=1000)
    pid = b.peek_pending(limit=10)[0]["id"]
    b.bump_pending_retry(pid)
    assert b.peek_pending(limit=10)[0]["retries"] == 1
