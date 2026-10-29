import asyncio

from app.pipeline.queue import ItemQueue, Job


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


async def test_concurrency_limit_and_all_processed():
    running = 0
    peak = 0
    done = []

    async def handler(job):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        done.append(job.item_id)

    async def on_drop(job, why):
        raise AssertionError("nothing should drop")

    q = ItemQueue(handler, on_drop, concurrency=2, max_size=10)
    q.start()
    for i in range(6):
        await q.submit(Job(f"i{i}", ["f"], "h"))
    await q.drain()
    await q.stop()
    assert sorted(done) == [f"i{i}" for i in range(6)]
    assert peak == 2


async def test_backpressure_drops_oldest_when_full():
    gate = asyncio.Event()
    dropped = []
    done = []

    async def handler(job):
        await gate.wait()
        done.append(job.item_id)

    async def on_drop(job, why):
        dropped.append((job.item_id, why))

    q = ItemQueue(handler, on_drop, concurrency=1, max_size=2)
    q.start()
    await q.submit(Job("busy", ["f"], "h"))
    await asyncio.sleep(0.01)  # worker picks up "busy" and blocks
    for i in range(4):
        await q.submit(Job(f"i{i}", ["f"], "h"))
    assert dropped == [("i0", "backpressure"), ("i1", "backpressure")]
    assert q.pending == 2
    gate.set()
    await q.drain()
    await q.stop()
    # Newest first after the busy one.
    assert done == ["busy", "i3", "i2"]
    assert q.dropped == 2


async def test_stale_jobs_are_dropped_on_dequeue():
    clock = Clock()
    gate = asyncio.Event()
    dropped = []
    done = []

    async def handler(job):
        await gate.wait()
        done.append(job.item_id)

    async def on_drop(job, why):
        dropped.append((job.item_id, why))

    q = ItemQueue(handler, on_drop, concurrency=1, max_size=10, stale_after_s=30, clock=clock)
    q.start()
    await q.submit(Job("busy", ["f"], "h"))
    await asyncio.sleep(0.01)
    await q.submit(Job("old", ["f"], "h"))
    clock.t = 40
    await q.submit(Job("fresh", ["f"], "h"))
    gate.set()
    await q.drain()
    await q.stop()
    assert done == ["busy", "fresh"]
    assert dropped == [("old", "stale")]


async def test_extra_frames_merge_into_pending_job():
    gate = asyncio.Event()
    seen = {}

    async def handler(job):
        await gate.wait()
        seen[job.item_id] = list(job.frames)

    async def on_drop(job, why):
        pass

    q = ItemQueue(handler, on_drop, concurrency=1, max_size=10)
    q.start()
    await q.submit(Job("busy", ["f"], "h"))
    await asyncio.sleep(0.01)
    await q.submit(Job("reel", ["f1"], "h"))
    await q.submit(Job("reel", ["f2"], "h"))
    await q.submit(Job("reel", ["f3", "f4"], "h"))
    gate.set()
    await q.drain()
    await q.stop()
    assert seen["reel"] == ["f1", "f2", "f3"]  # capped at 3 frames
