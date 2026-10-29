import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/demo-feed-scroll.json";
import { classifyMotion, dHash, HASH_BITS, HASH_H, HASH_W, hashDistance, SceneDetector, type DetectorEvent } from "./sceneChange";
import { DwellTracker } from "./dwell";

const decode = (b64: string) => Uint8ClampedArray.from(atob(b64), (c) => c.charCodeAt(0));

function run(frames: { t: number; gray: string }[]) {
  let n = 0;
  const det = new SceneDetector({ newId: () => `item${n++}` });
  const events: DetectorEvent[] = [];
  for (const f of frames) events.push(...det.feed(decode(f.gray), f.t));
  events.push(...det.flush(frames[frames.length - 1].t + 1));
  return events;
}

describe("dHash", () => {
  it("produces a HASH_BITS-bit hash and distance in [0,1]", () => {
    const a = dHash(Array.from({ length: HASH_W * HASH_H }, (_, i) => i % HASH_W));
    const b = dHash(Array.from({ length: HASH_W * HASH_H }, (_, i) => HASH_W - (i % HASH_W)));
    expect(a.length * 4).toBe(HASH_BITS);
    expect(hashDistance(a, a)).toBe(0);
    expect(hashDistance(a, b)).toBe(1);
  });
});

describe("SceneDetector on recorded Demo Feed scroll", () => {
  it("fixture matches the hash size", () => expect(fixture.size).toEqual([HASH_W, HASH_H]));
  const events = run(fixture.frames);
  const enters = events.filter((e) => e.kind === "enter") as Extract<DetectorEvent, { kind: "enter" }>[];
  const newItems = enters.filter((e) => e.isNew);

  it("detects one new item per post", () => {
    expect(newItems.length).toBe(fixture.posts);
  });

  it("treats revisited posts as the same item (dedup by hash)", () => {
    const revisits = enters.filter((e) => !e.isNew);
    expect(revisits.length).toBeGreaterThanOrEqual(2);
    // The last two visits in the fixture go back to posts 13 and 11.
    const order = newItems.map((e) => e.itemId);
    const last2 = revisits.slice(-2).map((e) => order.indexOf(e.itemId));
    expect(last2).toEqual([fixture.visits.at(-2), fixture.visits.at(-1)]);
  });

  it("emits balanced enter/leave events", () => {
    expect(events.filter((e) => e.kind === "leave").length).toBe(enters.length);
  });

  it("accumulates dwell per item", () => {
    const dwell = new DwellTracker();
    const totals: Record<string, number> = {};
    for (const e of events) {
      if (e.kind === "enter") dwell.enter(e.itemId, e.t);
      if (e.kind === "leave") {
        const d = dwell.leave(e.t)!;
        totals[d.itemId] = d.dwellMs;
      }
    }
    // Post 0 had the long (3.5 s) dwell; post 1 the short one (1.6 s).
    const [p0, p1] = newItems.map((e) => totals[e.itemId]);
    expect(p0).toBeGreaterThan(p1);
    expect(p0).toBeGreaterThan(2000);
  });
});

describe("SceneDetector unit behavior", () => {
  const ramp = (dir: 1 | -1) =>
    Array.from({ length: HASH_W * HASH_H }, (_, i) => 128 + dir * ((i % HASH_W) * 3 - 48));
  const A = ramp(1);
  const B = ramp(-1);
  const blank = new Array(HASH_W * HASH_H).fill(30);
  it("requires stability before declaring an item", () => {
    const det = new SceneDetector({ newId: () => "x" });
    expect(det.feed(A, 0)).toEqual([]);
    expect(det.feed(A, 200)).toEqual([]);
    expect(det.feed(A, 450)).toMatchObject([{ kind: "enter", itemId: "x", isNew: true }]);
  });
  it("ignores blank frames", () => {
    const det = new SceneDetector({ newId: () => "x" });
    for (let t = 0; t < 2000; t += 250) expect(det.feed(blank, t)).toEqual([]);
  });
  it("leaves on a big change and re-enters the same id on return", () => {
    let i = 0;
    const det = new SceneDetector({ newId: () => `id${i++}` });
    det.feed(A, 0);
    det.feed(A, 500);
    expect(det.feed(B, 750)).toMatchObject([{ kind: "leave", itemId: "id0" }]);
    det.feed(B, 1300);
    det.feed(A, 1500);
    expect(det.feed(A, 2000)).toMatchObject([{ kind: "enter", itemId: "id0", isNew: false }]);
  });

  // A textured "page" taller than the viewport, so we can scroll through it.
  const page = Array.from({ length: (HASH_H * 3) * HASH_W }, (_, i) =>
    Math.round(128 + 90 * Math.sin(i * 0.37) * Math.cos(Math.floor(i / HASH_W) * 0.71)),
  );
  const view = (row: number) => page.slice(row * HASH_W, (row + HASH_H) * HASH_W);

  it("classifies vertical shifts as scroll and in-place edits as change", () => {
    expect(classifyMotion(view(0), view(0))).toBe("still");
    expect(classifyMotion(view(0), view(6))).toBe("scroll");
    const edited = view(0).map((v, i) => (i % HASH_W > 10 && i % HASH_W < 22 && i > 300 && i < 700 ? 255 - v : v));
    expect(classifyMotion(view(0), edited)).toBe("change");
  });

  it("keeps a playing reel as one item and asks for mid-dwell frames", () => {
    let i = 0;
    const det = new SceneDetector({ newId: () => `id${i++}` });
    const events: DetectorEvent[] = [];
    let t = 0;
    for (; t <= 500; t += 250) events.push(...det.feed(view(0), t));
    // Text appearing in the middle of the reel, frame after frame.
    for (let k = 0; k < 30; k++, t += 250) {
      const f = view(0).map((v, j) => (j > 400 && j < 400 + k * 12 ? 250 : v));
      events.push(...det.feed(f, t));
    }
    expect(events.filter((e) => e.kind === "enter")).toHaveLength(1);
    expect(events.filter((e) => e.kind === "leave")).toHaveLength(0);
    expect(events.filter((e) => e.kind === "midframe")).toHaveLength(2);
  });

  it("ends the item as soon as the user scrolls", () => {
    const det = new SceneDetector({ newId: () => "a" });
    det.feed(view(0), 0);
    det.feed(view(0), 250);
    det.feed(view(0), 500);
    expect(det.feed(view(8), 750)).toMatchObject([{ kind: "leave", itemId: "a" }]);
  });
});
