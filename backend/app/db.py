"""Session-scoped SQLite storage for derived data only.

Raw frames and audio are never written here. We keep item metadata, derived item cards,
an optional small thumbnail, behavior signals and interest-model versions. Everything is
deleted by `clear_all()` (the "Clear session" button).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from .models import InterestModel, Item, ItemCard, ItemStatus, Session, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  started_at INTEGER NOT NULL,
  stopped_at INTEGER,
  consent_acknowledged INTEGER NOT NULL DEFAULT 0,
  settings TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  phash TEXT NOT NULL,
  first_seen_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  dwell_ms INTEGER NOT NULL DEFAULT 0,
  thumb TEXT,
  status TEXT NOT NULL,
  duplicate_of TEXT
);
CREATE TABLE IF NOT EXISTS item_cards (
  item_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  card TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  type TEXT NOT NULL,
  value REAL NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS interest_versions (
  session_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  model TEXT NOT NULL,
  cause TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (session_id, version)
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        self._conn.close()

    # --- sessions ---
    def insert_session(self, s: Session) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?)",
                (s.id, s.started_at, s.stopped_at, int(s.consent_acknowledged),
                 json.dumps(s.settings)),
            )

    def stop_session(self, session_id: str, stopped_at: int) -> None:
        with self._tx() as c:
            c.execute("UPDATE sessions SET stopped_at=? WHERE id=?", (stopped_at, session_id))

    def get_session(self, session_id: str) -> Session | None:
        with self._tx() as c:
            r = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if r is None:
            return None
        return Session(
            id=r["id"], started_at=r["started_at"], stopped_at=r["stopped_at"],
            consent_acknowledged=bool(r["consent_acknowledged"]),
            settings=json.loads(r["settings"]),
        )

    # --- items ---
    def upsert_item(self, it: Item) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET last_seen_at=excluded.last_seen_at,
                     dwell_ms=excluded.dwell_ms, thumb=COALESCE(excluded.thumb, items.thumb),
                     status=excluded.status, duplicate_of=excluded.duplicate_of""",
                (it.id, it.session_id, it.phash, it.first_seen_at, it.last_seen_at, it.dwell_ms,
                 it.thumb, it.status.value, it.duplicate_of),
            )

    def get_item(self, item_id: str) -> Item | None:
        with self._tx() as c:
            r = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        return _row_to_item(r) if r else None

    def list_items(self, session_id: str) -> list[Item]:
        with self._tx() as c:
            rows = c.execute(
                "SELECT * FROM items WHERE session_id=? ORDER BY first_seen_at", (session_id,)
            ).fetchall()
        return [_row_to_item(r) for r in rows]

    def set_item_status(self, item_id: str, status: ItemStatus) -> None:
        with self._tx() as c:
            c.execute("UPDATE items SET status=? WHERE id=?", (status.value, item_id))

    # --- cards ---
    def save_card(self, session_id: str, card: ItemCard, updated_at: int) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO item_cards VALUES (?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET card=excluded.card,
                     updated_at=excluded.updated_at""",
                (card.item_id, session_id, card.model_dump_json(), updated_at),
            )

    def get_card(self, item_id: str) -> ItemCard | None:
        with self._tx() as c:
            r = c.execute("SELECT card FROM item_cards WHERE item_id=?", (item_id,)).fetchone()
        return ItemCard.model_validate_json(r["card"]) if r else None

    def list_cards(self, session_id: str) -> list[ItemCard]:
        with self._tx() as c:
            rows = c.execute(
                "SELECT card FROM item_cards WHERE session_id=? ORDER BY updated_at",
                (session_id,),
            ).fetchall()
        return [ItemCard.model_validate_json(r["card"]) for r in rows]

    # --- signals ---
    def add_signal(self, session_id: str, s: Signal) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO signals (session_id,item_id,type,value,created_at) VALUES (?,?,?,?,?)",
                (session_id, s.item_id, s.type.value, s.value, s.created_at),
            )

    def list_signals(self, session_id: str) -> list[Signal]:
        with self._tx() as c:
            rows = c.execute(
                "SELECT * FROM signals WHERE session_id=? ORDER BY id", (session_id,)
            ).fetchall()
        return [
            Signal(item_id=r["item_id"], type=r["type"], value=r["value"],
                   created_at=r["created_at"])
            for r in rows
        ]

    # --- interest versions ---
    def save_interest_version(
        self, session_id: str, model: InterestModel, cause: str | None
    ) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO interest_versions VALUES (?,?,?,?,?)",
                (session_id, model.version, model.model_dump_json(), cause, model.updated_at),
            )

    def list_interest_versions(self, session_id: str) -> list[tuple[InterestModel, str | None]]:
        with self._tx() as c:
            rows = c.execute(
                "SELECT model, cause FROM interest_versions WHERE session_id=? ORDER BY version",
                (session_id,),
            ).fetchall()
        return [(InterestModel.model_validate_json(r["model"]), r["cause"]) for r in rows]

    # --- privacy ---
    def clear_all(self) -> None:
        with self._tx() as c:
            for t in ("item_cards", "items", "signals", "interest_versions", "sessions"):
                c.execute(f"DELETE FROM {t}")
        with self._lock:
            self._conn.execute("VACUUM")


def _row_to_item(r: sqlite3.Row) -> Item:
    return Item(
        id=r["id"], session_id=r["session_id"], phash=r["phash"],
        first_seen_at=r["first_seen_at"], last_seen_at=r["last_seen_at"], dwell_ms=r["dwell_ms"],
        thumb=r["thumb"], status=ItemStatus(r["status"]), duplicate_of=r["duplicate_of"],
    )
