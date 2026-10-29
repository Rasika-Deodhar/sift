// Perceptual hashing and scene-change detection. Pure functions over grayscale pixels so they
// can be unit-tested against recorded fixtures without a browser.

/** Size of the grayscale thumbnail the sampler produces for hashing (dHash needs W = H + 1). */
export const HASH_W = 33;
export const HASH_H = 32;
export const HASH_BITS = (HASH_W - 1) * HASH_H; // 1024

/** Difference hash: for each row, is a pixel brighter than its right neighbour? -> hex string. */
export function dHash(gray: ArrayLike<number>, w = HASH_W, h = HASH_H): string {
  let hex = "";
  let nibble = 0;
  let n = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w - 1; x++) {
      nibble = (nibble << 1) | (gray[y * w + x] > gray[y * w + x + 1] ? 1 : 0);
      if (++n % 4 === 0) {
        hex += nibble.toString(16);
        nibble = 0;
      }
    }
  }
  return hex;
}

const POPCOUNT = Array.from({ length: 16 }, (_, i) =>
  [1, 2, 4, 8].reduce((s, b) => s + (i & b ? 1 : 0), 0),
);

/** Normalized Hamming distance between two equal-length hex hashes, in [0, 1]. */
export function hashDistance(a: string, b: string): number {
  if (a.length !== b.length) return 1;
  let d = 0;
  for (let i = 0; i < a.length; i++) d += POPCOUNT[parseInt(a[i], 16) ^ parseInt(b[i], 16)];
  return d / (a.length * 4);
}

/** Mean absolute pixel difference between two grayscale thumbnails (0-255). */
export function meanAbsDiff(a: ArrayLike<number>, b: ArrayLike<number>): number {
  if (a.length !== b.length) return 255;
  let d = 0;
  for (let i = 0; i < a.length; i++) d += Math.abs(a[i] - b[i]);
  return d / a.length;
}

/**
 * Coarse color signature: the RGBA thumbnail averaged down to a `cells` x `cells` RGB grid, as
 * hex (one byte per channel). Lets the backend tell apart posts with the same layout.
 */
export function colorSignature(rgba: ArrayLike<number>, w = HASH_W, h = HASH_H, cells = 8): string {
  let hex = "";
  for (let cy = 0; cy < cells; cy++) {
    for (let cx = 0; cx < cells; cx++) {
      const x0 = Math.floor((cx * w) / cells), x1 = Math.floor(((cx + 1) * w) / cells);
      const y0 = Math.floor((cy * h) / cells), y1 = Math.floor(((cy + 1) * h) / cells);
      for (let ch = 0; ch < 3; ch++) {
        let sum = 0, n = 0;
        for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++, n++) sum += rgba[(y * w + x) * 4 + ch];
        hex += Math.round(sum / Math.max(1, n)).toString(16).padStart(2, "0");
      }
    }
  }
  return hex;
}

/**
 * Bounding box of the "content" in a thumbnail: cells that differ clearly from the background
 * color (estimated from the border). Returned as fractions of the frame, or null if the content
 * fills the frame. Used to crop thumbnails to the post instead of the page around it.
 */
export function contentBox(
  rgba: ArrayLike<number>,
  w = HASH_W,
  h = HASH_H,
  threshold = 28,
): { x: number; y: number; w: number; h: number } | null {
  const border: number[][] = [];
  for (let x = 0; x < w; x++) for (const y of [0, h - 1]) border.push(px(rgba, w, x, y));
  for (let y = 0; y < h; y++) for (const x of [0, w - 1]) border.push(px(rgba, w, x, y));
  const bg = [0, 1, 2].map((c) => median(border.map((p) => p[c])));
  const on: boolean[] = [];
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const p = px(rgba, w, x, y);
      on.push(Math.abs(p[0] - bg[0]) + Math.abs(p[1] - bg[1]) + Math.abs(p[2] - bg[2]) > threshold);
    }
  }
  // Keep columns that are mostly content (drops headers and side text), then rows that are
  // mostly content within those columns.
  const cols: number[] = [];
  for (let x = 0; x < w; x++) {
    let n = 0;
    for (let y = 0; y < h; y++) n += on[y * w + x] ? 1 : 0;
    if (n >= h * 0.25) cols.push(x);
  }
  if (cols.length === 0) return null;
  let x0 = cols[0], x1 = cols[cols.length - 1], y0 = h, y1 = -1;
  for (let y = 0; y < h; y++) {
    let n = 0;
    for (let x = x0; x <= x1; x++) n += on[y * w + x] ? 1 : 0;
    if (n >= (x1 - x0 + 1) * 0.3) {
      y0 = Math.min(y0, y);
      y1 = Math.max(y1, y);
    }
  }
  if (y1 < 0) return null;
  x0 = Math.max(0, x0 - 1); y0 = Math.max(0, y0 - 1);
  x1 = Math.min(w - 1, x1 + 1); y1 = Math.min(h - 1, y1 + 1);
  const box = { x: x0 / w, y: y0 / h, w: (x1 - x0 + 1) / w, h: (y1 - y0 + 1) / h };
  return box.w * box.h > 0.8 || box.w * box.h < 0.03 ? null : box;
}

