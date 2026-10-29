"""Turns an UnderstandResult into an ItemCard with a value score."""

from __future__ import annotations

from ..models import InterestModel, ItemCard, UnderstandResult


def build_card(
    item_id: str, u: UnderstandResult, interests: InterestModel | None = None,
    transcript: str | None = None,
) -> ItemCard:
    score = round(max(0.0, min(10.0, u.intrinsic_quality)), 1)
    return ItemCard(
        item_id=item_id, summary=u.summary, topics=u.topics, category=u.category,
        format=u.format, on_screen_text=u.on_screen_text, transcript=transcript,
        quality_signals=u.quality_signals, intrinsic_quality=u.intrinsic_quality,
        value_score=score, reason=u.reason, evidence_snippet=u.evidence_snippet,
        score_breakdown={"quality": score},
    )
