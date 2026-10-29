import type { InterestModel, ItemCard, ItemStatus, UiItem } from "./types";

export interface State {
  items: Record<string, UiItem>;
  order: string[]; // first-seen order
  interest: InterestModel | null;
  prevInterest: InterestModel | null;
}

export const initialState: State = { items: {}, order: [], interest: null, prevInterest: null };

export type Action =
  | { type: "detected"; id: string; thumb: string | null; at: number }
  | { type: "revisit"; id: string }
  | { type: "dwell"; id: string; dwellMs: number }
  | { type: "status"; id: string; status: ItemStatus; error?: string; duplicateOf?: string | null }
  | { type: "card"; card: ItemCard; status?: ItemStatus }
  | { type: "action"; id: string; action: UiItem["userAction"] }
  | { type: "interest"; model: InterestModel }
  | { type: "hydrate"; items: UiItem[]; cards: ItemCard[]; interest: InterestModel | null }
  | { type: "reset" };

export function reducer(s: State, a: Action): State {
  const patch = (id: string, p: Partial<UiItem>): State =>
    s.items[id] ? { ...s, items: { ...s.items, [id]: { ...s.items[id], ...p } } } : s;
  switch (a.type) {
    case "detected":
      if (s.items[a.id]) return s;
      return {
        ...s,
        order: [...s.order, a.id],
        items: {
          ...s.items,
          [a.id]: { id: a.id, thumb: a.thumb, firstSeenAt: a.at, dwellMs: 0, visits: 1, status: "detected" },
        },
      };
    case "revisit":
      return patch(a.id, { visits: (s.items[a.id]?.visits ?? 0) + 1 });
    case "dwell":
      return patch(a.id, { dwellMs: a.dwellMs });
    case "status":
      return patch(a.id, { status: a.status, error: a.error, duplicateOf: a.duplicateOf });
    case "card": {
      const it = s.items[a.card.item_id];
      if (!it) return s;
      const status = a.status ?? (it.status === "deduped" ? "deduped" : "ready");
      return patch(a.card.item_id, { card: a.card, status });
    }
    case "hydrate": {
      const items: Record<string, UiItem> = {};
      for (const it of a.items) items[it.id] = it;
      for (const c of a.cards) if (items[c.item_id]) items[c.item_id].card = c;
      return { items, order: a.items.map((i) => i.id), interest: a.interest, prevInterest: null };
    }
    case "action":
      return patch(a.id, { userAction: a.action });
    case "interest":
      return { ...s, prevInterest: s.interest, interest: a.model };
    case "reset":
      return initialState;
  }
}