function px(rgba: ArrayLike<number>, w: number, x: number, y: number): number[] {
  const i = (y * w + x) * 4;
  return [rgba[i], rgba[i + 1], rgba[i + 2]];
}

function median(v: number[]): number {
  const s = [...v].sort((a, b) => a - b);
  return s[s.length >> 1];
}

/** Standard deviation of the grayscale thumbnail; near-zero means a blank / loading frame. */
export function contrast(gray: ArrayLike<number>): number {
  let sum = 0;
  let sq = 0;
  for (let i = 0; i < gray.length; i++) {
    sum += gray[i];
    sq += gray[i] * gray[i];
  }
  const mean = sum / gray.length;
  return Math.sqrt(Math.max(0, sq / gray.length - mean * mean));
}

export type Motion = "still" | "scroll" | "change";

/**
 * Classifies the motion between two consecutive thumbnails by testing vertical shifts:
 * - "still": nearly identical frames
 * - "scroll": content moved up/down (best match at a non-zero row shift) -> the user is scrolling
 * - "change": content changed in place (a reel playing, an animation) -> same item
 */
export function classifyMotion(
  prev: ArrayLike<number>,
  cur: ArrayLike<number>,
  opts: { stillMad: number; maxShift: number } = { stillMad: 1.0, maxShift: 20 },
  w = HASH_W,
  h = HASH_H,
): Motion {
  const cost = (s: number) => {
    let d = 0;
    let n = 0;
    for (let y = Math.max(0, -s); y < Math.min(h, h - s); y++) {
      for (let x = 0; x < w; x++) d += Math.abs(prev[y * w + x] - cur[(y + s) * w + x]);
      n += w;
    }
    return n ? d / n : 255;
  };
  const c0 = cost(0);
  if (c0 <= opts.stillMad) return "still";
  let best = Infinity;
  for (let s = 1; s <= opts.maxShift; s++) best = Math.min(best, cost(s), cost(-s));
  return best <= Math.max(opts.stillMad * 2, c0 * 0.5) ? "scroll" : "change";
}

export interface DetectorOptions {
  /** In-place change (no scroll) larger than this hash distance still ends the item. */
  bigChangeFrac: number;
  /** Mean pixel difference below which consecutive frames count as identical. */
  stillMad: number;
  /** Largest vertical shift, in thumbnail rows, tested when looking for scroll motion. */
  maxShift: number;
  /** How long the screen must stop scrolling before we call it a new item. */
  stableMs: number;
  /**
   * A settled screen is the same item as one seen before only if BOTH its hash distance and its
   * mean pixel difference are this small. Feed posts share a lot of layout, so either signal
   * alone confuses different posts; together they separate them (see sceneChange.test.ts).
   */
  dedupFrac: number;
  dedupMad: number;
  /**
   * A static post that changes in place and settles into a frame at least this different
   * (hash distance AND mean pixel difference) is a new item. This catches scrolls that happen
   * between two samples. Items that were already moving (reels) are exempt.
   */
  switchFrac: number;
  switchMad: number;
  /** Distance from the item's first frame that indicates motion (a playing reel). */
  motionFrac: number;
  /** Ms after entering an item at which to request extra frames, if it is moving. */
  midFrameAtMs: number[];
  /** Frames with contrast below this are ignored (blank, loading). */
  minContrast: number;
  newId: () => string;
}

export const DEFAULT_DETECTOR: Omit<DetectorOptions, "newId"> = {
  bigChangeFrac: 0.25,
  stillMad: 1.0,
  maxShift: 20,
  stableMs: 400,
  dedupFrac: 0.03,
  dedupMad: 2.0,
  switchFrac: 0.04,
  switchMad: 4.0,
  motionFrac: 0.03,
  midFrameAtMs: [2500, 6000],
  minContrast: 4,
};

