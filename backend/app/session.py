"""Live session state: one local user, one active capture session at a time.

Owns the item queue, the dedup cache, the interest model and the connected WebSocket clients.
Raw frames and audio exist only inside queued jobs (memory) and are discarded after use.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket

from . import interest as interest_mod
from .config import Settings
from .db import Database
from .meta_client import MetaAPIError, ModelClient, RateLimited, decode_data_url
from .models import (
    InterestModel,
    Item,
    ItemCard,
    ItemStatus,
    Session,
    Signal,
    SignalType,
    UnderstandResult,
    now_ms,
)
from .pipeline import curate
from .pipeline.dedup import PhashCache
from .pipeline.queue import ItemQueue, Job
from .pipeline.understand import PROMPTS, UnderstandError, understand
from .summary import build_summary, narrate

log = logging.getLogger("sift.session")

MAX_FRAME_BYTES = 1_500_000
MAX_THUMB_BYTES = 40_000
MAX_FRAMES = 3


class SessionManager:
    def __init__(self, settings: Settings, db: Database, client: ModelClient | None) -> None:
        self.settings = settings
        self.db = db
        self.client = client
        self.session: Session | None = None
        self.interest = InterestModel()
        self.sockets: set[WebSocket] = set()
        self.cache: PhashCache[UnderstandResult] = PhashCache()
        self.items: dict[str, Item] = {}
        self.queue = self._new_queue()
        self._lock = asyncio.Lock()
        self._learn_lock = asyncio.Lock()
        self._dwell_applied: set[str] = set()

    def _new_queue(self) -> ItemQueue:
        return ItemQueue(
            self._process, self._dropped,
            concurrency=self.settings.worker_concurrency,
            max_size=self.settings.queue_max,
            stale_after_s=self.settings.stale_after_s,
        )

    # --- lifecycle -----------------------------------------------------------------------

    async def start(self, consent: bool, focus_hint: str | None, audio: bool) -> Session:
        async with self._lock:
            await self._reset_runtime()
            sid = uuid.uuid4().hex[:12]
            hint = [w.strip().lower() for w in (focus_hint or "").split(",") if w.strip()][:8]
            self.session = Session(
                id=sid, started_at=now_ms(), consent_acknowledged=consent,
                settings={"audio": audio, "focus_hint": hint},
            )
            self.db.insert_session(self.session)
            self.interest = InterestModel(version=0, focus_hint=hint)
            self.db.save_interest_version(sid, self.interest, "start")
            self.queue.start()
        await self.broadcast({"type": "session", "session": self.session.model_dump()})
        await self.broadcast({"type": "interest_update", "model": self.interest.model_dump(),
                              "cause": "start"})
        return self.session

    async def stop(self) -> None:
        if self.session and self.session.stopped_at is None:
            self.session.stopped_at = now_ms()
            self.db.stop_session(self.session.id, self.session.stopped_at)
            await self.broadcast({"type": "session", "session": self.session.model_dump()})

    async def clear(self) -> None:
        async with self._lock:
            await self._reset_runtime()
            self.db.clear_all()
            self.session = None
            self.interest = InterestModel()
        await self.broadcast({"type": "cleared"})

    async def _reset_runtime(self) -> None:
        await self.queue.stop()
        self.queue = self._new_queue()
        self.cache.clear()
        self.items.clear()
        self._dwell_applied.clear()

    async def shutdown(self) -> None:
        await self.queue.stop()
        if self.client:
            await self.client.aclose()

    async def summary(self, narrative: bool = False) -> dict:
        if self.session is None:
            return {"session": None}
        items = self.db.list_items(self.session.id)
        cards = self.db.list_cards(self.session.id)
        out = build_summary(items, cards, self.interest)
        out["session"] = self.session.model_dump()
        if narrative:
            system = (PROMPTS / "digest_system.md").read_text()
            out["digest"] = await narrate(self.client, out, system)
        return out

    # --- websocket -----------------------------------------------------------------------

    async def broadcast(self, msg: dict) -> None:
        dead = []
        for ws in list(self.sockets):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)

    def snapshot(self) -> dict:
        sid = self.session.id if self.session else None
        return {
            "type": "hello",
            "mock": bool(self.client and self.client.mock),
            "model_ready": self.client is not None,
            "session": self.session.model_dump() if self.session else None,
            "items": [i.model_dump() for i in self.db.list_items(sid)] if sid else [],
            "cards": [c.model_dump() for c in self.db.list_cards(sid)] if sid else [],
            "interest": self.interest.model_dump(),
        }

    async def handle_message(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if self.session is None or self.session.stopped_at is not None:
            if kind in ("item_frames", "audio_chunk", "dwell"):
                return  # capture is not active: ignore late messages
        if kind == "item_frames":
            await self.on_item_frames(msg)
        elif kind == "dwell":
            await self.on_dwell(str(msg["item_id"]), int(msg.get("dwell_ms", 0)))
        elif kind == "signal":
            await self.on_signal(str(msg["item_id"]), SignalType(msg["signal"]),
                                 float(msg.get("value", 1.0)))
        elif kind == "ping":
            return
        else:
            log.debug("ignoring message type %r", kind)

    # --- capture events ------------------------------------------------------------------

    async def on_item_frames(self, msg: dict[str, Any]) -> None:
        assert self.session is not None
        item_id = str(msg["item_id"])[:64]
        frames = [f for f in msg.get("frames", []) if isinstance(f, str)][:MAX_FRAMES]
        for f in frames:
            decode_data_url(f, MAX_FRAME_BYTES)  # validates; raises on junk
        item = self.items.get(item_id)
        if item is None:
            thumb = msg.get("thumb")
            if not (isinstance(thumb, str) and len(thumb) < MAX_THUMB_BYTES * 4 // 3 + 64):
                thumb = None
            seen = int(msg.get("seen_at") or now_ms())
            item = Item(
                id=item_id, session_id=self.session.id, phash=str(msg.get("phash", ""))[:512],
                sig=str(msg.get("sig", ""))[:512],
                first_seen_at=seen, last_seen_at=seen, thumb=thumb,
            )
            self.items[item_id] = item
        elif not msg.get("extra"):
            return
        if not frames:
            return
        if self.client is None:
            item.status = ItemStatus.error
            self.db.upsert_item(item)
            await self._status(item, error="MODEL_API_KEY is not set")
            return
        if item.status in (ItemStatus.detected, ItemStatus.queued):
            item.status = ItemStatus.queued
            self.db.upsert_item(item)
            job = Job(item_id=item_id, frames=frames, phash=item.phash, sig=item.sig)
            await self.queue.submit(job)
            await self._status(item)

    async def on_dwell(self, item_id: str, dwell_ms: int) -> None:
        item = self.items.get(item_id)
        if item is None:
            return
        item.dwell_ms = max(item.dwell_ms, dwell_ms)
        item.last_seen_at = now_ms()
        self.db.upsert_item(item)
        await self._maybe_learn_dwell(item)

    # --- learning ------------------------------------------------------------------------

    async def on_signal(self, item_id: str, kind: SignalType, value: float = 1.0) -> dict:
        """Quick action from the UI (save / hide / more / less)."""
        if self.session is None:
            return {"ok": False, "error": "no session"}
        card = self.db.get_card(item_id)
        if card is None:
            return {"ok": False, "error": "item not analyzed yet"}
        await self._learn(Signal(item_id=item_id, type=kind, value=value), card)
        return {"ok": True, "interest": self.interest.model_dump()}

    async def _maybe_learn_dwell(self, item: Item) -> None:
        """Dwell is learned once per item, when both the dwell and the card are known."""
        if item.id in self._dwell_applied or item.dwell_ms <= 0:
            return
        card = self.db.get_card(item.id)
        if card is None:
            return
        self._dwell_applied.add(item.id)
        await self._learn(Signal(item_id=item.id, type=SignalType.dwell, value=item.dwell_ms),
                          card)

    async def _learn(self, sig: Signal, card: ItemCard) -> None:
        assert self.session is not None
        async with self._learn_lock:
            self.db.add_signal(self.session.id, sig)
            new, changes = interest_mod.apply_signal(self.interest, card, sig)
            if not changes:
                return  # neutral signal (e.g. medium dwell): nothing learned
            cause = interest_mod.describe_cause(sig, card)
            self.interest = new
            self.db.save_interest_version(self.session.id, new, cause)
            await self.broadcast({
                "type": "interest_update", "model": new.model_dump(), "cause": cause,
                "signal": sig.type.value, "item_id": sig.item_id,
                "changes": [c.as_dict() for c in changes],
            })
            await self._rerank()

    async def _rerank(self) -> None:
        """Re-scores every card against the new interest model; pushes the ones that moved."""
        assert self.session is not None
        for card in self.db.list_cards(self.session.id):
            new = curate.rescore(card, self.interest)
            if new.tier != card.tier or abs(new.value_score - card.value_score) >= 0.1:
                self.db.save_card(self.session.id, new, now_ms())
                await self.broadcast({"type": "item_update", "card": new.model_dump(),
                                      "prev_score": card.value_score, "prev_tier": card.tier})

    def interest_versions(self) -> list[dict]:
        if self.session is None:
            return []
        return [
            {"version": m.version, "cause": cause, "created_at": m.updated_at,
             "top_topics": sorted(m.topic_weights.items(), key=lambda kv: -kv[1])[:5],
             "model": m.model_dump()}
            for m, cause in self.db.list_interest_versions(self.session.id)
        ]

    def interest_diff(self, a: int, b: int) -> dict:
        versions = {v["version"]: v["model"] for v in self.interest_versions()}
        if a not in versions or b not in versions:
            raise KeyError("unknown version")
        ma, mb = InterestModel(**versions[a]), InterestModel(**versions[b])
        return {"from": a, "to": b, "changes": interest_mod.diff(ma, mb)}

    # --- pipeline ------------------------------------------------------------------------

    async def _status(self, item: Item, error: str | None = None) -> None:
        await self.broadcast({
            "type": "item_status", "item_id": item.id, "status": item.status.value,
            "duplicate_of": item.duplicate_of, "error": error,
        })

    async def _dropped(self, job: Job, why: str) -> None:
        item = self.items.get(job.item_id)
        if item is None:
            return
        item.status = ItemStatus.dropped
        self.db.upsert_item(item)
        await self._status(item, error=f"skipped analysis ({why}: scrolling faster than the model)")

    async def _process(self, job: Job) -> None:
        item = self.items.get(job.item_id)
        if item is None or self.session is None:
            return
        item.status = ItemStatus.processing
        await self._status(item)

        hit = self.cache.lookup(job.phash, job.sig) if job.phash else None
        try:
            if hit is not None:
                owner, u = hit
                item.duplicate_of = owner
            else:
                assert self.client is not None
                u = await understand(self.client, job.frames, self.interest)
                if job.phash:
                    self.cache.put(job.phash, item.id, u, job.sig)
        except (UnderstandError, MetaAPIError) as e:
            item.status = ItemStatus.error
            self.db.upsert_item(item)
            msg = "rate limited by the model API" if isinstance(e, RateLimited) else str(e)
            await self._status(item, error=msg[:200])
            return
        finally:
            job.frames = []  # drop raw frames as soon as they are used

        if not u.is_post:
            item.status = ItemStatus.dropped
            self.db.upsert_item(item)
            await self._status(item, error="no post visible")
            return
        recent = [c.topics for c in self.db.list_cards(self.session.id)]
        card = curate.build_card(item.id, u, self.interest, recent_topics=recent)
        await self._publish(item, card, ItemStatus.deduped if hit else ItemStatus.ready)

    async def _publish(self, item: Item, card: ItemCard, status: ItemStatus) -> None:
        assert self.session is not None
        item.status = status
        self.db.upsert_item(item)
        self.db.save_card(self.session.id, card, now_ms())
        await self.broadcast({"type": "item_card", "card": card.model_dump(),
                              "status": status.value, "duplicate_of": item.duplicate_of})
        await self._maybe_learn_dwell(item)
