from fastapi.testclient import TestClient

from .conftest import TINY_JPEG, FakeClient


def make_app(tmp_path, monkeypatch, client):
    monkeypatch.setenv("SIFT_DB", str(tmp_path / "t.db"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    app.state.client_override = client
    return app


def test_health(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch, FakeClient())
    with TestClient(app) as c:
        body = c.get("/health").json()
        assert body["ok"] is True and body["model_ready"] is True


def test_consent_required(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch, FakeClient())
    with TestClient(app) as c:
        assert c.post("/session/start", json={"consent_acknowledged": False}).status_code == 400


def test_frames_to_card_over_websocket(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch, FakeClient())
    with TestClient(app) as c:
        with c.websocket_connect("/stream") as ws:
            assert ws.receive_json()["type"] == "hello"
            c.post("/session/start", json={"consent_acknowledged": True})
            ws.send_json({"type": "item_frames", "item_id": "a1", "phash": "ab" * 32,
                          "frames": [TINY_JPEG], "thumb": TINY_JPEG})
            seen = []
            for _ in range(20):
                m = ws.receive_json()
                seen.append(m["type"])
                if m["type"] == "item_card":
                    card = m["card"]
                    break
            assert card["item_id"] == "a1"
            assert card["topics"] == ["cycling", "bike maintenance"]
            assert card["category"] == "Tutorials & How-to"
            # Clear removes everything.
            c.post("/session/clear")
            assert c.get("/health").json()["cache"]["size"] == 0
