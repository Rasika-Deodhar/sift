# Sift: v1 Build Plan (v2 of this document)

> Hand this file to Claude Code as the project brief. Ask it to read this fully, then execute the milestones in order, committing after each one.

## 1. What Sift is

Sift auto-curates a feed as the user scrolls. The user shares their own screen (or a browser tab) with Sift using the browser's standard screen-share permission. Sift watches what appears, understands each post or reel, and in real time builds a curated stream: the valuable items are highlighted with a one-line reason, and low-value ones are collapsed. No setup or teaching required. Sift learns what the user cares about from how they behave (what they dwell on, save, or hide). Later, a **Categorize** button groups the incoming items into live category lanes.

Tagline: "Your feed is optimized for the platform. Sift is optimized for you."

## 2. Hard constraints (Meta Global AI Developer Hackathon)

- Building window: Oct 27 to Nov 4, 2026. Submission due Nov 4, 9:00 PM ET. Everything in the repo must be written during this window; the README must say so.
- **Every AI feature must call Meta models only** (Muse Spark, Muse Voice Transcribe, SAM 3.1, optionally Muse Image / Muse Wonder). No OpenAI, Anthropic, Google or other model APIs inside the product.
- Repo must be public. Use only code, data and assets we have rights to.
- **Do not scrape, automate, or inject code into Instagram, Facebook, Threads or any other platform.** No browser extension that reads a platform's DOM or network traffic, no bots, no logins, no bulk downloading. Sift's only input from a platform is **pixels and audio the user chooses to share through the browser's screen-capture permission** (`getDisplayMedia`), started and stopped by the user.
- Demo content must be non-political and not about war. No health advice, personality profiling, or job-screening feature. Sift learns topic and quality preferences only.
- Privacy by default: process frames in memory, do not persist raw frames or audio beyond the session, keep only derived item cards (and optionally small thumbnails) for the session, and give the user a one-click "clear session" action.
- Demo safety: the repo ships a **Demo Feed** page (static feed of content we own or have rights to) so capture can be shown reliably without depending on any third-party site.
- Deliverables: public repo, 3-minute demo video, working live product.

## 3. Rubric focus

Impact 30%, Use of Meta AI tooling 25%, Demo 25%, Technical depth 20%. So: a live, visibly working curation loop; multimodal understanding (vision + audio); explanations; and real engineering (streaming, dedup, throttling). A smooth 3-minute demo beats a long feature list.

## 4. How it works

```
 User's feed (any site)         Sift web app (second window / second monitor)
 ----------------------         ---------------------------------------------
 user scrolls normally  --->  [Capture]  getDisplayMedia (tab/window share, optional tab audio)
                               |  frame sampler (~1 fps) + scene-change detector (perceptual hash)
                               |  dwell-time tracker (how long each item stays on screen)
                               v
                         [FastAPI backend]  (WebSocket / SSE to UI)
                               |  item queue + dedup cache + throttled workers
                               |  understand: Muse Spark vision (+ Voice Transcribe for audio chunks)
                               |  curate: score + reason + category
                               |  interest model: topic weights updated from behavior
                               v
                         [Curated stream UI]  highlighted picks, collapsed low-value, reasons
                         [Categorize button]  live category lanes (later milestone)
```

Sift runs in its own window or tab, next to the feed being scrolled. The browser requires the user to pick the shared tab or window and grants no ongoing access beyond that.

## 5. Stack

- Backend: Python 3.11+, FastAPI, Pydantic, SQLite (session-scoped), WebSocket or SSE for live updates, ffmpeg only if needed for audio.
- Frontend: Vite + React + TypeScript; capture runs client-side (`getDisplayMedia`, canvas for frame grabs, `MediaRecorder` for audio chunks); small CSS or Tailwind.
- Dev tooling: `uv` or `pip`, `npm`/`pnpm`, a `Makefile` with `dev`, `test`, `lint`.

## 6. Repo layout

```
sift/
  README.md
  SIFT_PLAN.md
  .env.example
  Makefile
  backend/
    app/
      main.py                 # FastAPI app, routes, websocket
      config.py
      models.py               # Pydantic + DB models
      db.py
      meta_client.py          # ALL Meta API calls live here (single seam)
      pipeline/
        queue.py              # item queue, concurrency limit, backpressure
        dedup.py              # perceptual-hash cache
        understand.py         # frame(s) -> ItemCard
        audio.py              # audio chunk -> transcript
        curate.py             # score + reason + category
      interest.py             # topic weights, decay, behavior signals
      categories.py           # default taxonomy + lane grouping
      prompts/
    tests/
  frontend/
    src/
      capture/ (screenShare.ts, frameSampler.ts, sceneChange.ts, dwell.ts, audioChunks.ts)
      components/ (CuratedStream.tsx, ItemCard.tsx, CategoryLanes.tsx, Controls.tsx)
      api.ts
  demo_feed/                  # static Demo Feed page + content we own or have rights to
  docs/
    architecture.md
    meta-api-notes.md
    demo-script.md
```

