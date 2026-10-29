"""Pydantic models shared by the API, the pipeline and the database layer."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CATEGORIES: tuple[str, ...] = (
    "Tutorials & How-to",
    "News & Updates",
    "Opinion & Discussion",
    "Humor",
    "Inspiration",
    "Product & Promo",
    "Other",
)


class ItemFormat(StrEnum):
    tutorial = "tutorial"
    opinion = "opinion"
    news = "news"
    humor = "humor"
    inspiration = "inspiration"
    promo = "promo"
    other = "other"


class SignalType(StrEnum):
    dwell = "dwell"
    save = "save"
    hide = "hide"
    more_like_this = "more_like_this"
    less_like_this = "less_like_this"


class ItemStatus(StrEnum):
    detected = "detected"
    queued = "queued"
    processing = "processing"
    ready = "ready"
    deduped = "deduped"
    dropped = "dropped"
    error = "error"


def now_ms() -> int:
    return int(time.time() * 1000)


class Session(BaseModel):
    id: str
    started_at: int
    stopped_at: int | None = None
    consent_acknowledged: bool = False
    settings: dict = Field(default_factory=dict)


class Item(BaseModel):
    id: str
    session_id: str
    phash: str
    sig: str = ""  # small color signature (hex), used only for dedup
    first_seen_at: int
    last_seen_at: int
    dwell_ms: int = 0
    thumb: str | None = None  # small JPEG data URL; optional, session-scoped
    status: ItemStatus = ItemStatus.detected
    duplicate_of: str | None = None


class UnderstandResult(BaseModel):
    """Strict shape we ask Muse Spark to return for one on-screen post."""

    is_post: bool = True
    summary: str = Field(min_length=1, max_length=400)
    topics: list[str] = Field(min_length=1, max_length=6)
    format: ItemFormat
    category: str
    on_screen_text: str = Field(default="", max_length=1200)
    quality_signals: list[str] = Field(default_factory=list, max_length=6)
    intrinsic_quality: float = Field(ge=0, le=10)
    reason: str = Field(min_length=1, max_length=200)
    evidence_snippet: str = Field(default="", max_length=240)

    @field_validator("topics")
    @classmethod
    def _norm_topics(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for t in v:
            t = " ".join(t.strip().lower().split())[:40]
            if t and t not in out:
                out.append(t)
        if not out:
            raise ValueError("topics must contain at least one non-empty topic")
        return out

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        for c in CATEGORIES:
            if v.strip().lower() == c.lower():
                return c
        return "Other"


class ItemCard(BaseModel):
    item_id: str
    summary: str
    topics: list[str]
    category: str
    format: ItemFormat
    on_screen_text: str = ""
    transcript: str | None = None
    quality_signals: list[str] = Field(default_factory=list)
    intrinsic_quality: float = 5.0
    value_score: float = Field(ge=0, le=10)
    reason: str
    evidence_snippet: str = ""
    tier: Literal["highlight", "normal", "skipped"] = "normal"
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    fit_note: str = ""  # e.g. "Matches your interest in cycling" (from the interest model)


class InterestModel(BaseModel):
    version: int = 0
    topic_weights: dict[str, float] = Field(default_factory=dict)
    format_weights: dict[str, float] = Field(default_factory=dict)
    focus_hint: list[str] = Field(default_factory=list)
    updated_at: int = Field(default_factory=now_ms)

    @property
    def is_empty(self) -> bool:
        return not self.topic_weights and not self.format_weights and not self.focus_hint


class Signal(BaseModel):
    item_id: str
    type: SignalType
    value: float = 1.0
    created_at: int = Field(default_factory=now_ms)


class SignalIn(BaseModel):
    item_id: str
    type: SignalType
    value: float = 1.0


class SessionStartIn(BaseModel):
    consent_acknowledged: bool
    focus_hint: str | None = None
    audio_enabled: bool = False
