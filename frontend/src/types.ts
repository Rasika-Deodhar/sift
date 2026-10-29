export type ItemStatus =
  | "detected"
  | "queued"
  | "processing"
  | "ready"
  | "deduped"
  | "dropped"
  | "error";

export type Tier = "highlight" | "normal" | "skipped";

export interface ItemCard {
  item_id: string;
  summary: string;
  topics: string[];
  category: string;
  format: string;
  on_screen_text: string;
  transcript: string | null;
  quality_signals: string[];
  intrinsic_quality: number;
  value_score: number;
  reason: string;
  evidence_snippet: string;
  tier: Tier;
  score_breakdown: Record<string, number>;
  fit_note: string;
}

export interface UiItem {
  id: string;
  thumb: string | null;
  firstSeenAt: number;
  dwellMs: number;
  visits: number;
  status: ItemStatus;
  card?: ItemCard;
  error?: string;
  duplicateOf?: string | null;
  userAction?: "save" | "hide" | "more_like_this" | "less_like_this";
  /** Set when a re-rank moved this item; cleared after a few seconds by the UI. */
  moved?: { from: number; to: number; at: number };
}

export interface InterestModel {
  version: number;
  topic_weights: Record<string, number>;
  format_weights: Record<string, number>;
  focus_hint: string[];
  updated_at: number;
}

export const CATEGORIES = [
  "Tutorials & How-to",
  "News & Updates",
  "Opinion & Discussion",
  "Humor",
  "Inspiration",
  "Product & Promo",
  "Other",
] as const;
