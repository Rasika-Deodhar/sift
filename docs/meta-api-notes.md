# Meta Model API notes

Recorded on 2026-10-29 (hackathon day 3) before writing `backend/app/meta_client.py`.

> **How these notes were gathered.** The build environment's network policy blocks the docs hosts
> (`dev.meta.ai`, `developer.meta.com`), so the pages could not be opened directly. The facts
> below come from search-engine extracts of the official pages (Overview, Quickstart, Models,
> Image understanding, Chat completion, Speech to text, SAM, Pricing and rate limits). Items
> marked **[verify]** come from secondary sources or were ambiguous, and must be checked against
> the live docs with a real key before the demo. Every one of them is a config value or an
> isolated function in `meta_client.py`, so fixing one is a one-line change.

## Base URL and auth

| Item | Value | Source |
|---|---|---|
| Base URL | `https://api.meta.ai/v1` | Quickstart |
| Auth | `Authorization: Bearer $MODEL_API_KEY` | Quickstart |
| Wire format | OpenAI-compatible (Chat Completions at `/v1/chat/completions`; Responses at `/v1/responses`). The OpenAI SDK works with a changed base URL. | Quickstart, Chat completion, SAM pages |
| Anthropic-format | A Messages-compatible endpoint exists at `https://api.meta.ai` (for coding harnesses). Sift does not use it. | Quickstart |

Sift talks to the API with plain `httpx` (no third-party AI SDK), so `grep` for other providers'
SDKs stays empty.

## Model IDs

| Use in Sift | Model ID | Notes |
|---|---|---|
| Vision understanding of a post (frames -> ItemCard JSON) | `muse-spark-1.3` | Newest; recommended for new work. 1,048,576-token context. Text, image, video, PDF input. |
| Text calls (refine card with transcript, lane naming) | `muse-spark-1.3` | Same model. |
| Fallback / audio understanding | `muse-spark-1.2` | Docs say audio understanding on 1.3 is "not fully supported"; 1.2 suggested for audio. Sift sends audio to Voice Transcribe instead, so this is not needed. |
| Speech to text | `muse-voice-transcribe-1.0` | See below. |
| Segmentation (stretch) | `sam-3.1` | Via `/v1/responses`. |
| Open-weight (optional bonus) | `meta-models/muse-spark-open-1026` on Baseten | Hackathon rule: use this exact name, not the one in Meta's docs. Baseten base URL `https://inference.baseten.co/v1` **[verify]**. |

Other listed variants: `muse-spark-1.3-contributor`, `muse-spark-1.2-contributor` (contributor
mode, lower RPM), `muse-spark-1.1` (older; some Overview/blog examples still show it).

## Image input

- Chat Completions accepts OpenAI-style content parts: `{"type": "image_url", "image_url": {"url": ...}}`.
  The URL may be a `data:image/jpeg;base64,...` data URL (shown in Meta's blog example).
- Docs recommend the Responses API for images and files; Chat Completions also works. Sift uses
  Chat Completions because it is the simplest wire format with structured output.
- Max image size / dimensions: **not found [verify]**. Sift downsizes frames client-side to at most
  768 px on the long edge as JPEG quality 0.7 (typically 40-90 KB), well under any plausible limit.

## Structured output

- Muse Spark supports structured output. Secondary sources and one working third-party client
  use `response_format: {"type": "json_schema", "json_schema": {"name", "schema", "strict": true}}`
  **[verify]**. JSON mode (`{"type": "json_object"}`) is described as separate from schema
  enforcement.
- Sift sends `json_schema`; if the API rejects the parameter (HTTP 400) the client retries the
  same request once with `json_object`, and always validates the result with Pydantic and retries
  once on invalid output (plan section 10.1).

## Speech to text (Muse Voice Transcribe)

- File endpoint: `POST https://api.meta.ai/v1/asr/transcribe` (multipart, `Authorization` header).
- Realtime: `wss://api.meta.ai/v1/asr/realtime` (not used in v1).
- Multipart layout **[verify]**: a `request` part with JSON settings (`model`, `audioEncoding: "WAV"`,
  mode) and an `audio` part with the WAV file. Response JSON has `transcript` (also `sessionId`,
  `audioDurationMs`, `turns`).
- Audio: mono 16-bit PCM WAV at 16 kHz or 24 kHz; file up to 10 minutes, body up to 32 MB
  **[verify]**. Sift encodes 16 kHz mono WAV in the browser, in 8-second chunks (~256 KB).
- Price: $3.00 per 1,000 minutes.

## SAM 3.1 (stretch)

- `POST /v1/responses` with `model: "sam-3.1"`, an image (or video) and a short noun-phrase
  prompt ("main post"). Returns a box and mask per match. 3,000 RPM; $2.50 per 1,000 images.

## Rate limits and latency

- Limits are **per team**, not per key, and per model.
- `muse-spark-1.3` (and 1.2, 1.1): 3,000 RPM, 4,000,000 TPM. Contributor variants: 150 RPM.
- `sam-3.1`: 3,000 RPM, no TPM limit.
- Latency: Meta publishes no latency figures. Sift budgets ~2-6 s per vision call, runs 3
  concurrent workers, and drops stale items (see `pipeline/queue.py`). 429 responses are retried
  with exponential backoff honoring `Retry-After`.

## Source pages (to re-check with network access)

- https://dev.meta.ai/docs/overview
- https://dev.meta.ai/docs/quickstart
- https://dev.meta.ai/docs/models
- https://dev.meta.ai/docs/image-understanding
- https://dev.meta.ai/docs/protocols/chat-completions
- https://dev.meta.ai/docs/speech-to-text
- https://dev.meta.ai/docs/sam/overview
- https://dev.meta.ai/docs/pricing-rate-limits
