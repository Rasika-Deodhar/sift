import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { CaptureSession } from "./capture/captureSession";
import Controls from "./components/Controls";
import { initialState, reducer } from "./store";

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const capture = useRef<CaptureSession | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const [, force] = useState(0);

  // Re-render twice a second while sharing so live dwell counters move.
  useEffect(() => {
    if (!sharing) return;
    const id = setInterval(() => force((n) => n + 1), 500);
    return () => clearInterval(id);
  }, [sharing]);

  const start = useCallback(async ({ audio }: { audio: boolean; focusHint: string }) => {
    setError(null);
    try {
      const s = await CaptureSession.start(
        { audio },
        {
          onItemEnter: (e) =>
            e.isNew
              ? dispatch({ type: "detected", id: e.itemId, thumb: e.thumb, at: e.at })
              : dispatch({ type: "revisit", id: e.itemId }),
          onItemLeave: (e) => dispatch({ type: "dwell", id: e.itemId, dwellMs: e.dwellMs }),
          onMidFrame: () => {},
          onEnded: () => {
            capture.current = null;
            previewRef.current?.replaceChildren();
            setSharing(false);
          },
        },
      );
      capture.current = s;
      s.sampler.video.className = "preview-video";
      previewRef.current?.replaceChildren(s.sampler.video);
      setSharing(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const stop = useCallback(() => capture.current?.stop(), []);
  const clear = useCallback(() => {
    capture.current?.stop();
    dispatch({ type: "reset" });
  }, []);

  const liveId = capture.current?.currentItemId ?? null;
  const items = state.order.map((id) => state.items[id]).reverse();

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="logo">Sift</span>
          <span className="tagline">Your feed is optimized for the platform. Sift is optimized for you.</span>
        </div>
        <Controls
          sharing={sharing}
          hasAudio={capture.current?.hasAudio ?? false}
          onStart={start}
          onStop={stop}
          onClear={clear}
        />
      </header>
      {error && <div className="banner error">{error}</div>}
      <div className="layout">
        <aside className="side">
          <div className="preview">
            {/* The capture <video> is attached imperatively; React owns no children of this div. */}
            <div className="preview-slot" ref={previewRef} />
            {!sharing && <p className="muted">Live preview appears here while sharing.</p>}
          </div>
        </aside>
        <main className="stream">
          {items.length === 0 && <p className="muted">Start Sift and scroll your feed. Detected items appear here.</p>}
          {items.map((it) => (
            <div key={it.id} data-item-id={it.id} className={`detected ${it.id === liveId ? "live" : ""}`}>
              {it.thumb && <img src={it.thumb} alt="" />}
              <div>
                <div>Item {it.id.slice(0, 6)}</div>
                <div className="muted small">
                  seen {new Date(it.firstSeenAt).toLocaleTimeString()} · visits {it.visits} · dwell{" "}
                  {((it.id === liveId ? capture.current!.liveDwell(it.id) : it.dwellMs) / 1000).toFixed(1)}s
                </div>
              </div>
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
