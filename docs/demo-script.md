# 3-minute demo script

**Setup (before recording).** `make dev`. Two browser windows side by side: left, the Demo Feed
at `http://localhost:5173/demo/` (or a real feed you scroll); right, Sift at
`http://localhost:5173`. Click once in the Demo Feed so reels play with sound. Press "Clear
session" in Sift. Zoom the Sift window so cards are readable on video.

| Time | Do | Say |
|---|---|---|
| 0:00 | Show both windows. | "Your feed is optimized for the platform. Sift is optimized for you. Sift watches the feed I share with it, understands every post with Meta's Muse Spark, and builds a curated stream that learns what I value, with no setup." |
| 0:20 | Click **Start Sift**, show the consent note, tick tab audio, pick the Demo Feed tab. Point at the red "Sharing" indicator. | "It only sees the tab I pick, only while I share. Frames are analyzed in memory and never saved." |
| 0:30 | Scroll the feed slowly: bike sealant post, the "90% OFF" promo, pasta water, the bike-chain reel. | "Each post appears in seconds with a category, a value score, a one-line reason, and a quote from the post as evidence." |
| 1:00 | Point at the promo landing in **Skipped (N)**. Expand it. Hover a score. | "Low-value items aren't hidden, they're collapsed, and every decision is explainable: here it flagged engagement bait and a hard sell. Hover the score for the breakdown." |
| 1:15 | On the bike-chain reel, point at the 🔊 transcript chip. | "For reels, Muse Voice Transcribe turns the audio into text and Muse Spark updates the card from what was said." |
| 1:30 | Keep scrolling. Dwell on the AI post and the tokens reel. Click **Save** on two AI items, **Hide** on the meme. | "Now I just behave normally. Long dwell, saves and hides update what Sift thinks I like." |
| 1:50 | Point at the interest strip flashing ▲ ai, ▼ memes, and at cards showing ▲ 6.2 → 7.4 as they move into Sift picks. Click **Before / after**. | "The interest strip shows what changed and why, and the stream re-ranks live. Every version is kept, so here's before and after." |
| 2:10 | Flip **Categorize**. Collapse a lane. Scroll two more posts; watch counts tick. | "Categorize groups everything into live lanes. Counts update as I scroll." |
| 2:40 | Press **Stop**. The session digest opens. | "When I stop, Sift gives me a digest written by Muse Spark: what was worth my time, and what it filtered out." |
| 2:50 | Show the README model table and the repo URL. | "Muse Spark vision and text, Muse Voice Transcribe, all through one Meta client. Open source, built during the hackathon. Your feed is optimized for the platform. Sift is optimized for you." |

**Fallbacks.** If the network is slow, the queue keeps the newest items and the stats panel
shows "skipped while scrolling fast". If audio sharing is not offered (non-Chromium browsers
or window share), skip the 1:15 beat. Run `make e2e` before recording to confirm the loop.
