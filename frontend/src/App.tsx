import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, StreamSocket, type ServerMessage } from "./api";
import { CaptureSession } from "./capture/captureSession";
import Controls from "./components/Controls";
import CategoryLanes from "./components/CategoryLanes";
import CuratedStream from "./components/CuratedStream";
import InterestStrip from "./components/InterestStrip";
import SessionSummary from "./components/SessionSummary";
import { initialState, reducer, type Action } from "./store";
import type { UiItem } from "./types";

type SignalType = "save" | "hide" | "more_like_this" | "less_like_this";

function toAction(m: ServerMessage): Action | null {
  switch (m.type) {
    case "hello":
      return {
        type: "hydrate",
        items: m.items.map(
          (i): UiItem => ({
            id: i.id,
            thumb: i.thumb,
            firstSeenAt: i.first_seen_at,
            dwellMs: i.dwell_ms,
            visits: 1,
            status: i.status,
            duplicateOf: i.duplicate_of,
          }),
        ),
        cards: m.cards,
        interest: m.interest,
      };
    case "item_status":
      return { type: "status", id: m.item_id, status: m.status, error: m.error ?? undefined, duplicateOf: m.duplicate_of };
    case "item_card":
      return { type: "card", card: m.card, status: m.status };
    case "item_update":
      return { type: "rerank", card: m.card, prevScore: m.prev_score };
    case "interest_update":
      return { type: "interest", model: m.model, cause: m.cause, changes: m.changes };
    case "cleared":
      return { type: "reset" };
    default:
      return null;
  }
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [sharing, setSharing] = useState(false);
  const [connected, setConnected] = useState(false);
  const [server, setServer] = useState<{ mock: boolean; modelReady: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSummary, setShowSummary] = useState(false);
  const [lanes, setLanes] = useState(false);
  const capture = useRef<CaptureSession | null>(null);
  const socket = useRef<StreamSocket | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const [, force] = useState(0);

  useEffect(() => {
    const s = new StreamSocket();
    s.onStatus = setConnected;
    s.onMessage = (m) => {
      if (m.type === "hello") setServer({ mock: m.mock, modelReady: m.model_ready });
      if (m.type === "error") setError(m.message);
      const a = toAction(m);
      if (a) dispatch(a);
    };
    s.connect();
    socket.current = s;
    return () => s.close();
  }, []);

  // Re-render twice a second while sharing so live dwell counters move.
  useEffect(() => {
    if (!sharing) return;
    const id = setInterval(() => force((n) => n + 1), 500);
    return () => clearInterval(id);
  }, [sharing]);

  const start = useCallback(async ({ audio, focusHint }: { audio: boolean; focusHint: string }) => {
    setError(null);
    const send = (m: Parameters<StreamSocket["send"]>[0]) => socket.current?.send(m);
    try {
      const s = await CaptureSession.start(
        { audio },
        {
          onItemEnter: (e) => {
            if (!e.isNew) {
              dispatch({ type: "revisit", id: e.itemId });
              return;
            }
            dispatch({ type: "detected", id: e.itemId, thumb: e.thumb, at: e.at });
            if (e.frame) {
              send({ type: "item_frames", item_id: e.itemId, phash: e.phash, sig: e.sig, frames: [e.frame], thumb: e.thumb, seen_at: e.at });
            }
          },
          onItemLeave: (e) => {
            dispatch({ type: "dwell", id: e.itemId, dwellMs: e.dwellMs });
            send({ type: "dwell", item_id: e.itemId, dwell_ms: Math.round(e.dwellMs) });
          },
          onAudioChunk: (e) => send({ type: "audio_chunk", item_id: e.itemId, wav: e.wav }),
          onMidFrame: (e) => send({ type: "item_frames", item_id: e.itemId, phash: "", frames: [e.frame], extra: true }),
          onEnded: () => {
            capture.current = null;
            previewRef.current?.replaceChildren();
            setSharing(false);
            api.stopSession().catch(() => {});
            setShowSummary(true);
          },
        },
        async () => {
          dispatch({ type: "reset" });
          await api.startSession(focusHint, audio);
        },
      );
      capture.current = s;
      s.sampler.video.className = "preview-video";
      previewRef.current?.replaceChildren(s.sampler.video);
      setSharing(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(/Permission|NotAllowed/i.test(msg) ? "Sharing was cancelled." : msg);
    }
  }, []);

  const stop = useCallback(() => capture.current?.stop(), []);
  const clear = useCallback(async () => {
    capture.current?.stop();
    dispatch({ type: "reset" });
    await api.clearSession().catch((e) => setError(String(e)));
  }, []);

  const onSignal = useCallback((id: string, type: SignalType) => {
    dispatch({ type: "action", id, action: type });
    socket.current?.send({ type: "signal", item_id: id, signal: type });
  }, []);

  const liveId = capture.current?.currentItemId ?? null;
  const items = state.order.map((id) => state.items[id]).reverse();
  const liveDwell = (id: string) => capture.current?.liveDwell(id) ?? state.items[id]?.dwellMs ?? 0;

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="logo">Sift</span>
          <span className="tagline">Your feed is optimized for the platform. Sift is optimized for you.</span>
          {server?.mock && <span className="chip mock" title="SIFT_MOCK_META=true: fake model output">MOCK MODEL</span>}
          {!connected && <span className="chip warn">reconnecting…</span>}
        </div>
        <Controls
          sharing={sharing}
          hasAudio={capture.current?.hasAudio ?? false}
          onStart={start}
          onStop={stop}
          onClear={clear}
        />
      </header>
      {server && !server.modelReady && (
        <div className="banner error">
          The backend has no <code>MODEL_API_KEY</code>. Capture works, but items will not be analyzed. Set it in <code>.env</code> and restart.
        </div>
      )}
      {error && <div className="banner error" onClick={() => setError(null)}>{error}</div>}
      <div className="layout">
        <aside className="side">
          <div className="preview">
            {/* The capture <video> is attached imperatively; React owns no children of this div. */}
            <div className="preview-slot" ref={previewRef} />
            {!sharing && <p className="muted">Live preview appears here while sharing.</p>}
          </div>
          <StatsPanel items={items} />
          <button className="btn" disabled={items.length === 0} onClick={() => setShowSummary(true)}>
            Session digest
          </button>
        </aside>
        <main className="stream">
          <InterestStrip interest={state.interest} lastChange={state.lastChange} />
          <div className="stream-bar">
            <span className="muted small">{lanes ? "Grouped by category" : "Curated stream"}</span>
            <button
              className={`btn small ${lanes ? "on" : ""}`}
              aria-pressed={lanes}
              onClick={() => setLanes((v) => !v)}
            >
              Categorize
            </button>
          </div>
          {lanes ? (
            <CategoryLanes items={items} liveId={liveId} liveDwell={liveDwell} onSignal={onSignal} />
          ) : (
            <CuratedStream items={items} liveId={liveId} liveDwell={liveDwell} onSignal={onSignal} />
          )}
        </main>
      </div>
      {showSummary && <SessionSummary onClose={() => setShowSummary(false)} />}
    </div>
  );
}

function StatsPanel({ items }: { items: UiItem[] }) {
  const analyzed = items.filter((i) => i.card);
  const picks = analyzed.filter((i) => i.card!.tier === "highlight").length;
  const skipped = analyzed.filter((i) => i.card!.tier === "skipped" || i.userAction === "hide").length;
  const working = items.filter((i) => i.status === "queued" || i.status === "processing").length;
  return (
    <div className="panel stats-panel">
      <div className="stats">
        <div className="stat"><div className="n">{items.length}</div><div className="muted small">seen</div></div>
        <div className="stat"><div className="n">{picks}</div><div className="muted small">picks</div></div>
        <div className="stat"><div className="n">{skipped}</div><div className="muted small">skipped</div></div>
      </div>
      {working > 0 && <p className="muted small working">Understanding {working} item{working > 1 ? "s" : ""} with Muse Spark…</p>}
    </div>
  );
}
