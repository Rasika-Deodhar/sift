import json

import httpx
import pytest

from app.config import Settings
from app.meta_client import MetaAPIError, MetaClient, decode_data_url, parse_json_content

from .conftest import TINY_JPEG, good_result


def make(handler, **env):
    s = Settings(MODEL_API_KEY="test-key", **env)
    return MetaClient(s, transport=httpx.MockTransport(handler))


def chat_reply(obj) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(obj)}}]})


async def test_understand_sends_images_schema_and_auth():
    captured = {}

    def handler(req: httpx.Request):
        captured["url"] = str(req.url)
        captured["auth"] = req.headers["authorization"]
        captured["body"] = json.loads(req.content)
        return chat_reply(good_result())

    c = make(handler)
    out = await c.understand_item([TINY_JPEG, TINY_JPEG], "describe", {"type": "object"}, "sys")
    await c.aclose()
    assert out["format"] == "tutorial"
    assert captured["url"] == "https://api.meta.ai/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    body = captured["body"]
    assert body["model"] == "muse-spark-1.3"
    assert body["response_format"]["type"] == "json_schema"
    user = body["messages"][1]["content"]
    assert [p["type"] for p in user] == ["text", "image_url", "image_url"]


async def test_falls_back_to_json_object_when_schema_rejected():
    formats = []

    def handler(req):
        body = json.loads(req.content)
        formats.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": "unsupported response_format"})
        return chat_reply(good_result())

    c = make(handler)
    await c.understand_item([TINY_JPEG], "p", {"type": "object"})
    await c.understand_item([TINY_JPEG], "p", {"type": "object"})
    await c.aclose()
    assert formats == ["json_schema", "json_object", "json_object"]


async def test_retries_rate_limit_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.meta_client.asyncio.sleep", no_sleep)

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "1"})
        return chat_reply(good_result())

    c = make(handler)
    assert (await c.understand_item([TINY_JPEG], "p"))["summary"]
    await c.aclose()
    assert calls["n"] == 3


async def test_error_does_not_leak_key():
    c = make(lambda req: httpx.Response(401, text="bad key"))
    with pytest.raises(MetaAPIError) as e:
        await c.text_complete("s", "u")
    await c.aclose()
    assert "test-key" not in str(e.value)


async def test_transcribe_multipart_and_parse():
    captured = {}

    def handler(req: httpx.Request):
        captured["url"] = str(req.url)
        captured["body"] = req.content
        return httpx.Response(200, json={"sessionId": "s", "transcript": " hi there "})

    c = make(handler)
    assert await c.transcribe(b"RIFF....WAVE") == "hi there"
    await c.aclose()
    assert captured["url"].endswith("/v1/asr/transcribe")
    assert b'name="audio"' in captured["body"] and b"muse-voice-transcribe-1.0" in captured["body"]


async def test_open_weight_text_routes_to_baseten():
    urls = []

    def handler(req):
        urls.append((str(req.url), json.loads(req.content)["model"]))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    c = make(handler, SIFT_OPEN_WEIGHT_TEXT=True, BASETEN_API_KEY="bk")
    assert await c.text_complete("s", "u") == "ok"
    await c.aclose()
    assert urls == [("https://inference.baseten.co/v1/chat/completions",
                     "meta-models/muse-spark-open-1026")]


def test_parse_json_content_variants():
    assert parse_json_content('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_content('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        parse_json_content("no json here")


def test_decode_data_url_limits():
    assert decode_data_url(TINY_JPEG, 100).startswith(b"\xff\xd8")
    with pytest.raises(ValueError):
        decode_data_url(TINY_JPEG, 2)
    with pytest.raises(ValueError):
        decode_data_url("http://example.com/x.jpg", 100)
