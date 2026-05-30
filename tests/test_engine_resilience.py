import pytest
from engine.db import Brain
from engine.scheduler import safe_insert, flush_outbox


class FlakySupa:
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.inserted = []

    async def insert_opportunity(self, payload):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("réseau down")
        self.inserted.append(payload)


async def test_safe_insert_queues_to_outbox_on_failure():
    brain = Brain(":memory:")
    supa = FlakySupa(fail_times=1)
    ok = await safe_insert(brain, supa, {"ad_id": "1"})
    assert ok is False
    assert len(brain.peek_outbox()) == 1
    assert brain.peek_outbox()[0]["payload"]["ad_id"] == "1"


async def test_flush_outbox_replays_when_back_online():
    brain = Brain(":memory:")
    supa = FlakySupa(fail_times=1)
    await safe_insert(brain, supa, {"ad_id": "1"})  # va en outbox
    # réseau revenu : flush rejoue
    sent = await flush_outbox(brain, supa)
    assert sent == 1
    assert supa.inserted[-1]["ad_id"] == "1"
    assert brain.peek_outbox() == []
