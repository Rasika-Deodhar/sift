"""Interest model: topic and format weights learned from behavior, with exponential decay.

Only topics and formats are learned (never personal attributes). Every update produces a new
version so the UI can show before/after.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import InterestModel, ItemCard, Signal, SignalType

HALF_LIFE_MS = 10 * 60 * 1000  # weights halve after 10 minutes without reinforcement
TOPIC_LR = 0.5
FORMAT_LR = 0.3
MAX_WEIGHT = 2.0
PRUNE_BELOW = 0.02

ACTION_VALUES: dict[SignalType, float] = {
    SignalType.save: 1.0,
    SignalType.more_like_this: 0.8,
    SignalType.less_like_this: -0.8,
    SignalType.hide: -1.0,
}


def dwell_value(dwell_ms: float) -> float:
    """Long dwell = interest, very short = skip, in between = no signal."""
    if dwell_ms < 1200:
        return -0.35
    if dwell_ms < 3000:
        return 0.0
    return 0.25 + 0.5 * min(1.0, (dwell_ms - 3000) / 12000)


def signal_value(s: Signal) -> float:
    if s.type == SignalType.dwell:
        return dwell_value(s.value)
    return ACTION_VALUES[s.type] * (s.value if s.value else 1.0)


def decay(weights: dict[str, float], elapsed_ms: float) -> dict[str, float]:
    if elapsed_ms <= 0:
        return dict(weights)
    f = 0.5 ** (elapsed_ms / HALF_LIFE_MS)
    return {k: w * f for k, w in weights.items() if abs(w * f) >= PRUNE_BELOW}


@dataclass
class Change:
    key: str
    kind: str  # "topic" | "format"
    before: float
    after: float

    def as_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "before": round(self.before, 3),
                "after": round(self.after, 3)}


def apply_signal(
    m: InterestModel, card: ItemCard, s: Signal
) -> tuple[InterestModel, list[Change]]:
    """Returns the next model version and what changed (ignores decay-only drift)."""
    v = signal_value(s)
    topics = decay(m.topic_weights, s.created_at - m.updated_at)
    formats = decay(m.format_weights, s.created_at - m.updated_at)
    changes: list[Change] = []
    if v != 0:
        for i, t in enumerate(card.topics):
            before = topics.get(t, 0.0)
            after = _clamp(before + TOPIC_LR * v / (1 + 0.5 * i))  # first topic counts most
            topics[t] = after
            changes.append(Change(t, "topic", before, after))
        f = card.format.value
        before = formats.get(f, 0.0)
        formats[f] = _clamp(before + FORMAT_LR * v)
        changes.append(Change(f, "format", before, formats[f]))
    topics = {k: w for k, w in topics.items() if abs(w) >= PRUNE_BELOW}
    formats = {k: w for k, w in formats.items() if abs(w) >= PRUNE_BELOW}
    nxt = InterestModel(
        version=m.version + 1, topic_weights=topics, format_weights=formats,
        focus_hint=m.focus_hint, updated_at=max(s.created_at, m.updated_at),
    )
    return nxt, changes


def diff(a: InterestModel, b: InterestModel) -> list[dict]:
    """Per-key changes from model a to model b, largest first."""
    out = []
    for kind, wa, wb in (("topic", a.topic_weights, b.topic_weights),
                         ("format", a.format_weights, b.format_weights)):
        for k in set(wa) | set(wb):
            before, after = wa.get(k, 0.0), wb.get(k, 0.0)
            if abs(after - before) >= 0.01:
                out.append(Change(k, kind, before, after).as_dict())
    return sorted(out, key=lambda c: -abs(c["after"] - c["before"]))


def describe_cause(s: Signal, card: ItemCard) -> str:
    what = card.summary[:60]
    if s.type == SignalType.dwell:
        secs = s.value / 1000
        return f"dwelled {secs:.1f}s on: {what}"
    return f"{s.type.value.replace('_', ' ')}: {what}"


def _clamp(w: float) -> float:
    return max(-MAX_WEIGHT, min(MAX_WEIGHT, w))
