"""Session-level learning loop: signals change weights, versions are kept, cards re-rank."""

import asyncio

from app.db import Database
from app.models import SignalType
from app.session import SessionManager

from .conftest import TINY_JPEG, FakeClient, good_result


class Recorder:
    def __init__(self):
        self.msgs = []

    async def send_json(self, m):
        self.msgs.append(m)


async def make(settings, results):
    client = FakeClient(results)
    m = SessionManager(settings, Database(settings.db_path), client)
    rec = Recorder()
    m.sockets.add(rec)
    await m.start(True, None, False)
    return m, rec


PHASHES = {1: "0" * 64, 2: "f" * 64, 3: "0f" * 32}


async def push(m, item_id, n):
    """n picks one of three far-apart hashes so the dedup cache never matches them."""
    await m.handle_message({"type": "item_frames", "item_id": item_id, "phash": PHASHES[n],
                            "frames": [TINY_JPEG]})


async def test_save_and_hide_shift_weights_and_rerank(settings):
    cyc = good_result(topics=["cycling"], intrinsic_quality=6, format="tutorial")
    meme = good_result(topics=["memes"], intrinsic_quality=6, format="humor", category="Humor")
    m, rec = await make(settings, [cyc, meme, cyc])
    await push(m, "c1", 1)
    await m.queue.drain()  # one at a time: the queue serves newest first
    await push(m, "m1", 2)
    await m.queue.drain()
    assert {c.tier for c in m.db.list_cards(m.session.id)} == {"normal"}

    await m.handle_message({"type": "signal", "item_id": "c1", "signal": "save"})
    await m.on_signal("m1", SignalType.hide)
    assert m.interest.topic_weights["cycling"] > 0 > m.interest.topic_weights["memes"]
    assert m.interest.version == 2
    assert [v["version"] for v in m.interest_versions()] == [0, 1, 2]
    diff = m.interest_diff(0, 2)["changes"]
    assert {c["key"] for c in diff} >= {"cycling", "memes"}

    # A new cycling item now scores above its intrinsic quality.
    await push(m, "c2", 3)
    await m.queue.drain()
    c2 = m.db.get_card("c2")
    assert c2.value_score > 6 and "cycling" in c2.fit_note
    updates = [x for x in rec.msgs if x["type"] == "item_update"]
    assert any(u["card"]["item_id"] == "m1" and u["card"]["value_score"] < 6 for u in updates)
    await m.shutdown()


async def test_dwell_learned_once_after_card_arrives(settings):
    m, rec = await make(settings, [good_result(topics=["cooking"])])
    m.client.delay = 0.05
    await push(m, "a", 1)
    await m.handle_message({"type": "dwell", "item_id": "a", "dwell_ms": 9000})
    assert m.interest.version == 0  # card not ready yet
    await m.queue.drain()
    await asyncio.sleep(0)
    assert m.interest.version == 1 and m.interest.topic_weights["cooking"] > 0
    await m.handle_message({"type": "dwell", "item_id": "a", "dwell_ms": 12000})
    assert m.interest.version == 1  # not double counted
    await m.shutdown()


async def test_quick_skip_lowers_weight(settings):
    m, _ = await make(settings, [good_result(topics=["deals"], format="promo")])
    await push(m, "a", 1)
    await m.queue.drain()
    await m.handle_message({"type": "dwell", "item_id": "a", "dwell_ms": 600})
    assert m.interest.topic_weights["deals"] < 0
    await m.shutdown()


async def test_signal_before_card_is_rejected(settings):
    m, _ = await make(settings, [])
    out = await m.on_signal("nope", SignalType.save)
    assert out == {"ok": False, "error": "item not analyzed yet"}
    await m.shutdown()
