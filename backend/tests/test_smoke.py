from fastapi.testclient import TestClient


def test_health_and_ws_echo(tmp_path, monkeypatch):
    monkeypatch.setenv("SIFT_DB", str(tmp_path / "t.db"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        assert c.get("/health").json()["ok"] is True
        with c.websocket_connect("/stream") as ws:
            ws.send_json({"hello": "sift"})
            assert ws.receive_json() == {"type": "echo", "data": {"hello": "sift"}}
