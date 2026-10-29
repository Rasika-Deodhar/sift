"""Generate the Demo Feed's short reels with ffmpeg + flite (text-to-speech).

Everything in these clips (text, colors, voice) is synthesized locally, so the project owns it.
Run from the repo root:  python demo_feed/tools/make_reels.py
Requires an ffmpeg build with the `flite` and `drawtext` filters, libx264, libvpx and libopus.
Both MP4 (H.264) and WebM (VP9) are written so every browser can play them.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "media"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

REELS = [
    {
        "id": "reel-bike-chain",
        "bg": "0x1f6f5c",
        "lines": ["Clean your bike chain", "in 3 steps", "1. Degrease  2. Rinse  3. Lube"],
        "voice": "Here is how to clean a bike chain in three steps. First, apply degreaser "
        "and scrub with a brush. Second, rinse and dry it fully. Third, put one drop of lube "
        "on each roller, then wipe off the extra.",
    },
    {
        "id": "reel-knife-skills",
        "bg": "0x8a3b12",
        "lines": ["Dice an onion fast", "without crying", "chill it 10 min first"],
        "voice": "To dice an onion fast, chill it for ten minutes first. Cut it in half "
        "through the root, make horizontal cuts, then vertical cuts, and slice across. "
        "Keep the root on so it holds together.",
    },
    {
        "id": "reel-prank",
        "bg": "0x6b2a8a",
        "lines": ["WAIT FOR IT", "you won't believe", "what happens next!!!"],
        "voice": "Wait for it. Wait for it. Oh my gosh. You will not believe this. "
        "Smash that follow button for part two.",
    },
    {
        "id": "reel-ai-tokens",
        "bg": "0x1d3b8a",
        "lines": ["What is a token?", "LLMs read text", "in small chunks"],
        "voice": "What is a token? Language models do not read whole words. They split "
        "text into small chunks called tokens. A short word is often one token, and a long "
        "word can be several. Context limits are counted in tokens.",
    },
]


def make(reel: dict, tmp: Path) -> None:
    txt = tmp / f"{reel['id']}.txt"
    txt.write_text(reel["voice"])
    draws = []
    for i, line in enumerate(reel["lines"]):
        start = i * 2.5
        y = 300 + i * 120
        size = 52 if i == 0 else 40
        safe = line.replace(":", r"\:").replace("'", "")
        draws.append(
            f"drawtext=fontfile={FONT}:text='{safe}':fontcolor=white:fontsize={size}:"
            f"x=(w-text_w)/2:y={y}:enable='gte(t,{start})'"
        )
    draws.append(
        f"drawtext=fontfile={FONT}:text='@sift_demo':fontcolor=white@0.7:fontsize=28:x=30:y=h-80"
    )
    wav = tmp / f"{reel['id']}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", f"flite=textfile={txt}:voice=slt", str(wav)],
        check=True,
    )
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(wav)],
        check=True, capture_output=True, text=True,
    ).stdout) + 0.8
    out = OUT / f"{reel['id']}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={reel['bg']}:s=540x960:r=24",
            "-i", str(wav),
            "-filter_complex", f"[0:v]{','.join(draws)}[v];[1:a]aresample=44100[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{duration:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart",
            str(out),
        ],
        check=True,
    )
    webm = out.with_suffix(".webm")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(out),
         "-c:v", "libvpx-vp9", "-crf", "42", "-b:v", "0", "-row-mt", "1", "-deadline", "realtime",
         "-c:a", "libopus", "-b:a", "40k", str(webm)],
        check=True,
    )
    for f in (out, webm):
        print("wrote", f, f.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found")
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        for r in REELS:
            make(r, Path(d))
