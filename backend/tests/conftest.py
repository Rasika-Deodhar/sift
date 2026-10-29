import asyncio
import base64

import pytest

from app.config import Settings

# A 1x1 JPEG is enough: the fake client never looks at pixels.
TINY_JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xd9").decode()


def good_result(**over) -> dict:
    d = {
        "is_post": True,
        "summary": "How to clean a bike chain in three steps.",
        "topics": ["Cycling", "bike maintenance"],
        "format": "tutorial",
        "category": "Tutorials & How-to",
        "on_screen_text": "Clean your bike chain in 3 steps",
        "quality_signals": ["concrete steps"],
        "intrinsic_quality": 8,
        "reason": "Concrete, quick maintenance steps.",
        "evidence_snippet": "1. Degrease 2. Rinse 3. Lube",
    }
    d.update(over)
    return d


class FakeClient:
    """Scripted stand-in for MetaClient. `responses` is consumed in order; then `default`."""

    mock = False

    def __init__(self, responses=None, default=None, delay=0.0, transcript="hello world"):
        self.responses = list(responses or [])
        self.default = default if default is not None else good_result()
        self.delay = delay
        self.calls = []
        self.text_calls = []
        self.transcript = transcript

    async def understand_item(self, frames, prompt, json_schema=None, system=None):
        self.calls.append({"frames": frames, "prompt": prompt})
        if self.delay:
            await asyncio.sleep(self.delay)
        r = self.responses.pop(0) if self.responses else self.default
        if isinstance(r, Exception):
            raise r
        return r

    async def text_complete(self, system, user, json_schema=None):
        self.text_calls.append(user)
        r = self.responses.pop(0) if self.responses else self.default
        return r

    async def transcribe(self, audio_wav):
        return self.transcript

    async def aclose(self):
        return None


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(SIFT_DB=str(tmp_path / "test.db"), SIFT_WORKERS=2, SIFT_QUEUE_MAX=4)
