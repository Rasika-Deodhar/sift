import { useEffect, useState } from "react";
import { api } from "../api";
import { CATEGORIES, type UiItem } from "../types";
import ItemCardView from "./ItemCard";

interface Props {
  items: UiItem[];
  liveId: string | null;
  liveDwell: (id: string) => number;
  onSignal: (id: string, type: "save" | "hide" | "more_like_this" | "less_like_this") => void;
}

/** Live category lanes: counts update as you scroll; each lane collapses independently. */
export default function CategoryLanes({ items, liveId, liveDwell, onSignal }: Props) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [otherName, setOtherName] = useState<string | null>(null);
  const analyzed = items.filter((i) => i.card);
  const lanes = CATEGORIES.map((cat) => ({
    cat,
    items: analyzed
      .filter((i) => i.card!.category === cat)
      .sort((a, b) => b.card!.value_score - a.card!.value_score),
  })).filter((l) => l.items.length > 0);
  const otherCount = lanes.find((l) => l.cat === "Other")?.items.length ?? 0;

  // When "Other" grows, ask Muse Spark for a more descriptive lane name.
  useEffect(() => {
    if (otherCount >= 4) api.otherLaneName().then((r) => setOtherName(r.name), () => {});
  }, [otherCount]);

  if (lanes.length === 0) return <p className="muted">Lanes fill in as items are understood.</p>;

  return (
    <div className="lanes">
      {lanes.map(({ cat, items: laneItems }) => {
        const isCollapsed = collapsed[cat] ?? false;
        const picks = laneItems.filter((i) => i.card!.tier === "highlight").length;
        return (
          <section key={cat} className="lane" data-lane={cat}>
            <button
              className="lane-head"
              aria-expanded={!isCollapsed}
              onClick={() => setCollapsed((c) => ({ ...c, [cat]: !isCollapsed }))}
            >
              <span>{isCollapsed ? "▸" : "▾"}</span>
              <b>{cat === "Other" && otherName ? `${otherName}` : cat}</b>
              {cat === "Other" && otherName && <span className="muted small">(named by Muse Spark)</span>}
              <span className="lane-count">{laneItems.length}</span>
              {picks > 0 && <span className="chip pick">{picks} pick{picks > 1 ? "s" : ""}</span>}
            </button>
            {!isCollapsed && (
              <div className="lane-body">
                {laneItems.map((i) => (
                  <ItemCardView
                    key={i.id}
                    item={i}
                    live={i.id === liveId}
                    liveDwellMs={i.id === liveId ? liveDwell(i.id) : undefined}
                    onSignal={onSignal}
                    compact
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
