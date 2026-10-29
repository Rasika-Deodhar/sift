import { useEffect, useState } from "react";
import { api, type InterestChange } from "../api";
import type { InterestModel } from "../types";

interface Props {
  interest: InterestModel | null;
  lastChange: { cause: string; changes: InterestChange[]; at: number } | null;
}

interface Diff {
  from: number;
  to: number;
  changes: InterestChange[];
}

/** What Sift thinks you like right now, and what just changed. */
export default function InterestStrip({ interest, lastChange }: Props) {
  const [showDiff, setShowDiff] = useState(false);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [, tick] = useState(0);

  // Let the "what changed" highlight fade after a few seconds.
  useEffect(() => {
    if (!lastChange) return;
    const id = setTimeout(() => tick((n) => n + 1), 6000);
    return () => clearTimeout(id);
  }, [lastChange]);

  useEffect(() => {
    if (showDiff && interest && interest.version > 0) {
      api.interestDiff<Diff>(0, interest.version).then(setDiff, () => setDiff(null));
    }
  }, [showDiff, interest]);

  if (!interest) return null;
  const topics = Object.entries(interest.topic_weights).sort((a, b) => b[1] - a[1]);
  const likes = topics.filter(([, w]) => w > 0.05).slice(0, 6);
  const skips = topics.filter(([, w]) => w < -0.05).slice(-3).reverse();
  const recent = lastChange && Date.now() - lastChange.at < 6000 ? lastChange : null;
  const changed = new Map(recent?.changes.map((c) => [c.key, c]) ?? []);
  const cold = likes.length === 0 && skips.length === 0;

  return (
    <section className="interest-strip panel" aria-live="polite">
      <div className="row">
        <b>Sift thinks you like</b>
        <span className="muted small">v{interest.version}</span>
        {interest.version > 0 && (
          <button className="btn small ghost" onClick={() => setShowDiff((v) => !v)}>
            {showDiff ? "Hide before/after" : "Before / after"}
          </button>
        )}
      </div>
      {cold && (
        <p className="muted small">
          {interest.focus_hint.length
            ? `Starting from your focus hint: ${interest.focus_hint.join(", ")}. `
            : "Cold start: ranking by quality and novelty. "}
          Dwell on what you like, or use Save / Hide, and this will adapt.
        </p>
      )}
      <div className="row tags">
        {likes.map(([t, w]) => (
          <span key={t} className={`chip like ${changed.has(t) ? "flash" : ""}`} title={`weight ${w.toFixed(2)}`}>
            {t} <Bar w={w} />
            {changed.has(t) && <Arrow c={changed.get(t)!} />}
          </span>
        ))}
        {skips.map(([t, w]) => (
          <span key={t} className={`chip dislike ${changed.has(t) ? "flash" : ""}`} title={`weight ${w.toFixed(2)}`}>
            less {t}
            {changed.has(t) && <Arrow c={changed.get(t)!} />}
          </span>
        ))}
      </div>
      {recent && <p className="muted small changed-cause">Updated from: {recent.cause}</p>}
      {showDiff && diff && (
        <table className="diff">
          <thead>
            <tr>
              <th>{diff.changes.length ? "Changed since session start" : "No changes yet"}</th>
              <th>before</th>
              <th>now</th>
            </tr>
          </thead>
          <tbody>
            {diff.changes.slice(0, 10).map((c) => (
              <tr key={c.kind + c.key}>
                <td>
                  {c.key} <span className="muted small">{c.kind}</span>
                </td>
                <td>{c.before.toFixed(2)}</td>
                <td className={c.after > c.before ? "up" : "down"}>{c.after.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Bar({ w }: { w: number }) {
  return <span className="bar" style={{ width: `${Math.min(40, Math.abs(w) * 20)}px` }} />;
}

function Arrow({ c }: { c: InterestChange }) {
  return <b className={c.after > c.before ? "up" : "down"}>{c.after > c.before ? " ▲" : " ▼"}</b>;
}
