"""Sift FastAPI app: REST for session control, one WebSocket for the live stream."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, get_settings
from .db import Database
from .meta_client import make_client
from .models import SessionStartIn
from .session import SessionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("sift")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db = Database(settings.db_path)
    client = getattr(app.state, "client_override", None) or make_client(settings)
    if client is None:
        log.warning("MODEL_API_KEY is not set: capture works, but items will not be analyzed")
    app.state.manager = SessionManager(settings, db, client)
    yield
    await app.state.manager.shutdown()
    db.close()


app = FastAPI(title="Sift", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


def manager() -> SessionManager:
    return app.state.manager


@app.get("/health")
def health() -> dict:
    m = manager()
    return {
        "ok": True,
        "model_ready": m.client is not None,
        "mock": bool(m.client and m.client.mock),
        "queue": {"pending": m.queue.pending, "active": m.queue.active,
                  "dropped": m.queue.dropped, "processed": m.queue.processed},
        "cache": {"size": len(m.cache), "hits": m.cache.hits, "misses": m.cache.misses},
    }


@app.post("/session/start")
async def session_start(body: SessionStartIn) -> dict:
    if not body.consent_acknowledged:
        raise HTTPException(400, "consent is required before capture starts")
    s = await manager().start(True, body.focus_hint, body.audio_enabled)
    return {"session": s.model_dump()}


@app.post("/session/stop")
async def session_stop() -> dict:
    await manager().stop()
    return {"ok": True}


@app.post("/session/clear")
async def session_clear() -> dict:
    await manager().clear()
    return {"ok": True}


@app.get("/session/summary")
async def session_summary(narrative: bool = False) -> dict:
    return await manager().summary(narrative)


@app.websocket("/stream")
async def stream(ws: WebSocket) -> None:
    m = manager()
    await ws.accept()
    m.sockets.add(ws)
    try:
        await ws.send_json(m.snapshot())
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                await m.handle_message(msg)
            except (ValueError, KeyError, TypeError) as e:
                await ws.send_json({"type": "error", "message": f"bad message: {e}"[:200]})
    except WebSocketDisconnect:
        pass
    finally:
        m.sockets.discard(ws)


app.mount("/demo", StaticFiles(directory=REPO_ROOT / "demo_feed", html=True), name="demo")
