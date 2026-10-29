# Sift

> **Your feed is optimized for the platform. Sift is optimized for you.**

Sift auto-curates a feed while you scroll it. You share a browser tab or window with Sift using
the browser's standard screen-share prompt. Sift watches what appears, understands each post or
reel with Meta's **Muse Spark** (vision) and **Muse Voice Transcribe** (audio), and builds a live,
curated stream next to it: valuable items are highlighted with a one-line reason and an evidence
quote, low-value ones collapse into a Skipped group you can always open. There is no setup: Sift
learns what you care about from how you behave (what you dwell on, save or hide), and a
**Categorize** button groups everything into live category lanes.

**Built for the Meta Global AI Developer Hackathon. All code, content and documentation in this
repository were written during the building window, Oct 27 to Nov 4, 2026** (see
[CHANGELOG.md](CHANGELOG.md) for what was built when).

## Quick start

Requirements: Python 3.11+, Node 18+, and Chrome or Edge (tab audio sharing is Chromium-only).
[`uv`](https://docs.astral.sh/uv/) is used if present, otherwise `pip`.

```bash
cp .env.example .env
```

Set `MODEL_API_KEY` in `.env` (a Meta Model API key), then:

```bash
make dev
```

Open **http://localhost:5173** (Sift) and **http://localhost:5173/demo/** (the Demo Feed) in two
windows side by side. In Sift press **Start Sift**, read the consent note, and pick the Demo Feed
tab (tick "Share tab audio" for reels). Scroll the feed; cards appear within a few seconds.

Without a key you can still try the whole loop with fake model output:
`SIFT_MOCK_META=true make dev` (the UI shows a **MOCK MODEL** badge).

| Command | What it does |
|---|---|
| `make dev` | Installs dependencies if needed, runs the API on :8000 and the web app on :5173 |
| `make test` | Backend pytest suite + frontend vitest suite |
| `make lint` | ruff, TypeScript type check, and `scripts/check-compliance.sh` |
| `make e2e` | Browser end-to-end smoke test against a running `make dev` (Playwright) |
| `make fixtures` | Re-records the scene-detection fixture by scrolling the Demo Feed |
| `make reels` | Re-renders the Demo Feed reels (ffmpeg + Flite) |

## How it works

```
 your feed (any tab)  ──getDisplayMedia──▶  Sift (browser)                    FastAPI backend
                                            frame sampler + scene detector ─▶ queue + dedup cache
                                            dwell tracker, audio chunker      Muse Spark vision → JSON card
                                            curated stream, lanes, interest ◀─ Voice Transcribe → refine
                                                                              score: quality + interest fit
                                                                              interest model (decay, versions)
```

- **Capture (browser).** Frames are sampled every 150 ms into a tiny thumbnail. A perceptual
  hash plus a vertical-shift motion test tells *scrolling* (ends the item) from *a reel playing*
  (same item). Once the screen settles for 400 ms it is a new item, or a revisit if its hash and
  colors match one seen before. One JPEG frame (plus up to two mid-reel frames) is sent per item.
- **Understand.** Muse Spark returns a strict JSON card: summary, topics, format, category,
  on-screen text, quality signals, intrinsic quality, a one-line reason and an evidence quote.
  It is validated with Pydantic and retried once if invalid.
- **Curate.** `value = quality + interest fit (up to ±3, scaled by how much Sift has learned) −
  repeat penalty`. Cold start ranks by quality and novelty; an optional focus hint ("AI, cycling")
  bootstraps it. ≥ 7 is a Sift pick, < 4.5 is collapsed into Skipped.
- **Learn.** Dwell and save / hide / more / less update topic and format weights with
  exponential decay; every change is a new version (before/after view), and the whole stream is
  re-scored live.
- **Listen.** Tab audio is chunked per item in the browser as 16 kHz WAV, transcribed by Muse
  Voice Transcribe, and Muse Spark folds the transcript into the card.
- **Engineering.** Bounded newest-first queue with concurrency limit and backpressure, stale-job
  dropping, perceptual-hash + color dedup cache, 429 backoff with `Retry-After`, auto-reconnecting
  WebSocket, all Meta calls behind one module.

More detail: [docs/architecture.md](docs/architecture.md). API details and model notes:
[docs/meta-api-notes.md](docs/meta-api-notes.md). Demo: [docs/demo-script.md](docs/demo-script.md).

## Meta models used

| Model | Used for |
|---|---|
| **Muse Spark 1.3** (`muse-spark-1.3`), vision | Understanding each post from screen frames into a structured card |
| **Muse Spark 1.3**, text | Refining cards from transcripts, naming the "Other" lane, writing the session digest |
| **Muse Voice Transcribe** (`muse-voice-transcribe-1.0`) | Transcribing tab audio of reels |
| **SAM 3.1** (`sam-3.1`) | Stretch: client method implemented for cropping to the post region, not yet wired in |
| **Muse Spark Open** (`meta-models/muse-spark-open-1026` on Baseten) | Optional: `SIFT_OPEN_WEIGHT_TEXT=true` runs text calls on the open-weight model |

Every model call goes through [`backend/app/meta_client.py`](backend/app/meta_client.py), using
plain `httpx` against the Meta Model API. No other AI provider is used anywhere;
`make lint` runs [`scripts/check-compliance.sh`](scripts/check-compliance.sh), which fails on any
other provider's SDK or endpoint.

## Privacy and platform rules

- Sift's only input is what you choose to share through the browser's screen-share prompt. It
  has no browser extension and never reads, scrapes, automates or injects into any site. Stop
  (or the browser's own "Stop sharing") ends capture immediately.
- Frames and audio are processed in memory and never written to disk. Sift keeps only derived
  text cards and small thumbnails for the current session, in a local SQLite file that is wiped
  on session start, on backend start, and by **Clear session**.
- Sift learns topics and formats only, never personal attributes. Its prompts forbid describing
  people's identity or traits and giving health, legal or financial advice.
- The Demo Feed (`demo_feed/`) contains only content created for this project (generated SVG
  posts and reels rendered with ffmpeg + Flite); see
  [demo_feed/LICENSE-CONTENT.md](demo_feed/LICENSE-CONTENT.md). Topics are non-political.

## Tests

- **Scene detection** on a recorded Demo Feed scroll (`frontend/src/capture/__fixtures__`):
  one item per post, revisits deduplicated, balanced enter/leave, dwell accumulation, plus
  scroll vs. in-place motion and reel mid-frame cases.
- **JSON validation and retry** of model output, **dedup cache**, **queue backpressure** and
  stale drops, **interest-model math** (bands, decay, clamping, versions), curation scoring,
  session-level learning and re-ranking, audio refinement, lanes, and the Meta client against a
  mocked HTTP transport (auth, image parts, schema fallback, 429 retry, transcription).
- `make e2e` drives real Chromium: it shares the Demo Feed tab into Sift, scrolls, checks every
  post becomes a card, a revisit is recognized, Save/Hide update the interest strip, and lanes
  hold the same items.

## Repository layout

```
backend/app/       FastAPI app, session manager, Meta client, pipeline, interest model
backend/tests/     pytest suite (all model calls faked)
frontend/src/      React app; capture/ holds screen share, sampling, detection, dwell, audio
frontend/scripts/  e2e smoke test and fixture recorder (Playwright, local pages only)
demo_feed/         static Demo Feed + its generated media
docs/              architecture, Meta API notes, demo script
SIFT_PLAN.md       the build plan this project follows
```

## License

Code: [MIT](LICENSE). Demo Feed content: CC0 (see `demo_feed/LICENSE-CONTENT.md`).
