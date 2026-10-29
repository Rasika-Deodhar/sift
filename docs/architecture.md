# Sift architecture

```
 Feed tab (any site, or the bundled Demo Feed)
        │  pixels + optional tab audio, only through the browser's getDisplayMedia prompt
        ▼
 ┌──────────────────────── Browser: Sift web app (React + TypeScript) ────────────────────────┐
 │ screenShare.ts   getDisplayMedia, Stop / browser "Stop sharing" ends everything             │
 │ frameSampler.ts  worker-timed ticks (150 ms) → 33×32 thumbnail; JPEG frames on demand       │
 │ sceneChange.ts   dHash + vertical-shift motion classifier → enter / leave / midframe        │
 │                  stability window (400 ms), color-aware revisit dedup, content crop        │
 │ dwell.ts         per-item dwell, accumulated across revisits                               │
 │ audioChunks.ts   tab audio → per-item 16 kHz mono WAV chunks, silence dropped               │
 │ api.ts           REST + one WebSocket (auto-reconnect)                                      │
 └───────────────┬──────────────────────────────────────────────────────▲───────────────────┘
   item_frames, dwell, audio_chunk, signal                    hello, item_status, item_card,
                 │                                            item_update, interest_update
 ┌───────────────▼─────────────────── Backend: FastAPI (Python) ────────┴───────────────────┐
 │ session.py      one live session; owns everything below; broadcasts to sockets           │
 │ pipeline/queue  bounded, newest-first, N workers, drops oldest on overflow / stale jobs  │
 │ pipeline/dedup  perceptual hash + color signature LRU cache → no repeat model calls      │
 │ pipeline/understand  frames (+ transcript) → Muse Spark → strict JSON → Pydantic (retry)  │
 │ pipeline/audio  WAV → Muse Voice Transcribe → Muse Spark refines the card                 │
 │ pipeline/curate quality + interest fit (+ novelty) → value score, tier, explanation       │
 │ interest.py     topic/format weights, exponential decay, versioned per change            │
 │ categories.py   default lanes; Muse Spark names the "Other" lane                          │
 │ summary.py      session digest (optionally narrated by Muse Spark)                        │
 │ meta_client.py  THE ONLY module that calls a model (Meta Model API over httpx)            │
 │ db.py           SQLite, derived data only, wiped on start / clear / restart               │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
```

## Item lifecycle

1. **Detect** (browser). Every 150 ms the sampler draws the shared video into a 33×32 canvas.
   `classifyMotion` compares consecutive thumbnails at vertical shifts of up to 20 rows: a
   better match at a non-zero shift means the page is scrolling, which ends the current item.
   An in-place change (a reel playing) keeps it. After 400 ms without scrolling the screen is a
   new item, unless both its dHash and its color thumbnail match an item seen before, in which
   case it is a revisit and its dwell resumes. A static post that changes and settles into a
   clearly different frame also counts as a new item, which catches a scroll that fell between
   two samples.
2. **Send** one JPEG frame (≤768 px) right away, and up to two more mid-dwell frames if the item
   is moving (reels). A 160 px thumbnail, cropped to the post, is the only image kept.
3. **Queue**. The backend validates the frame, then queues a job. The queue serves the newest
   item first, runs at most `SIFT_WORKERS` model calls at once, drops the oldest waiting job when
   more than `SIFT_QUEUE_MAX` are waiting, and drops jobs older than `SIFT_STALE_AFTER_S`.
   Extra frames for a waiting job are merged into it.
4. **Dedup**. Before calling the model, the job's perceptual hash and color signature are looked
   up in an LRU cache; a hit reuses the earlier understanding.
5. **Understand**. Muse Spark gets the frames, the current interest profile and any transcript,
   and must return the `UnderstandResult` JSON schema (strict `json_schema` response format, with
   a JSON-mode fallback). Pydantic validates it; on failure the call is retried once with the
   validation error appended. `is_post: false` (loading screen, menu) drops the item.
6. **Curate**. `value = quality + 3 · confidence · fit − novelty`, clamped to 0-10, where `fit`
   is a tanh of position-weighted topic weights and the format weight, and `confidence` grows
   with how much behavior Sift has seen (0 on a cold start, so ranking is by quality and
   novelty). Tiers: ≥ 7 highlight, < 4.5 skipped. The card carries the model's reason and
   evidence quote plus a local fit note ("Matches your interest in cycling").
7. **Learn**. Dwell (< 1.2 s = skip, > 3 s = interest, scaled to 15 s) and quick actions (save
   +1, more +0.8, less −0.8, hide −1) update topic weights (first topic counts most) and the
   format weight. Weights decay with a 10-minute half-life, are clamped to ±2, and every change
   is saved as a new version. After each update every card is re-scored; the ones that moved
   are pushed as `item_update` and show their score delta.
8. **Listen** (optional). While an item is on screen, tab audio is buffered, resampled to 16 kHz
   and sent in ≤ 8 s WAV chunks (max 3 per item, silence dropped). Muse Voice Transcribe returns
   text; Muse Spark then refines the card's summary, topics, reason and evidence from it.

## Meta model calls

| Where | Model | Purpose |
|---|---|---|
| `understand_item` | `muse-spark-1.3` (vision) | frames → structured item card |
| `transcribe` | `muse-voice-transcribe-1.0` | tab audio → transcript |
| `text_complete` | `muse-spark-1.3` (or `meta-models/muse-spark-open-1026` on Baseten) | refine card from transcript; name the Other lane; session digest |
| `segment` | `sam-3.1` | stretch: crop to the post region (implemented in the client, not yet used) |

All calls go through `backend/app/meta_client.py`; tests replace it with a fake.

## Privacy

- Input is only what the user shares through the browser prompt; Stop ends capture at once.
- Frames and audio exist only in memory: in the browser until sent, in a queued job until the
  model call returns (then the job's frame list is cleared). Nothing writes media to disk
  (`scripts/check-compliance.sh` checks the backend for file writes).
- SQLite keeps derived cards, small thumbnails, signals and interest versions, for the current
  session only: it is wiped when a session starts, when the backend starts, and by
  "Clear session".
- Only topics and formats are learned. The prompts forbid describing people's identity or
  personal attributes and giving health, legal or financial advice.
