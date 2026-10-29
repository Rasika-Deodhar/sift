# Changelog

All code, content and docs in this repository were written during the Meta Global AI Developer
Hackathon building window (Oct 27 to Nov 4, 2026).

## 2026-10-29

- M0 Setup: repo scaffold, FastAPI health + WebSocket echo, SQLite schema, Vite + React app,
  Makefile, `.env.example`, Meta Model API notes, Demo Feed page with generated posts and reels.
- M1 Capture: consent flow and `getDisplayMedia` share, worker-timed frame sampler, 1024-bit
  dHash, motion classifier (scroll vs. in-place change), scene detector with stability window,
  color-aware revisit dedup, dwell tracker, live preview and detected-items list. Vitest suite
  over a Playwright-recorded Demo Feed scroll fixture; browser e2e smoke script.
- M2 Understand: `meta_client.py` (httpx, OpenAI-compatible Chat Completions with strict
  JSON-schema output and JSON-mode fallback, 429/5xx backoff, Voice Transcribe multipart, SAM
  Responses call, optional Muse Spark Open on Baseten, offline mock), understanding prompt +
  Pydantic validation with one retry, phash + color-signature dedup cache, bounded newest-first
  queue with backpressure and stale drops, session manager and WebSocket protocol, live stream
  cards in the UI.
- M3 Curate: value score = intrinsic quality blended with interest fit (weighted by how much
  Sift has learned) minus a novelty penalty for near-repeats; highlight / normal / skipped tiers;
  fit notes ("Matches your interest in cycling"); score breakdown tooltip; Skipped group that
  expands to show why; session digest endpoint with an optional Muse Spark narrative; stats
  panel; thumbnails auto-cropped to the post.
- M4 Learn from behavior: interest model with topic/format weights, exponential decay
  (10-minute half-life), dwell bands (quick skip / neutral / long dwell) and quick actions
  (save, hide, more, less), versioned per change; `POST /signal`, `GET /interest/versions`,
  `GET /interest/diff`; live re-ranking pushes `item_update`s; interest strip with "what
  changed" flashes and a before/after table; re-ranked cards show their score delta. Fixed the
  score blend so liking a topic can only raise items on it.
- M5 Audio + Categorize: tab audio captured per on-screen item, resampled to 16 kHz mono WAV in
  the browser (silent chunks dropped, max 3 chunks per item), transcribed with Muse Voice
  Transcribe and folded into the card by Muse Spark (summary, topics, reason, evidence quote
  from speech), then re-scored. Categorize toggle with live, collapsible category lanes and
  counts; Muse Spark names the "Other" lane once it grows.
