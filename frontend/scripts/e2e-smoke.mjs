// End-to-end smoke test: opens the Demo Feed and Sift in one Chromium window, starts Sift,
// auto-selects the Demo Feed tab in the screen-share picker, scrolls, and checks the stream.
// Needs `make dev` running. Usage: node frontend/scripts/e2e-smoke.mjs [--shots DIR]
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.env.SIFT_URL ?? "http://localhost:5173";
const shots = process.argv.includes("--shots") ? process.argv[process.argv.indexOf("--shots") + 1] : null;
const posts = Number(process.env.POSTS ?? 6);

const browser = await chromium.launch({
  headless: true,
  channel: "chromium", // full Chromium (new headless); the headless shell lacks getDisplayMedia
  args: [
    "--auto-select-tab-capture-source-by-title=Sift Demo Feed",
    "--autoplay-policy=no-user-gesture-required",
  ],
});
const ctx = await browser.newContext({ viewport: { width: 1200, height: 860 } });
const feed = await ctx.newPage();
await feed.goto(`${BASE}/demo/`);
await feed.mouse.click(5, 300); // a user gesture, so reels play with sound
const sift = await ctx.newPage();
const debug = !!process.env.SIFT_DEBUG;
sift.on("console", (m) => (m.type() === "error" || (debug && m.type() === "debug")) && console.log("[sift console]", m.text()));
await sift.goto(BASE);
if (debug) await sift.evaluate(() => { window.__siftDebug = true; });
await sift.getByRole("button", { name: "Start Sift" }).click();
await sift.getByRole("button", { name: /choose what to share/ }).click();
await sift.locator(".sharing-pill").waitFor({ timeout: 10000 });
console.log("sharing started");

for (let i = 1; i <= posts; i++) {
  await feed.waitForTimeout(i % 2 ? 3000 : 1800);
  await feed.evaluate((i) => document.querySelectorAll(".post")[i].scrollIntoView({ behavior: "smooth" }), i);
}
// Scroll back up to an earlier post: it must be recognized as a revisit, not a new item.
await feed.waitForTimeout(2500);
await feed.evaluate((i) => document.querySelectorAll(".post")[i].scrollIntoView({ behavior: "smooth" }), posts - 2);
await feed.waitForTimeout(Number(process.env.SETTLE_MS ?? 6000));
if (debug) console.log("feed position", await feed.evaluate(() => { const f = document.getElementById("feed"); return [f.scrollTop, f.clientHeight, f.scrollHeight]; }));
// Learning loop: Save one item, Hide another; the interest strip must show learned topics.
const saveBtn = sift.getByRole("button", { name: "Save" }).first();
if (await saveBtn.count()) {
  await saveBtn.click();
  await sift.getByRole("button", { name: "Hide" }).last().click();
  await sift.locator(".interest-strip .chip.like").first().waitFor({ timeout: 5000 });
}
if (shots) await sift.screenshot({ path: `${shots}/sift.png`, fullPage: true });
// Categorize: lanes view groups the same items.
let lanes = [];
if (await sift.locator("[data-item-id] .reason").count()) {
  await sift.getByRole("button", { name: "Categorize" }).click();
  await sift.locator(".lane").first().waitFor({ timeout: 3000 });
  lanes = await sift.evaluate(() =>
    [...document.querySelectorAll(".lane")].map((l) => `${l.getAttribute("data-lane")}:${l.querySelector(".lane-count")?.textContent}`),
  );
  if (shots) await sift.screenshot({ path: `${shots}/lanes.png`, fullPage: true });
  await sift.getByRole("button", { name: "Categorize" }).click();
}
const skippedN = Number((await sift.locator(".skipped-toggle").textContent().catch(() => ""))?.match(/Skipped \((\d+)\)/)?.[1] ?? 0);
if (skippedN) await sift.locator(".skipped-toggle").click(); // expand so every item is countable
const summary = await sift.evaluate(() => ({
  detected: document.querySelectorAll("[data-item-id]").length,
  revisited: [...document.querySelectorAll("[data-item-id]")].filter((e) => /[2-9] visits/.test(e.textContent ?? "")).length,
  cards: document.querySelectorAll("[data-item-id] .reason").length,
  likes: [...document.querySelectorAll(".interest-strip .chip.like")].map((e) => e.textContent),
  reranked: document.querySelectorAll(".chip.delta").length,
  transcripts: document.querySelectorAll(".chip.audio").length,
  picks: document.querySelectorAll(".tier-highlight").length,
  failed: document.querySelectorAll(".failed [data-item-id]").length,
  reasons: [...document.querySelectorAll("[data-item-id] .reason")].map((e) => e.textContent).slice(0, 12),
}));
console.log(JSON.stringify(summary, null, 1));
await sift.getByRole("button", { name: "Stop" }).click();
await sift.getByRole("button", { name: "Start Sift" }).waitFor({ timeout: 5000 });
console.log("stopped OK");
await browser.close();
summary.skipped = skippedN;
console.log("lanes", lanes.join(" | "));
const laneTotal = lanes.reduce((n, l) => n + Number(l.split(":").pop()), 0);
if (laneTotal !== summary.cards) {
  console.error(`lanes hold ${laneTotal} items, stream has ${summary.cards}`);
  process.exit(1);
}
const expectCards = process.env.EXPECT_CARDS !== "0";
if (summary.detected !== posts + 1 || summary.revisited < 1 || (expectCards && summary.cards < posts + 1)) {
  console.error(`expected ${posts + 1} items (all analyzed) and a revisit; got ${JSON.stringify(summary)}`);
  process.exit(1);
}
