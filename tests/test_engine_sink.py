"""Tests pour LocalSink (destination locale du scrape)."""

from engine.db import Brain
from engine.sink import LocalSink


async def test_sink_queues_payload_into_pending():
    """LocalSink enqueue les payloads bruts dans la file d'enrichissement."""
    brain = Brain(":memory:")
    sink = LocalSink(brain)
    await sink.insert_opportunity({"ad_id": "42", "source_search_id": "s1", "title": "PS5"})
    items = brain.peek_pending(limit=10)
    assert len(items) == 1
    assert items[0]["ad_id"] == "42"
    assert items[0]["search_id"] == "s1"
    assert items[0]["payload"]["title"] == "PS5"


async def test_sink_handles_missing_search_id():
    """LocalSink tolère les payloads sans source_search_id."""
    brain = Brain(":memory:")
    sink = LocalSink(brain)
    await sink.insert_opportunity({"ad_id": "7", "title": "x"})
    items = brain.peek_pending(limit=10)
    assert len(items) == 1
    assert items[0]["search_id"] is None
