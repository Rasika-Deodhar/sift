"""Sift FastAPI app."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, get_settings
from .db import Database


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = Database(get_settings().db_path)
    yield
    app.state.db.close()


app = FastAPI(title="Sift", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"ok": True, "meta_configured": s.meta_enabled, "mock": s.mock_meta}


@app.websocket("/stream")
async def stream(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            await ws.send_json({"type": "echo", "data": await ws.receive_json()})
    except WebSocketDisconnect:
        pass


app.mount("/demo", StaticFiles(directory=REPO_ROOT / "demo_feed", html=True), name="demo")
