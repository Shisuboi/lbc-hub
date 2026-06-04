import asyncio
import pytest
from engine.db import Brain
from engine.telegram_bot import telegram_poll_worker


class FakeTelegram:
    def __init__(self, updates_sequence):
        self._seq = iter(updates_sequence)
        self.answered = []

    async def get_updates(self, offset=0):
        try:
            return next(self._seq)
        except StopIteration:
            return []

    async def answer_callback(self, callback_query_id, text):
        self.answered.append((callback_query_id, text))


class FakeSupa:
    def __init__(self, create_result=True):
        self.calls = []
        self._result = create_result

    async def create_contact_from_telegram(self, opp_id, first_name):
        self.calls.append((opp_id, first_name))
        return self._result


async def _run_worker(brain, supa, telegram, poll_pause=0):
    """Exécute le worker jusqu'à stop."""
    stop = asyncio.Event()
    task = asyncio.create_task(
        telegram_poll_worker(brain, supa, telegram, stop, poll_pause=poll_pause)
    )
    await asyncio.sleep(0.05)
    stop.set()
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass


async def test_contact_callback_creates_signal_and_answers_enregistre():
    brain = Brain(":memory:")
    supa = FakeSupa(create_result=True)
    telegram = FakeTelegram([
        [{"update_id": 1, "callback_query": {
            "id": "cq-1", "data": "contact:opp-abc",
            "from": {"first_name": "Tristan"},
        }}],
    ])
    await _run_worker(brain, supa, telegram)
    assert ("opp-abc", "Tristan") in supa.calls
    assert any("Enregistré" in t for _, t in telegram.answered)
    assert brain.get_telegram_offset() == 2


async def test_contact_already_active_answers_deja_pris():
    brain = Brain(":memory:")
    supa = FakeSupa(create_result=False)
    telegram = FakeTelegram([
        [{"update_id": 5, "callback_query": {
            "id": "cq-2", "data": "contact:opp-xyz",
            "from": {"first_name": "Susanna"},
        }}],
    ])
    await _run_worker(brain, supa, telegram)
    assert any("occupe" in t.lower() and "déjà" in t.lower() for _, t in telegram.answered)


async def test_unknown_callback_data_answered_empty():
    brain = Brain(":memory:")
    supa = FakeSupa()
    telegram = FakeTelegram([
        [{"update_id": 3, "callback_query": {
            "id": "cq-3", "data": "autre_commande",
            "from": {"first_name": "X"},
        }}],
    ])
    await _run_worker(brain, supa, telegram)
    assert supa.calls == []
    assert any(t == "" for _, t in telegram.answered)


async def test_offset_advances_through_updates():
    brain = Brain(":memory:")
    supa = FakeSupa()
    telegram = FakeTelegram([
        [{"update_id": 10, "callback_query": {"id": "c1", "data": "contact:x", "from": {"first_name": "A"}}}],
        [{"update_id": 11, "callback_query": {"id": "c2", "data": "contact:y", "from": {"first_name": "B"}}}],
    ])
    await _run_worker(brain, supa, telegram)
    assert brain.get_telegram_offset() >= 12
