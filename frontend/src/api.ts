// REST + WebSocket client for the Sift backend (proxied by Vite under /api and /stream).

import type { InterestModel, ItemCard, ItemStatus } from "./types";

export type ServerMessage =
  | {
      type: "hello";
      mock: boolean;
      model_ready: boolean;
      session: { id: string; stopped_at: number | null } | null;
      items: { id: string; thumb: string | null; first_seen_at: number; dwell_ms: number; status: ItemStatus; duplicate_of: string | null }[];
      cards: ItemCard[];
      interest: InterestModel;
    }
  | { type: "session"; session: { id: string; stopped_at: number | null } }
  | { type: "item_status"; item_id: string; status: ItemStatus; duplicate_of?: string | null; error?: string | null; pipeline?: PipelineStats }
  | { type: "item_card"; card: ItemCard; status: ItemStatus; duplicate_of?: string | null }
  | { type: "item_update"; card: ItemCard; prev_score: number; prev_tier: string }
  | { type: "interest_update"; model: InterestModel; cause: string; changes?: InterestChange[] }
  | { type: "cleared" }
  | { type: "error"; message: string };

export interface PipelineStats {
  pending: number;
  active: number;
  dropped: number;
  processed: number;
  cache_hits: number;
}

export interface InterestChange {
  key: string;
  kind: "topic" | "format";
  before: number;
  after: number;
}

export type ClientMessage =
  | { type: "item_frames"; item_id: string; phash: string; sig?: string; frames: string[]; thumb?: string | null; seen_at?: number; extra?: boolean }
  | { type: "dwell"; item_id: string; dwell_ms: number }
  | { type: "audio_chunk"; item_id: string; wav: string }
  | { type: "signal"; item_id: string; signal: string; value?: number }
  | { type: "ping" };

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export const api = {
  startSession: (focusHint: string, audio: boolean) =>
    post<{ session: { id: string } }>("/session/start", {
      consent_acknowledged: true,
      focus_hint: focusHint || null,
      audio_enabled: audio,
    }),
  stopSession: () => post("/session/stop"),
  clearSession: () => post("/session/clear"),
  signal: (item_id: string, type: string) => post("/signal", { item_id, type }),
  summary: <T>(narrative = false) => get<T>(`/session/summary${narrative ? "?narrative=true" : ""}`),
  interestVersions: <T>() => get<T>("/interest/versions"),
  otherLaneName: () => get<{ name: string | null }>("/categories/other-name"),
  interestDiff: <T>(from: number, to: number) => get<T>(`/interest/diff?from=${from}&to=${to}`),
};

/** WebSocket with automatic reconnect and a small send buffer while disconnected. */
export class StreamSocket {
  private ws: WebSocket | null = null;
  private buffer: string[] = [];
  private closed = false;
  private retry = 500;
  onMessage: (m: ServerMessage) => void = () => {};
  onStatus: (connected: boolean) => void = () => {};

  connect(): void {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/stream`);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 500;
      this.onStatus(true);
      for (const m of this.buffer.splice(0)) ws.send(m);
    };
    ws.onmessage = (e) => this.onMessage(JSON.parse(e.data));
    ws.onclose = () => {
      this.onStatus(false);
      if (!this.closed) setTimeout(() => this.connect(), (this.retry = Math.min(this.retry * 2, 8000)));
    };
  }

  send(m: ClientMessage): void {
    const s = JSON.stringify(m);
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(s);
    // Keep only a few messages while offline; frames are big and quickly stale.
    else if (this.buffer.push(s) > 8) this.buffer.shift();
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }
}
