// Records scene-change fixtures by scrolling the Demo Feed in headless Chromium and sampling
// the viewport like Sift's frame sampler does (small grayscale thumbnail, ~4 fps, stored base64).
// Output: src/capture/__fixtures__/demo-feed-scroll.json
// Usage: node frontend/scripts/record-fixtures.mjs   (Playwright must be installed)

import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { extname, join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const here = dirname(fileURLToPath(import.meta.url));
const FEED_DIR = resolve(here, "../../demo_feed");
const OUT = resolve(here, "../src/capture/__fixtures__/demo-feed-scroll.json");
// Must match HASH_W / HASH_H in src/capture/sceneChange.ts.
const HASH_W = Number(process.env.HASH_W ?? 33);
const HASH_H = Number(process.env.HASH_H ?? 32);
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".mp4": "video/mp4", ".webm": "video/webm" };

const server = createServer(async (req, res) => {
  try {
    const p = join(FEED_DIR, decodeURIComponent(new URL(req.url, "http://x").pathname).replace(/\/$/, "/index.html"));
    const body = await readFile(p);
    res.writeHead(200, { "content-type": TYPES[extname(p)] ?? "application/octet-stream" }).end(body);
  } catch {
    res.writeHead(404).end();
  }
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 480, height: 820 } });
const hasher = await browser.newPage();
await page.goto(`http://localhost:${port}/`);
await page.waitForTimeout(800);

const frames = [];
const t0 = Date.now();
let sampling = true;
const sampler = (async () => {
  while (sampling) {
    const t = Date.now() - t0;
    const png = (await page.screenshot()).toString("base64");
    const gray = await hasher.evaluate(async ([b64, W, H]) => {
      const img = new Image();
      img.src = `data:image/png;base64,${b64}`;
      await img.decode();
      const c = document.createElement("canvas");
      c.width = W; c.height = H;
      const ctx = c.getContext("2d");
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(img, 0, 0, W, H);
      const d = ctx.getImageData(0, 0, W, H).data;
      let bin = "";
      for (let i = 0; i < d.length; i += 4) bin += String.fromCharCode(Math.round(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]));
      return btoa(bin);
    }, [png, HASH_W, HASH_H]);
    frames.push({ t, gray });
    await new Promise((r) => setTimeout(r, Math.max(0, 250 - (Date.now() - t0 - t))));
  }
})();

const n = await page.evaluate(() => window.SIFT_DEMO_POSTS.length);
const visits = [];
const scrollTo = async (i) => {
  await page.evaluate((i) => document.querySelectorAll(".post")[i].scrollIntoView({ behavior: "smooth" }), i);
};
// Scroll down through every post with varied dwell, then jump back up to revisit two posts.
for (let i = 0; i < n; i++) {
  visits.push(i);
  await page.waitForTimeout(i % 3 === 0 ? 3500 : 1600);
  if (i < n - 1) await scrollTo(i + 1);
}
for (const i of [n - 3, n - 5]) {
  await scrollTo(i);
  visits.push(i);
  await page.waitForTimeout(2000);
}
sampling = false;
await sampler;
await browser.close();
server.close();

const ids = await Promise.resolve(visits);
await writeFile(
  OUT,
  JSON.stringify({ viewport: [480, 820], size: [HASH_W, HASH_H], posts: n, visits: ids, intervalMs: 250, frames }),
);
console.log(`wrote ${frames.length} frames, ${n} posts, visits ${ids.join(",")} -> ${OUT}`);
