import type { UiItem } from "../types";

interface Props {
  item: UiItem;
  live: boolean;
  liveDwellMs?: number;
  onSignal?: (id: string, type: "save" | "hide" | "more_like_this" | "less_like_this") => void;
  compact?: boolean;
}

const STATUS_TEXT: Record<string, string> = {
  detected: "Detected",
  queued: "Queued",
  processing: "Understanding…",
  dropped: "Skipped analysis",
  error: "Could not analyze",
};

function scoreTitle(b: Record<string, number>): string {
  const parts = [`Value score (0-10)`, `quality ${b.quality ?? "?"}/10`];
  if (b.fit_points) parts.push(`interest fit ${b.fit_points >= 0 ? "+" : ""}${b.fit_points}`);
  if (b.novelty_penalty) parts.push(`repeat penalty -${b.novelty_penalty}`);
  return parts.join("\n");
}

export default function ItemCardView({ item, live, liveDwellMs, onSignal, compact }: Props) {
  const c = item.card;
  const dwell = ((live ? liveDwellMs ?? item.dwellMs : item.dwellMs) / 1000).toFixed(1);
  const tier = c?.tier ?? "pending";
  const moved = item.moved && Date.now() - item.moved.at < 6000 ? item.moved : null;
  return (
    <article
      data-item-id={item.id}
      className={`card tier-${tier} ${live ? "live" : ""} ${compact ? "compact" : ""} ${moved ? "moved" : ""}`}
    >
      <div className="thumb">{item.thumb ? <img src={item.thumb} alt="" /> : <div className="ph" />}</div>
      <div className="body">
        <div className="row top">
          {c ? (
            <>
              <span className="chip cat">{c.category}</span>
              <span className={`score s${Math.round(c.value_score)}`} title={scoreTitle(c.score_breakdown)}>
                {c.value_score.toFixed(1)}
              </span>
              {tier === "highlight" && <span className="chip pick">Sift pick</span>}
              {moved && (
                <span className={`chip delta ${moved.to > moved.from ? "up" : "down"}`} title="Re-ranked after your feedback">
                  {moved.to > moved.from ? "▲" : "▼"} {moved.from.toFixed(1)} → {moved.to.toFixed(1)}
                </span>
              )}
            </>
          ) : (
            <span className={`chip status ${item.status}`}>{STATUS_TEXT[item.status] ?? item.status}</span>
          )}
          <span className="meta muted small">
            {live && <b className="live-dot">● on screen </b>}
            dwell {dwell}s{item.visits > 1 ? ` · ${item.visits} visits` : ""}
            {item.status === "deduped" ? " · seen before" : ""}
          </span>
        </div>
        {c ? (
          <>
            <p className="reason">{c.reason}</p>
            {c.fit_note && <p className="fit-note">↳ {c.fit_note}</p>}
            {!compact && <p className="summary muted">{c.summary}</p>}
            {compact && <p className="summary muted small">{c.summary}</p>}
            {c.evidence_snippet && !compact && <blockquote className="evidence">“{c.evidence_snippet}”</blockquote>}
            {!compact && (
              <div className="row tags">
                {c.topics.map((t) => (
                  <span key={t} className="chip topic">{t}</span>
                ))}
                <span className="chip fmt">{c.format}</span>
                {c.transcript && <span className="chip audio" title={c.transcript}>🔊 transcript</span>}
              </div>
            )}
            {onSignal && (
              <div className="row actions">
                {(
                  [
                    ["save", "Save"],
                    ["more_like_this", "More like this"],
                    ["less_like_this", "Less like this"],
                    ["hide", "Hide"],
                  ] as const
                ).map(([k, label]) => (
                  <button
                    key={k}
                    className={`btn small ${item.userAction === k ? "on" : ""}`}
                    onClick={() => onSignal(item.id, k)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </>
        ) : (
          item.error && <p className="muted small">{item.error}</p>
        )}
      </div>
    </article>
  );
}
