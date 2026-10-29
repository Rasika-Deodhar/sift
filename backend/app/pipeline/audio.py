"""Audio chunk (16 kHz mono WAV from the browser) -> transcript via Muse Voice Transcribe,
and transcript -> refined item card via Muse Spark text. Audio bytes are never stored."""

from __future__ import annotations

import logging
import struct

from pydantic import BaseModel, Field, ValidationError

from ..meta_client import MetaAPIError, ModelClient
from ..models import ItemCard

log = logging.getLogger("sift.audio")

MAX_WAV_BYTES = 1_000_000  # ~30 s at 16 kHz mono 16-bit
MIN_SPEECH_CHARS = 12


def validate_wav(data: bytes) -> float:
    """Checks a PCM WAV header; returns duration in seconds. Raises ValueError otherwise."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    if len(data) > MAX_WAV_BYTES:
        raise ValueError("audio chunk too large")
    fmt, channels, rate = struct.unpack("<HHI", data[20:28])
    bits = struct.unpack("<H", data[34:36])[0]
    if fmt != 1 or channels != 1 or rate not in (16000, 24000) or bits != 16:
        raise ValueError("expected 16 kHz or 24 kHz mono 16-bit PCM")
    return (len(data) - 44) / (rate * 2)


async def transcribe_chunk(client: ModelClient, wav: bytes) -> str:
    validate_wav(wav)
    return (await client.transcribe(wav)).strip()


class RefineResult(BaseModel):
    summary: str = Field(min_length=1, max_length=400)
    topics: list[str] = Field(min_length=1, max_length=6)
    quality_signals: list[str] = Field(default_factory=list, max_length=6)
    intrinsic_quality: float = Field(ge=0, le=10)
    reason: str = Field(min_length=1, max_length=200)
    evidence_snippet: str = Field(default="", max_length=240)


REFINE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "topics", "quality_signals", "intrinsic_quality", "reason",
                 "evidence_snippet"],
    "properties": {
        "summary": {"type": "string"},
        "topics": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
        "quality_signals": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "intrinsic_quality": {"type": "number", "minimum": 0, "maximum": 10},
        "reason": {"type": "string"},
        "evidence_snippet": {"type": "string"},
    },
}

REFINE_SYSTEM = (
    "You update Sift's card for one feed item now that its audio transcript is available. "
    "Keep what the visuals established, and use the speech to make the summary, topics, quality "
    "judgment, one-line reason (max 20 words) and evidence quote (max 15 words, copied exactly "
    "from the transcript or visible text) more accurate. Describe content, never people; no "
    "health, legal or financial advice. Topics are short lowercase noun phrases. Same quality "
    "scale as before: 0-2 clickbait/engagement bait, 3-5 generic, 6-8 informative or genuinely "
    "funny, 9-10 specific and original. Answer with one JSON object matching the schema."
)


async def refine_with_transcript(
    client: ModelClient, card: ItemCard, transcript: str
) -> RefineResult | None:
    """Returns refined fields, or None if the model call or validation fails (card is kept)."""
    if len(transcript) < MIN_SPEECH_CHARS:
        return None
    user = (
        f"Current card:\nsummary: {card.summary}\ntopics: {', '.join(card.topics)}\n"
        f"format: {card.format.value}\nvisible text: {card.on_screen_text[:600]}\n"
        f"quality signals: {', '.join(card.quality_signals)}\n"
        f"intrinsic quality: {card.intrinsic_quality}\nreason: {card.reason}\n\n"
        f'Transcript:\n"""{transcript[:3000]}"""'
    )
    for _ in range(2):
        try:
            raw = await client.text_complete(REFINE_SYSTEM, user, REFINE_SCHEMA)
            return RefineResult.model_validate(raw)
        except (ValidationError, ValueError) as e:
            log.warning("invalid refine output: %s", str(e)[:200])
            user += "\n\nYour previous answer was invalid; return only the JSON object."
        except MetaAPIError as e:
            log.warning("refine failed: %s", e)
            return None
    return None