## 7. Data model

- `Session`: id, started_at, consent_acknowledged, settings.
- `Item`: id, session_id, first_seen_at, last_seen_at, dwell_ms, thumb (optional, small), status.
- `ItemCard`: item_id, summary, topics[], category, format (tutorial | opinion | news | humor | inspiration | promo | other), on_screen_text, transcript (nullable), quality_signals[], value_score (0-10), reason, evidence_snippet.
- `InterestModel` (per session, versioned): topic_weights{topic: float}, format_weights{format: float}, updated_at. Weights decay over time.
- `Signal`: item_id, type (dwell | save | hide | more_like_this | less_like_this), value, created_at.

Keep interest-model versions so the demo can show before/after.

## 8. Capture and detection (client-side)

1. User clicks **Start Sift**, sees a plain-language consent note, and picks the tab or window to share. Optionally enables tab audio.
2. `frameSampler` grabs frames at ~1 fps onto a canvas.
3. `sceneChange` computes a perceptual hash per frame; a significant change plus a short stability period (e.g. 400 ms) marks a **new item**. A repeated hash within the session is treated as the same item (dedup).
4. For each new item, send 1 to 3 representative frames (the stable frame, and a mid-dwell frame for reels) to the backend.
5. `dwell` records how long the item stayed on screen; send the final dwell_ms when the item changes.
6. `audioChunks` records short audio segments (e.g. 5-10 s) while an item is on screen and sends them for transcription. Skip if audio is not shared.
7. Show a small live preview and a visible "Sharing" indicator; **Stop** ends capture immediately.

Isolating the post from surrounding UI (nav bars, comments): first rely on Muse Spark's vision to describe only the main content; optionally use SAM 3.1 to crop the primary region (stretch).

## 9. Meta client (`meta_client.py`)

Single module, thin wrapper, so model names and endpoints change in one place.

- `understand_item(frames, prompt) -> dict` (Muse Spark vision, structured JSON)
- `transcribe(audio_bytes) -> str` (Muse Voice Transcribe)
- `text_complete(system, user, json_schema=None) -> dict | str` (Muse Spark)
- optional `segment(image_bytes, concept)` (SAM 3.1)

**First task before writing any code in this file:** read the Meta Model API docs (Overview, Quickstart, Model list, API fundamentals, Cookbook) and record in `docs/meta-api-notes.md`: base URL, auth, exact model IDs, supported input types (image, video, audio), size and rate limits, JSON/structured output support, latency. Do not guess. Read the API key from the environment; never commit keys.

Optional later: a config switch to run text calls on an open-weight model (Muse Spark Open) via a partner for the open-weight bonus. The hackathon requires `meta-models/muse-spark-open-1026` on Baseten, not the name in their docs.

## 10. Curation logic (no teaching step)

