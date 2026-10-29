"""The single seam for every Meta Model API call.

All model names and endpoints come from config (see docs/meta-api-notes.md). Uses plain httpx
against Meta's OpenAI-compatible endpoints, so no third-party AI SDK is involved. Tests replace
this client with a fake; nothing else in the app talks to a model.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import re
from typing import Any, Protocol

import httpx

from .config import Settings

log = logging.getLogger("sift.meta")


class MetaAPIError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RateLimited(MetaAPIError):
    pass


class ModelClient(Protocol):
    """What the pipeline needs from a model provider. Implemented by MetaClient and fakes."""

    mock: bool

    async def understand_item(
        self, frames: list[str], prompt: str, json_schema: dict | None = None,
        system: str | None = None,
    ) -> dict: ...

    async def transcribe(self, audio_wav: bytes) -> str: ...

    async def text_complete(
        self, system: str, user: str, json_schema: dict | None = None
    ) -> dict | str: ...

    async def aclose(self) -> None: ...


def parse_json_content(content: str) -> dict:
    """Parses a model's JSON answer, tolerating code fences or leading prose."""
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in model output")
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


class MetaClient:
    mock = False

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        if settings.model_api_key is None:
            raise MetaAPIError("MODEL_API_KEY is not set")
        self.s = settings
        self._http = httpx.AsyncClient(
            base_url=settings.meta_base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {settings.model_api_key.get_secret_value()}"},
            timeout=settings.request_timeout_s,
            transport=transport,
        )
        self._text_http: httpx.AsyncClient | None = None
        if settings.open_weight_text and settings.baseten_api_key is not None:
            self._text_http = httpx.AsyncClient(
                base_url=settings.baseten_base_url.rstrip("/") + "/",
                headers={"Authorization": f"Api-Key {settings.baseten_api_key.get_secret_value()}"},
                timeout=settings.request_timeout_s,
                transport=transport,
            )
        # Some deployments may not accept strict json_schema; remember and fall back to JSON mode.
        self._json_schema_ok = True

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._text_http:
            await self._text_http.aclose()

    # --- low level -----------------------------------------------------------------------

    async def _post(
        self, http: httpx.AsyncClient, path: str, *, json_body: dict | None = None,
        files: Any = None, attempts: int = 4,
    ) -> dict:
        delay = 1.0
        for attempt in range(attempts):
            try:
                r = await http.post(path, json=json_body, files=files)
            except httpx.TransportError as e:
                if attempt == attempts - 1:
                    raise MetaAPIError(f"network error calling {path}: {e}") from e
                await asyncio.sleep(delay + random.random() * 0.3)
                delay *= 2
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == attempts - 1:
                    cls = RateLimited if r.status_code == 429 else MetaAPIError
                    raise cls(f"{path} returned {r.status_code}", r.status_code)
                retry_after = r.headers.get("retry-after")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                log.warning("meta %s -> %s, retrying in %.1fs", path, r.status_code, wait)
                await asyncio.sleep(wait + random.random() * 0.3)
                delay *= 2
                continue
            if r.status_code >= 400:
                # Never include request headers (API key) in errors.
                raise MetaAPIError(
                    f"{path} returned {r.status_code}: {r.text[:300]}", r.status_code
                )
            return r.json()
        raise MetaAPIError(f"{path}: retries exhausted")

    async def _chat(
        self, messages: list[dict], model: str, json_schema: dict | None,
        http: httpx.AsyncClient | None = None, max_tokens: int = 700,
    ) -> str:
        http = http or self._http
        body: dict[str, Any] = {
            "model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens,
        }
        if json_schema is not None:
            if self._json_schema_ok:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "sift_output", "schema": json_schema, "strict": True},
                }
            else:
                body["response_format"] = {"type": "json_object"}
        try:
            data = await self._post(http, "chat/completions", json_body=body)
        except MetaAPIError as e:
            if e.status == 400 and json_schema is not None and self._json_schema_ok:
                log.warning("json_schema response_format rejected; falling back to json_object")
                self._json_schema_ok = False
                return await self._chat(messages, model, json_schema, http, max_tokens)
            raise
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise MetaAPIError("unexpected chat completion shape") from e

    # --- public API (plan section 9) -----------------------------------------------------

    async def understand_item(
        self, frames: list[str], prompt: str, json_schema: dict | None = None,
        system: str | None = None,
    ) -> dict:
        """Muse Spark vision: 1-3 JPEG data-URL frames + prompt -> structured JSON."""
        content: list[dict] = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url", "image_url": {"url": f}} for f in frames]
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": content}
        ]
        return parse_json_content(await self._chat(messages, self.s.vision_model, json_schema))

    async def text_complete(
        self, system: str, user: str, json_schema: dict | None = None
    ) -> dict | str:
        """Muse Spark text (or Muse Spark Open on Baseten when SIFT_OPEN_WEIGHT_TEXT=true)."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if self._text_http is not None:
            out = await self._chat(messages, self.s.open_weight_model, json_schema, self._text_http)
        else:
            out = await self._chat(messages, self.s.text_model, json_schema)
        return parse_json_content(out) if json_schema is not None else out

    async def transcribe(self, audio_wav: bytes) -> str:
        """Muse Voice Transcribe file endpoint: 16 kHz mono 16-bit WAV -> transcript text."""
        request = {"model": self.s.transcribe_model, "audioEncoding": "WAV"}
        files = {
            "request": (None, json.dumps(request), "application/json"),
            "audio": ("chunk.wav", audio_wav, "audio/wav"),
        }
        data = await self._post(self._http, "asr/transcribe", files=files, attempts=3)
        text = data.get("transcript") or data.get("text") or ""
        if not text and isinstance(data.get("turns"), list):
            text = " ".join(t.get("transcript", "") for t in data["turns"] if isinstance(t, dict))
        return str(text).strip()

    async def segment(self, image_data_url: str, concept: str) -> list[dict]:
        """SAM 3.1 via the Responses API: returns [{box: [x0,y0,x1,y1], score}] (stretch)."""
        body = {
            "model": self.s.segment_model,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }],
        }
        data = await self._post(self._http, "responses", json_body=body)
        boxes: list[dict] = []
        for out in data.get("output", []):
            for c in out.get("content", []) if isinstance(out, dict) else []:
                for m in c.get("masks", []) or c.get("objects", []) or []:
                    if "box" in m:
                        boxes.append({"box": m["box"], "score": m.get("score")})
        return boxes


class MockMetaClient:
    """Deterministic offline stand-in for local development (SIFT_MOCK_META=true).

    It cannot see images; it derives fake but stable output from a hash of the frame so the UI
    and pipeline can be exercised without a key. The UI shows a MOCK badge when this is active.
    """

    mock = True
    _TOPICS = ["cycling", "cooking", "ai", "photography", "gardening", "travel", "music", "humor"]
    _FORMATS = ["tutorial", "news", "opinion", "humor", "inspiration", "promo"]
    _CAT = {"tutorial": "Tutorials & How-to", "news": "News & Updates",
            "opinion": "Opinion & Discussion", "humor": "Humor", "inspiration": "Inspiration",
            "promo": "Product & Promo"}

    def __init__(self, latency_s: float = 0.8) -> None:
        self.latency_s = latency_s

    async def aclose(self) -> None:
        return None

    async def understand_item(
        self, frames: list[str], prompt: str, json_schema: dict | None = None,
        system: str | None = None,
    ) -> dict:
        await asyncio.sleep(self.latency_s)
        h = int(hashlib.sha256(frames[0].encode()).hexdigest(), 16)
        topic = self._TOPICS[h % len(self._TOPICS)]
        fmt = self._FORMATS[(h >> 8) % len(self._FORMATS)]
        q = 2 + (h >> 16) % 8
        return {
            "is_post": True,
            "summary": f"[mock] A {fmt} post about {topic}.",
            "topics": [topic, self._TOPICS[(h >> 24) % len(self._TOPICS)]],
            "format": fmt,
            "category": self._CAT[fmt],
            "on_screen_text": "",
            "quality_signals": ["mock output"],
            "intrinsic_quality": q,
            "reason": f"[mock] {fmt.title()} on {topic}.",
            "evidence_snippet": "",
        }

    async def text_complete(
        self, system: str, user: str, json_schema: dict | None = None
    ) -> dict | str:
        await asyncio.sleep(self.latency_s / 2)
        return {} if json_schema is not None else "[mock]"

    async def transcribe(self, audio_wav: bytes) -> str:
        await asyncio.sleep(self.latency_s / 2)
        return f"[mock transcript of {len(audio_wav) // 32000}s of audio]"


def make_client(settings: Settings) -> ModelClient | None:
    if settings.mock_meta:
        return MockMetaClient()
    if settings.model_api_key is None:
        return None
    return MetaClient(settings)


def decode_data_url(url: str, max_bytes: int) -> bytes:
    """Validates a base64 data URL (image or audio) and returns its bytes."""
    m = re.match(r"^data:([\w/+.-]+);base64,(.*)$", url, re.S)
    if not m:
        raise ValueError("not a base64 data URL")
    raw = base64.b64decode(m.group(2), validate=False)
    if len(raw) > max_bytes:
        raise ValueError("payload too large")
    return raw
