import { useEffect, useState } from "react";
import { api } from "../api";

interface Brief {
  item_id: string;
  summary: string;
  reason: string;
  category: string;
  value_score: number;
  thumb: string | null;
}

interface Summary {
  session: { id: string } | null;
  items_seen: number;
  items_analyzed: number;
  highlighted: number;
  skipped: number;
  total_dwell_ms: number;
  time_on_skipped_ms: number;
  categories: Record<string, number>;
  top_picks: Brief[];
  skipped_items: Brief[];
  top_topics: { topic: string; weight: number }[];
  digest?: string | null;
}

export default function SessionSummary({ onClose }: { onClose: () => void }) {
  const [s, setS] = useState<Summary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.summary<Summary>(true).then(setS, (e) => setErr(String(e)));
  }, []);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" role="dialog" aria-labelledby="digest-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="digest-title">Session digest</h2>
        {err && <p className="banner error">{err}</p>}
        {!s && !err && <p className="muted">Summarizing your session with Muse Spark…</p>}
        {s && !s.session && <p className="muted">No session yet.</p>}
        {s?.session && (
          <>
            {s.digest && <p className="digest">{s.digest}</p>}
            <div className="stats">
              <Stat n={s.items_seen} label="items seen" />
              <Stat n={s.highlighted} label="Sift picks" />
              <Stat n={s.skipped} label="skipped" />
              <Stat n={`${Math.round(s.time_on_skipped_ms / 1000)}s`} label="spent on skipped items" />
            </div>
            {s.top_topics.length > 0 && (
              <p>
                <b>You leaned into:</b> {s.top_topics.map((t) => t.topic).join(", ")}
              </p>
            )}
            <div className="row tags">
              {Object.entries(s.categories).map(([k, v]) => (
                <span key={k} className="chip cat">
                  {k} · {v}
                </span>
              ))}
            </div>
            <h3>Top picks</h3>
            <ul className="brief-list">
              {s.top_picks.map((p) => (
                <li key={p.item_id}>
                  {p.thumb && <img src={p.thumb} alt="" />}
                  <div>
                    <b>{p.value_score.toFixed(1)}</b> {p.summary}
                    <div className="muted small">{p.reason}</div>
                  </div>
                </li>
              ))}
            </ul>
            {s.skipped_items.length > 0 && (
              <>
                <h3>Filtered out</h3>
                <ul className="brief-list compact">
                  {s.skipped_items.map((p) => (
                    <li key={p.item_id}>
                      <div>
                        <b>{p.value_score.toFixed(1)}</b> {p.summary}
                        <div className="muted small">{p.reason}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ n, label }: { n: number | string; label: string }) {
  return (
    <div className="stat">
      <div className="n">{n}</div>
      <div className="muted small">{label}</div>
    </div>
  );
}
