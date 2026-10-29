"""Bounded work queue with a concurrency limit and backpressure.

If the user scrolls faster than the model can keep up, the queue does not grow without bound:
when it is full the OLDEST waiting job is dropped (the newest items are what the user is looking
at), and jobs that waited longer than `stale_after_s` are dropped when dequeued.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

log = logging.getLogger("sift.queue")


@dataclass
class Job:
    item_id: str
    frames: list[str]
    phash: str
    sig: str = ""
    enqueued_at: float = field(default_factory=time.monotonic)

    def add_frames(self, frames: list[str], max_frames: int = 3) -> None:
        self.frames = (self.frames + frames)[:max_frames]


Handler = Callable[[Job], Awaitable[None]]
DropHook = Callable[[Job, str], Awaitable[None]]


class ItemQueue:
    def __init__(
        self,
        handler: Handler,
        on_drop: DropHook,
        concurrency: int = 3,
        max_size: int = 12,
        stale_after_s: float = 45.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._handler = handler
        self._on_drop = on_drop
        self._concurrency = concurrency
        self.max_size = max_size
        self.stale_after_s = stale_after_s
        self._clock = clock
        self._pending: OrderedDict[str, Job] = OrderedDict()
        self._active: set[str] = set()
        self._wake = asyncio.Event()
        self._workers: list[asyncio.Task] = []
        self.dropped = 0
        self.processed = 0

    # --- lifecycle ---
    def start(self) -> None:
        if not self._workers:
            self._workers = [
                asyncio.create_task(self._worker(i), name=f"sift-worker-{i}")
                for i in range(self._concurrency)
            ]

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._pending.clear()
        self._active.clear()

    # --- producer side ---
    @property
    def pending(self) -> int:
        return len(self._pending)

    @property
    def active(self) -> int:
        return len(self._active)

    def is_known(self, item_id: str) -> bool:
        return item_id in self._pending or item_id in self._active

    async def submit(self, job: Job) -> None:
        """Adds a job. Extra frames for an item that is still waiting are merged into its job."""
        existing = self._pending.get(job.item_id)
        if existing is not None:
            existing.add_frames(job.frames)
            return
        if job.item_id in self._active:
            return  # already being processed; late frames are ignored
        job.enqueued_at = self._clock()
        self._pending[job.item_id] = job
        while len(self._pending) > self.max_size:
            _, oldest = self._pending.popitem(last=False)
            self.dropped += 1
            await self._on_drop(oldest, "backpressure")
        self._wake.set()

    def cancel(self, item_id: str) -> bool:
        return self._pending.pop(item_id, None) is not None

    # --- consumer side ---
    async def _next(self) -> Job:
        while True:
            # Newest first: the item on screen now matters more than one scrolled past.
            while self._pending:
                _, job = self._pending.popitem(last=True)
                if self._clock() - job.enqueued_at > self.stale_after_s:
                    self.dropped += 1
                    await self._on_drop(job, "stale")
                    continue
                return job
            self._wake.clear()
            await self._wake.wait()

    async def _worker(self, idx: int) -> None:
        while True:
            job = await self._next()
            self._active.add(job.item_id)
            try:
                await self._handler(job)
                self.processed += 1
            except asyncio.CancelledError:
                raise
            except Exception:  # handler reports its own errors; keep the worker alive
                log.exception("worker %d failed on %s", idx, job.item_id)
            finally:
                self._active.discard(job.item_id)

    async def drain(self, timeout: float = 5.0) -> None:
        """Waits until nothing is pending or active (used by tests)."""
        end = time.monotonic() + timeout
        while (self._pending or self._active) and time.monotonic() < end:
            await asyncio.sleep(0.01)
