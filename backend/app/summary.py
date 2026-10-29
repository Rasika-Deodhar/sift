"""Session digest: top picks, categories, what was skipped and why."""

from __future__ import annotations

import logging
from collections import Counter

from .meta_client import MetaAPIError, ModelClient
from .models import CATEGORIES, InterestModel, Item, ItemCard

log = logging.getLogger("sift.summary")


def build_summary(items: list[Item], cards: list[ItemCard], interest: InterestModel) -> dict:
    by_id = {i.id: i for i in items}
    ranked = sorted(cards, key=lambda c: -c.value_score)
    picks = [c for c in ranked if c.tier == "highlight"][:5] or ranked[:3]
    skipped = [c for c in ranked if c.tier == "skipped"]
    cats = Counter(c.category for c in cards)
    dwell = sum(i.dwell_ms for i in items)
    top_topics = sorted(interest.topic_weights.items(), key=lambda kv: -kv[1])[:5]
    return {
        "items_seen": len(items),
        "items_analyzed": len(cards),
        "highlighted": sum(c.tier == "highlight" for c in cards),
        "skipped": len(skipped),
        "total_dwell_ms": dwell,
        "time_on_skipped_ms": sum(by_id[c.item_id].dwell_ms for c in skipped if c.item_id in by_id),
        "categories": {k: cats.get(k, 0) for k in CATEGORIES if cats.get(k)},
        "top_picks": [_brief(c, by_id) for c in picks],
        "skipped_items": [_brief(c, by_id) for c in skipped[:10]],
        "top_topics": [{"topic": t, "weight": round(w, 3)} for t, w in top_topics if w > 0],
        "interest_version": interest.version,
    }


def _brief(c: ItemCard, by_id: dict[str, Item]) -> dict:
    it = by_id.get(c.item_id)
    return {
        "item_id": c.item_id, "summary": c.summary, "reason": c.reason,
        "category": c.category, "value_score": c.value_score, "topics": c.topics,
        "thumb": it.thumb if it else None,
    }


async def narrate(client: ModelClient | None, summary: dict, system: str) -> str | None:
    """Optional 2-3 sentence digest written by Muse Spark. Returns None on failure."""
    if client is None or summary["items_analyzed"] == 0:
        return None
    lines = [
        f"Items seen: {summary['items_seen']}, highlighted: {summary['highlighted']}, "
        f"skipped: {summary['skipped']}.",
        "Categories: " + ", ".join(f"{k} {v}" for k, v in summary["categories"].items()),
        "Top picks:",
        *[f"- {p['summary']} (why: {p['reason']})" for p in summary["top_picks"]],
        "Skipped examples:",
        *[f"- {p['summary']} (why: {p['reason']})" for p in summary["skipped_items"][:4]],
    ]
    try:
        out = await client.text_complete(system, "\n".join(lines))
    except MetaAPIError as e:
        log.warning("digest narration failed: %s", e)
        return None
    return out.strip() if isinstance(out, str) else None
