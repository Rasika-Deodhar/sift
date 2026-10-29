"""Scoring and presentation tiers.

value_score (0-10) blends:
  (a) intrinsic quality from Muse Spark (substance vs. clickbait), and
  (b) fit with the interest model (topic + format weights, plus the optional focus hint),
weighted by how much Sift has learned so far (cold start = quality only), minus a novelty
penalty for near-repeats of what was just shown. Every number is kept in score_breakdown so the
UI can explain the decision.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..models import InterestModel, ItemCard, UnderstandResult

HIGHLIGHT_AT = 7.0
SKIP_BELOW = 4.5
MAX_FIT_WEIGHT = 0.5  # at full confidence, interest fit is half of the score
NOVELTY_WINDOW = 8


def _hint_match(topic: str, hint: Sequence[str]) -> bool:
    return any(h and (h in topic or topic in h) for h in hint)


def interest_fit(topics: Sequence[str], fmt: str, m: InterestModel | None) -> tuple[float, str]:
    """Returns (fit in [-1, 1], short human note)."""
    if m is None or m.is_empty:
        return 0.0, ""
    weights: list[tuple[float, float, str]] = []  # (weight, importance, topic)
    for i, t in enumerate(topics):
        w = m.topic_weights.get(t, 0.0)
        if _hint_match(t, m.focus_hint):
            w += 0.6
        weights.append((w, 1.0 / (1 + i), t))  # first topic matters most
    total_imp = sum(imp for _, imp, _ in weights) or 1.0
    topic_part = sum(w * imp for w, imp, _ in weights) / total_imp
    fmt_part = m.format_weights.get(fmt, 0.0)
    fit = math.tanh(1.2 * topic_part + 0.5 * fmt_part)

    note = ""
    best = max(weights, key=lambda x: x[0], default=None)
    worst = min(weights, key=lambda x: x[0], default=None)
    if best and best[0] > 0.15 and fit > 0.1:
        note = f"Matches your interest in {best[2]}"
    elif worst and worst[0] < -0.15 and fit < -0.1:
        note = f"You tend to skip {worst[2]}"
    elif fmt_part > 0.2 and fit > 0.1:
        note = f"You like {fmt} posts"
    elif fmt_part < -0.2 and fit < -0.1:
        note = f"You tend to skip {fmt} posts"
    return fit, note


def interest_confidence(m: InterestModel | None) -> float:
    """0 on a cold start, approaching 1 as Sift sees more behavior."""
    if m is None or m.is_empty:
        return 0.0
    evidence = sum(abs(w) for w in m.topic_weights.values()) + sum(
        abs(w) for w in m.format_weights.values()
    )
    if m.focus_hint:
        evidence += 1.5
    return min(1.0, evidence / 3.0)


def novelty_penalty(topics: Sequence[str], recent: Sequence[Sequence[str]]) -> float:
    """Penalizes near-duplicates: items whose topics mostly repeat several recent items."""
    mine = set(topics)
    if not mine:
        return 0.0
    similar = 0
    for other in recent[-NOVELTY_WINDOW:]:
        o = set(other)
        if o and len(mine & o) / len(mine | o) >= 0.5:
            similar += 1
    return min(2.0, max(0, similar - 1) * 0.75)


def tier_for(score: float) -> str:
    if score >= HIGHLIGHT_AT:
        return "highlight"
    if score < SKIP_BELOW:
        return "skipped"
    return "normal"


def score(
    quality: float, topics: Sequence[str], fmt: str, m: InterestModel | None,
    recent_topics: Sequence[Sequence[str]] = (),
) -> tuple[float, dict[str, float], str]:
    q = max(0.0, min(10.0, quality))
    fit, note = interest_fit(topics, fmt, m)
    conf = interest_confidence(m)
    w = MAX_FIT_WEIGHT * conf
    nov = novelty_penalty(topics, recent_topics)
    value = (1 - w) * q + w * (5 + 5 * fit) - nov
    value = round(max(0.0, min(10.0, value)), 1)
    breakdown = {
        "quality": round(q, 2),
        "fit": round(fit, 3),
        "confidence": round(conf, 3),
        "novelty_penalty": round(nov, 2),
    }
    return value, breakdown, note


def build_card(
    item_id: str, u: UnderstandResult, interests: InterestModel | None = None,
    transcript: str | None = None, recent_topics: Sequence[Sequence[str]] = (),
) -> ItemCard:
    value, breakdown, note = score(
        u.intrinsic_quality, u.topics, u.format.value, interests, recent_topics
    )
    return ItemCard(
        item_id=item_id, summary=u.summary, topics=u.topics, category=u.category,
        format=u.format, on_screen_text=u.on_screen_text, transcript=transcript,
        quality_signals=u.quality_signals, intrinsic_quality=u.intrinsic_quality,
        value_score=value, reason=u.reason, evidence_snippet=u.evidence_snippet,
        tier=tier_for(value), score_breakdown=breakdown, fit_note=note,
    )


def rescore(card: ItemCard, m: InterestModel | None) -> ItemCard:
    """Recomputes score and tier for an existing card after the interest model changes.
    The novelty penalty from when the item first appeared is kept."""
    value, breakdown, note = score(card.intrinsic_quality, card.topics, card.format.value, m, ())
    nov = card.score_breakdown.get("novelty_penalty", 0.0)
    value = round(max(0.0, min(10.0, value - nov)), 1)
    breakdown["novelty_penalty"] = nov
    return card.model_copy(update={
        "value_score": value, "tier": tier_for(value), "score_breakdown": breakdown,
        "fit_note": note,
    })
