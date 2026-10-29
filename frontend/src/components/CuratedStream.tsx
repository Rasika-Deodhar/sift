import { useState } from "react";
import type { UiItem } from "../types";
import ItemCardView from "./ItemCard";

interface Props {
  items: UiItem[]; // newest first
  liveId: string | null;
  liveDwell: (id: string) => number;
  onSignal: (id: string, type: "save" | "hide" | "more_like_this" | "less_like_this") => void;
}

/**
 * The curated stream: highlighted picks and normal items in score order within recency,
 * pending items as they are being understood, and low-value items collapsed into "Skipped".
 * Nothing is hidden permanently: the Skipped group expands to show each item and why.
 */
export default function CuratedStream({ items, liveId, liveDwell, onSignal }: Props) {
  const [showSkipped, setShowSkipped] = useState(false);
  const visible = items.filter((i) => i.card && i.card.tier !== "skipped" && i.userAction !== "hide");
  const pending = items.filter((i) => !i.card && i.status !== "dropped" && i.status !== "error");
  const failed = items.filter((i) => !i.card && (i.status === "dropped" || i.status === "error"));
  const skipped = items.filter((i) => i.card && (i.card.tier === "skipped" || i.userAction === "hide"));
  const picks = visible.filter((i) => i.card!.tier === "highlight");
  const rest = visible.filter((i) => i.card!.tier !== "highlight");
  const card = (i: UiItem, compact = false) => (
    <ItemCardView
      key={i.id}
      item={i}
      live={i.id === liveId}
      liveDwellMs={i.id === liveId ? liveDwell(i.id) : undefined}
      onSignal={onSignal}
      compact={compact}
    />
  );

  if (items.length === 0) {
    return (
      <div className="empty">
        <h3>Nothing yet</h3>
        <p className="muted">
          Press <b>Start Sift</b>, share the tab you scroll (try the <a href="/demo/" target="_blank">Demo Feed</a>),
          and scroll normally. Each post appears here within a few seconds, with a reason.
        </p>
      </div>
    );
  }

  return (
    <div className="curated">
      {pending.length > 0 && <section className="group pending">{pending.map((i) => card(i))}</section>}
      {picks.length > 0 && (
        <section className="group picks">
          <h3 className="group-title">Sift picks <span className="muted">({picks.length})</span></h3>
          {picks.map((i) => card(i))}
        </section>
      )}
      {rest.length > 0 && (
        <section className="group rest">
          {picks.length > 0 && <h3 className="group-title">Also in your feed</h3>}
          {rest.map((i) => card(i))}
        </section>
      )}
      {skipped.length > 0 && (
        <section className="group skipped">
          <button className="skipped-toggle" onClick={() => setShowSkipped((v) => !v)} aria-expanded={showSkipped}>
            {showSkipped ? "▾" : "▸"} Skipped ({skipped.length})
            <span className="muted small"> low value for you right now; expand to see why</span>
          </button>
          {showSkipped && skipped.map((i) => card(i, true))}
        </section>
      )}
      {failed.length > 0 && (
        <details className="group failed">
          <summary className="muted small">Not analyzed ({failed.length})</summary>
          {failed.map((i) => card(i, true))}
        </details>
      )}
    </div>
  );
}