export type DetectorEvent =
  | { kind: "enter"; itemId: string; hash: string; isNew: boolean; t: number }
  | { kind: "leave"; itemId: string; t: number }
  | { kind: "midframe"; itemId: string; t: number };

interface Current {
  itemId: string;
  hash: string;
  gray: Uint8ClampedArray;
  enteredAt: number;
  moving: boolean;
  midIdx: number;
}

/**
 * Turns a stream of frame thumbnails into item enter/leave events.
 * Scrolling (or a very large in-place change) ends the current item; a new item starts once
 * scrolling has stopped for `stableMs`. In-place changes such as a playing reel keep the item.
 * Items seen before keep their id, so scrolling back to a post resumes its dwell instead of
 * creating a duplicate.
 */
export class SceneDetector {
  private opts: DetectorOptions;
  private current: Current | null = null;
  private prev: Uint8ClampedArray | null = null;
  private settledSince: number | null = null;
  private settleMoved = false;
  private seen: { itemId: string; hash: string; sig: Uint8ClampedArray }[] = [];
  /** Motion class of the last frame (for debugging and the UI). */
  lastMotion: Motion | "blank" = "still";

  constructor(opts: Partial<DetectorOptions> & { newId: () => string }) {
    this.opts = { ...DEFAULT_DETECTOR, ...opts };
  }

  get currentItemId(): string | null {
    return this.current?.itemId ?? null;
  }

  /**
   * Feed one sampled grayscale thumbnail (HASH_W x HASH_H). `t` is a monotonic time in ms.
   * `rgba` (same size) is optional; when given, dedup compares color too, because different
   * posts can have near-identical luma.
   */
  feed(grayIn: ArrayLike<number>, t: number, rgba?: ArrayLike<number>): DetectorEvent[] {
    const o = this.opts;
    const events: DetectorEvent[] = [];
    const gray = Uint8ClampedArray.from(grayIn);
    if (contrast(gray) < o.minContrast) {
      this.lastMotion = "blank";
      this.prev = null;
      this.settledSince = null;
      return events;
    }
    const motion: Motion = this.prev
      ? classifyMotion(this.prev, gray, { stillMad: o.stillMad, maxShift: o.maxShift })
      : "still";
    this.prev = gray;
    this.lastMotion = motion;
    const hash = dHash(gray);

    const cur = this.current;
    if (cur) {
      const d = hashDistance(hash, cur.hash);
      const switched =
        !cur.moving &&
        motion === "still" &&
        d > o.switchFrac &&
        meanAbsDiff(gray, cur.gray) > o.switchMad;
      if (motion !== "scroll" && d <= o.bigChangeFrac && !switched) {
        if (d > o.motionFrac) cur.moving = true;
        const due = o.midFrameAtMs[cur.midIdx];
        if (cur.moving && due !== undefined && t - cur.enteredAt >= due) {
          cur.midIdx++;
          events.push({ kind: "midframe", itemId: cur.itemId, t });
        }
        return events;
      }
      events.push({ kind: "leave", itemId: cur.itemId, t });
      this.current = null;
      this.settledSince = null;
      return events;
    }

    if (motion === "scroll") {
      this.settledSince = null;
      return events;
    }
    if (this.settledSince === null) {
      this.settledSince = t;
      this.settleMoved = false;
    } else if (motion === "change") {
      this.settleMoved = true;
    }
    if (t - this.settledSince < o.stableMs) return events;

    const sig = rgba ? Uint8ClampedArray.from(rgba) : gray;
    let match: { itemId: string } | null = null;
    let best = Infinity;
    for (const s of this.seen) {
      const d = hashDistance(hash, s.hash);
      if (d <= o.dedupFrac && d < best && meanAbsDiff(sig, s.sig) <= o.dedupMad) {
        best = d;
        match = s;
      }
    }
    const itemId = match ? match.itemId : o.newId();
    if (!match) this.seen.push({ itemId, hash, sig });
    this.current = { itemId, hash, gray, enteredAt: t, moving: this.settleMoved, midIdx: 0 };
    this.settledSince = null;
    events.push({ kind: "enter", itemId, hash, isNew: !match, t });
    return events;
  }

  /** End the current item (e.g. when capture stops). */
  flush(t: number): DetectorEvent[] {
    if (!this.current) return [];
    const ev: DetectorEvent = { kind: "leave", itemId: this.current.itemId, t };
    this.current = null;
    this.prev = null;
    this.settledSince = null;
    return [ev];
  }

  reset(): void {
    this.current = null;
    this.prev = null;
    this.settledSince = null;
    this.seen = [];
  }
}
