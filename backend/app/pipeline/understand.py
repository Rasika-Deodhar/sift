"""frames (+ optional transcript) -> validated UnderstandResult via Muse Spark vision."""

from __future__ import annotations

import json
import logging
from functools import cache
from pathlib import Path

from pydantic import ValidationError

from ..meta_client import ModelClient
from ..models import CATEGORIES, InterestModel, ItemFormat, UnderstandResult

log = logging.getLogger("sift.understand")
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

# Hand-written so it is valid for strict structured output (all keys required, no extras).
UNDERSTAND_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "is_post", "summary", "topics", "format", "category", "on_screen_text",
        "quality_signals", "intrinsic_quality", "reason", "evidence_snippet",
    ],
    "properties": {
        "is_post": {"type": "boolean"},
        "summary": {"type": "string", "description": "One or two sentences on what the post is."},
        "topics": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
        "format": {"type": "string", "enum": [f.value for f in ItemFormat]},
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "on_screen_text": {"type": "string", "description": "Main visible text, verbatim, short."},
        "quality_signals": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "intrinsic_quality": {"type": "number", "minimum": 0, "maximum": 10},
        "reason": {"type": "string"},
        "evidence_snippet": {"type": "string"},
    },
}


class UnderstandError(RuntimeError):
    pass


@cache
def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text()


def describe_interests(model: InterestModel | None, top: int = 6) -> str:
    if model is None or model.is_empty:
        return "(nothing yet: cold start)"
    lines = []
    if model.focus_hint:
        lines.append("Focus hint they typed: " + ", ".join(model.focus_hint))
    likes = sorted(model.topic_weights.items(), key=lambda kv: -kv[1])
    pos = [f"{t} ({w:+.2f})" for t, w in likes if w > 0.05][:top]
    neg = [f"{t} ({w:+.2f})" for t, w in reversed(likes) if w < -0.05][:top]
    if pos:
        lines.append("Likes topics: " + ", ".join(pos))
    if neg:
        lines.append("Skips topics: " + ", ".join(neg))
    fmts = sorted(model.format_weights.items(), key=lambda kv: -kv[1])
    if fmts:
        lines.append("Format leanings: " + ", ".join(f"{f} ({w:+.2f})" for f, w in fmts))
    return "\n".join(lines) or "(nothing yet: cold start)"


def build_user_prompt(interests: InterestModel | None, transcript: str | None = None) -> str:
    block = ""
    if transcript:
        quoted = f'"""{transcript[:2000]}"""'
        block = f"\nAudio transcript while this item was on screen:\n{quoted}\n"
    return _prompt("understand_user.md").format(
        categories=", ".join(CATEGORIES),
        formats=", ".join(f.value for f in ItemFormat),
        interest_profile=describe_interests(interests),
        transcript_block=block,
    )


async def understand(
    client: ModelClient,
    frames: list[str],
    interests: InterestModel | None = None,
    transcript: str | None = None,
) -> UnderstandResult:
    """Calls Muse Spark and validates the JSON. Retries once with the validation error."""
    system = _prompt("understand_system.md")
    prompt = build_user_prompt(interests, transcript)
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            raw = await client.understand_item(frames, prompt, UNDERSTAND_SCHEMA, system=system)
            return UnderstandResult.model_validate(raw)
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_err = e
            log.warning("invalid understand output (attempt %d): %s", attempt + 1, str(e)[:200])
            prompt = (
                build_user_prompt(interests, transcript)
                + "\n\nYour previous answer was invalid: "
                + str(e)[:400]
                + "\nReturn ONLY a JSON object that matches the schema exactly."
            )
    raise UnderstandError(f"model output invalid after retry: {last_err}")
