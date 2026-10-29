// Samples frames from the shared stream. Tiny thumbnails are hashed every tick for
// scene detection; full frames are only encoded when an item needs to be understood.
// Frames live in memory only and are never stored.

import { HASH_H, HASH_W } from "./sceneChange";

const TICK_WORKER = `let id=null;onmessage=(e)=>{clearInterval(id);if(e.data>0)id=setInterval(()=>postMessage(0),e.data)}`;

export interface FrameSamplerOptions {
  intervalMs: number;
  maxEdge: number;
  jpegQuality: number;
  thumbEdge: number;
}

export const DEFAULT_SAMPLER: FrameSamplerOptions = {
  intervalMs: 150,
  maxEdge: 768,
  jpegQuality: 0.7,
  thumbEdge: 160,
};

export class FrameSampler {
  readonly video: HTMLVideoElement;
  private hashCanvas = document.createElement("canvas");
  private frameCanvas = document.createElement("canvas");
  private worker: Worker | null = null;
  private opts: FrameSamplerOptions;

  constructor(stream: MediaStream, opts: Partial<FrameSamplerOptions> = {}) {
    this.opts = { ...DEFAULT_SAMPLER, ...opts };
    this.video = document.createElement("video");
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.srcObject = stream;
    this.hashCanvas.width = HASH_W;
    this.hashCanvas.height = HASH_H;
  }

  async start(
    onTick: (gray: Uint8ClampedArray, t: number, rgba: Uint8ClampedArray) => void,
  ): Promise<void> {
    await this.video.play();
    // A worker-driven timer keeps ticking when the Sift tab is in the background, where
    // main-thread timers are throttled.
    this.worker = new Worker(URL.createObjectURL(new Blob([TICK_WORKER])));
    this.worker.onmessage = () => {
      const rgba = this.rgbaThumb();
      if (rgba) onTick(toGray(rgba), performance.now(), rgba);
    };
    this.worker.postMessage(this.opts.intervalMs);
  }

  stop(): void {
    this.worker?.postMessage(0);
    this.worker?.terminate();
    this.worker = null;
    this.video.pause();
    this.video.srcObject = null;
  }

  private ready(): boolean {
    return this.video.readyState >= 2 && this.video.videoWidth > 0;
  }

  rgbaThumb(): Uint8ClampedArray | null {
    if (!this.ready()) return null;
    const ctx = this.hashCanvas.getContext("2d", { willReadFrequently: true })!;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(this.video, 0, 0, HASH_W, HASH_H);
    return ctx.getImageData(0, 0, HASH_W, HASH_H).data;
  }

  /** JPEG data URL of the current frame, scaled so the long edge is at most `edge`. */
  grabFrame(edge = this.opts.maxEdge, quality = this.opts.jpegQuality): string | null {
    if (!this.ready()) return null;
    const { videoWidth: w, videoHeight: h } = this.video;
    const scale = Math.min(1, edge / Math.max(w, h));
    this.frameCanvas.width = Math.round(w * scale);
    this.frameCanvas.height = Math.round(h * scale);
    const ctx = this.frameCanvas.getContext("2d")!;
    ctx.drawImage(this.video, 0, 0, this.frameCanvas.width, this.frameCanvas.height);
    return this.frameCanvas.toDataURL("image/jpeg", quality);
  }

  grabThumb(): string | null {
    return this.grabFrame(this.opts.thumbEdge, 0.6);
  }
}

/** RGBA -> luma (Rec. 601). */
export function toGray(rgba: Uint8ClampedArray): Uint8ClampedArray {
  const out = new Uint8ClampedArray(rgba.length / 4);
  for (let i = 0, j = 0; i < rgba.length; i += 4, j++) {
    out[j] = 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2];
  }
  return out;
}
