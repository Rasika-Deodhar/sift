"""Default category taxonomy, lane grouping, and an optional better name for "Other"."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, ValidationError

from .meta_client import MetaAPIError, ModelClient
from .models import CATEGORIES, ItemCard

log = logging.getLogger("sift.categories")
OTHER_RENAME_AT = 4


def group_lanes(cards: list[ItemCard]) -> dict[str, list[ItemCard]]:
    lanes: dict[str, list[ItemCard]] = {c: [] for c in CATEGORIES}
    for card in cards:
        lanes.setdefault(card.category, []).append(card)
    for lane in lanes.values():
        lane.sort(key=lambda c: -c.value_score)
    return lanes


class LaneName(BaseModel):
    name: str = Field(min_length=2, max_length=32)


LANE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["name"],
    "properties": {"name": {"type": "string"}},
}


async def suggest_other_name(client: ModelClient | None, cards: list[ItemCard]) -> str | None:
    """When the "Other" lane grows, ask Muse Spark for a short, descriptive lane name."""
    other = [c for c in cards if c.category == "Other"]
    if client is None or len(other) < OTHER_RENAME_AT:
        return None
    listing = "\n".join(f"- {c.summary} (topics: {', '.join(c.topics)})" for c in other[:12])
    system = (
        "Name a feed category lane in 1 to 3 words (Title Case) that covers all of these items. "
        "It must differ from: " + ", ".join(CATEGORIES[:-1]) + ". Answer as JSON {\"name\": ...}."
    )
    try:
        raw = await client.text_complete(system, listing, LANE_SCHEMA)
        return LaneName.model_validate(raw).name.strip()
    except (MetaAPIError, ValidationError, ValueError) as e:
        log.warning("lane naming failed: %s", e)
        return None