1. **Understand**: Muse Spark returns an `ItemCard` as strict JSON (validate with Pydantic; retry once on invalid output): summary, topics, format, on-screen text, quality signals.
2. **Score**: `value_score` combines (a) intrinsic quality signals (substance vs. clickbait, informative vs. filler, originality), and (b) fit with the interest model (topic and format weights). Muse Spark writes a one-line `reason` and an `evidence_snippet` from the visible text or transcript, so every decision is explainable and checkable.
3. **Cold start**: with an empty interest model, rank by intrinsic quality plus novelty (don't show ten near-duplicate items). Optional **Focus hint** box lets the user type a few words ("AI, cycling, cooking") to bootstrap; it is optional and never required.
4. **Learn from behavior**: dwell time (long dwell = interest, very short = skip), plus quick actions in Sift: save, hide, more like this, less like this. Update topic and format weights with exponential decay. Keep it at topic and format level, not personal attributes.
5. **Present**: items with high value_score are highlighted in the curated stream; low-value ones collapse into a "Skipped (N)" group the user can expand. Nothing is ever hidden permanently; the user can always see what was filtered and why.
6. **Throttle**: process items through a bounded queue with a concurrency limit; drop or defer stale items if the user scrolls faster than the pipeline; cache by perceptual hash to avoid repeat model calls.

## 11. Categorize button (later milestone)

A toggle on the stream. When on, incoming items are grouped into live **category lanes** (default taxonomy: Tutorials & How-to, News & Updates, Opinion & Discussion, Humor, Inspiration, Product & Promo, Other), with counts that update as the user scrolls and a collapse/expand per lane. Category is already produced in the `ItemCard`, so this is mostly UI and grouping. Optional: Muse Spark proposes a better lane name when "Other" grows large.

## 12. API surface (v1)

- `POST /session/start`, `POST /session/stop`, `POST /session/clear`
- `WS /stream`: server pushes `item_card`, `item_update`, `interest_update`; client sends `item_frames`, `audio_chunk`, `dwell`, `signal`
- `POST /signal` { item_id, type }
- `GET /session/summary`: digest of the session (top picks, categories, what was skipped)
- `GET /interest/versions`, `GET /interest/diff?from=&to=`

## 13. UI (v1)

- **Controls**: Start / Stop, optional audio toggle, Focus hint (optional), Clear session, visible "Sharing" indicator.
- **Curated stream**: live cards (thumbnail, category chip, reason, evidence, save/hide/more/less buttons); collapsed "Skipped" group.
- **Interest strip**: top topics Sift thinks you like right now, with a "what changed" indicator when they shift.
- **Categorize toggle** (later): lanes view.
- **Session summary**: a short digest at the end of a scroll session.
- Clean and demo-friendly; no accounts or auth in v1.

## 14. Milestones (each ends with a commit and a passing smoke test)

**M0: Setup (Day 1)**
- Scaffold repo, `.env.example`, Makefile, FastAPI hello + WebSocket echo, Vite app, SQLite init. README stub stating hackathon dates.
- Read Meta docs; write `docs/meta-api-notes.md`.
- Build the static **Demo Feed** page (scrollable feed of own/licensed images and short clips).

**M1: Capture (Day 1-2)**
- `getDisplayMedia` flow with consent note, frame sampler, perceptual hash, scene-change detection, dwell tracking. Show detected items in the UI with timings (no AI yet). Test against the Demo Feed.

**M2: Understand (Day 2-3)**
- `meta_client.understand_item`, ItemCard JSON with validation/retry, dedup cache, bounded queue. Items now appear in the stream with summary, topics, category.

**M3: Curate (Day 3-4)**
- Scoring, reason + evidence, highlight vs. collapse, Skipped group, cold-start behavior, session summary. This is the core of the demo.

**M4: Learn from behavior (Day 4-5)**
- Dwell and quick-action signals, interest model with decay and versioning, interest strip, visible re-ranking shift. Show before/after.

**M5: Audio + Categorize button (Day 5-6)**
- Tab audio chunks -> Voice Transcribe merged into ItemCards; Categorize toggle with live lanes.

**M6: Polish + demo (Day 6-7)**
- Loading/error states, rate-limit handling, privacy copy, clear-session, `docs/demo-script.md`, record the 3-minute video, public-repo checklist (no secrets, license, README with setup + architecture + what was built during the hackathon).

**Stretch**: SAM 3.1 post-region cropping; open-weight model switch; Muse Image cover for the session digest.

If time runs short, cut audio and lanes before cutting the learning loop or the demo polish.

## 15. Acceptance criteria for v1

- A fresh clone runs with `make dev` after setting one env var.
- Start Sift, share a tab running the Demo Feed, scroll, and see items appear in the curated stream within a few seconds each, with category, reason, and evidence.
- Dwell and save/hide actions visibly change topic weights and later ranking.
- Low-value items collapse into a Skipped group that can be expanded.
- Stopping the share stops all capture immediately; "Clear session" removes stored items.
- No non-Meta model calls anywhere (grep for other providers' SDKs returns nothing).
- No code path that scrapes, automates, or injects into a third-party platform.
- README states clearly that all code was written during the hackathon.
- Tests: scene-change detection on recorded fixtures, JSON validation/retry, dedup cache, interest-model update math, queue backpressure (client mocked).

## 16. Demo flow (3 minutes)

1. (0:00) Pitch: "Your feed is optimized for the platform. Sift is optimized for you." Show two windows side by side: a feed and Sift.
2. (0:20) Click Start, share the tab, begin scrolling. Items appear in Sift with reasons.
3. (1:00) Point out collapsed "Skipped" items and expand one to show why it was filtered.
4. (1:30) Spend time on a topic, save two items, hide one; show the interest strip shift and the stream re-prioritize.
5. (2:10) Flip the Categorize toggle; items regroup into live lanes.
6. (2:40) Show the session digest, the Meta models used, and the open-source repo. Close with the tagline.

## 17. Working rules for Claude Code

- Plan before coding each milestone; small changes, frequent commits with clear messages.
- Never hardcode secrets; never log API keys.
- All Meta calls go through `meta_client.py` and are mocked in tests.
- If a Meta API capability is unclear, check the docs or ask rather than assuming.
- Do not add dependencies for non-Meta AI providers.
- Do not write code that reads, injects into, or automates any third-party site. Capture is screen-share only.
- Do not persist raw frames or audio; keep derived data only, session-scoped.
- Keep a short changelog of what was built when, to support the "built during the hackathon" requirement.
