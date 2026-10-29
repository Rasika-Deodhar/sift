import asyncio
import base64
import struct

import pytest

from app.db import Database
from app.pipeline.audio import validate_wav
from app.session import SessionManager

from .conftest import TINY_JPEG, FakeClient, good_result


def wav(seconds=1.0, rate=16000) -> bytes:
    n = int(seconds * rate)
    data = b"\x00\x00" * n
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(data))
    return header + data


def as_data_url(b: bytes) -> str:
    return "data:audio/wav;base64," + base64.b64encode(b).decode()


def test_validate_wav():
    assert validate_wav(wav(2.0)) == pytest.approx(2.0)
    with pytest.raises(ValueError):
        validate_wav(b"OggS" + b"\x00" * 60)
    with pytest.raises(ValueError):
        validate_wav(wav(1.0, rate=44100))


REFINED = {
    "summary": "A reel explaining how to dice an onion quickly.",
    "topics": ["Cooking", "knife skills"],
    "quality_signals": ["concrete steps"],
    "intrinsic_quality": 8.5,
    "reason": "Clear technique you can use tonight.",
    "evidence_snippet": "chill it for ten minutes first",
}


async def test_transcript_refines_ready_card(settings):
    client = FakeClient([good_result(topics=["cooking"], intrinsic_quality=6), REFINED],
                        transcript="To dice an onion fast, chill it for ten minutes first.")
    m = SessionManager(settings, Database(settings.db_path), client)
    await m.start(True, None, True)
    await m.handle_message({"type": "item_frames", "item_id": "r", "phash": "0" * 64,
                            "frames": [TINY_JPEG]})
    await m.queue.drain()
    await m.handle_message({"type": "audio_chunk", "item_id": "r", "wav": as_data_url(wav())})
    await asyncio.gather(*m._audio_tasks)
    card = m.db.get_card("r")
    assert card.transcript.startswith("To dice an onion")
    assert card.topics == ["cooking", "knife skills"]
    assert card.evidence_snippet == "chill it for ten minutes first"
    assert card.value_score == 8.5
    await m.shutdown()


async def test_audio_chunks_capped_per_item_and_junk_ignored(settings):
    client = FakeClient([good_result()], transcript="")
    m = SessionManager(settings, Database(settings.db_path), client)
    await m.start(True, None, True)
    await m.handle_message({"type": "item_frames", "item_id": "r", "phash": "0" * 64,
                            "frames": [TINY_JPEG]})
    for _ in range(5):
        await m.handle_message({"type": "audio_chunk", "item_id": "r", "wav": as_data_url(wav())})
    assert m._audio_counts["r"] == 3
    await m.handle_message({"type": "audio_chunk", "item_id": "unknown", "wav": "x"})
    await asyncio.gather(*m._audio_tasks)
    await m.shutdown()
