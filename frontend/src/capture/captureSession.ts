// Wires screen share -> frame sampler -> scene detector -> dwell tracker, and reports item
// events to the app. Everything here runs in the user's browser.

import { AudioChunker } from "./audioChunks";
import { DwellTracker } from "./dwell";
import { FrameSampler } from "./frameSampler";
import { colorSignature, SceneDetector } from "./sceneChange";
import { onShareEnded, startScreenShare, stopStream } from "./screenShare";

export interface ItemEnter {
  itemId: string;
  isNew: boolean;
  phash: string;
  sig: string;
  frame: string | null;
  thumb: string | null;
  at: number; // wall-clock ms
}

export interface CaptureCallbacks {
  onItemEnter(e: ItemEnter): void;
  onItemLeave(e: { itemId: string; dwellMs: number }): void;
  onMidFrame(e: { itemId: string; frame: string }): void;
  onAudioChunk(e: { itemId: string; wav: string }): void;
  onEnded(): void;
}

export class CaptureSession {
  readonly stream: MediaStream;
  readonly sampler: FrameSampler;
  readonly dwell = new DwellTracker();
  private detector = new SceneDetector({ newId: () => crypto.randomUUID() });
  private stopped = false;
  private audio: AudioChunker | null = null;

  private constructor(stream: MediaStream, private cb: CaptureCallbacks) {
    this.stream = stream;
    this.sampler = new FrameSampler(stream);
  }

  /**
   * Opens the browser's share picker (must run inside the click handler's user activation),
   * then runs `beforeSampling` (e.g. starting the backend session) before any frame is read.
   */
  static async start(
    opts: { audio: boolean },
    cb: CaptureCallbacks,
    beforeSampling?: (s: CaptureSession) => Promise<void>,
  ): Promise<CaptureSession> {
    const stream = await startScreenShare(opts);
    const s = new CaptureSession(stream, cb);
    try {
      await beforeSampling?.(s);
    } catch (e) {
      stopStream(stream);
      throw e;
    }
    onShareEnded(stream, () => s.stop());
    if (s.hasAudio) {
      s.audio = new AudioChunker(stream, (itemId, wav) => cb.onAudioChunk({ itemId, wav }));
    }
    await s.sampler.start((gray, t, rgba) => s.tick(gray, t, rgba));
    return s;
  }

  get hasAudio(): boolean {
    return this.stream.getAudioTracks().length > 0;
  }

  get currentItemId(): string | null {
    return this.detector.currentItemId;
  }

  private tick(gray: Uint8ClampedArray, t: number, rgba: Uint8ClampedArray): void {
    if (this.stopped) return;
    const events = this.detector.feed(gray, t, rgba);
    if (import.meta.env.DEV && (window as { __siftDebug?: boolean }).__siftDebug) {
      console.debug("[sift]", Math.round(t), this.detector.lastMotion, JSON.stringify(events));
    }
    for (const ev of events) {
      if (ev.kind === "enter") {
        this.dwell.enter(ev.itemId, t);
        this.audio?.setItem(ev.itemId);
        this.cb.onItemEnter({
          itemId: ev.itemId,
          isNew: ev.isNew,
          phash: ev.hash,
          sig: colorSignature(rgba),
          frame: ev.isNew ? this.sampler.grabFrame() : null,
          thumb: ev.isNew ? this.sampler.grabThumb(rgba) : null,
          at: Date.now(),
        });
      } else if (ev.kind === "leave") {
        this.audio?.setItem(null);
        const d = this.dwell.leave(t);
        if (d) this.cb.onItemLeave(d);
      } else {
        const frame = this.sampler.grabFrame();
        if (frame) this.cb.onMidFrame({ itemId: ev.itemId, frame });
      }
    }
  }

  liveDwell(itemId: string): number {
    return this.dwell.current(itemId, performance.now());
  }

  /** Stops all capture immediately: tracks, timers, detector. */
  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    const t = performance.now();
    for (const ev of this.detector.flush(t)) {
      if (ev.kind === "leave") {
        const d = this.dwell.leave(t);
        if (d) this.cb.onItemLeave(d);
      }
    }
    this.audio?.stop();
    this.audio = null;
    this.sampler.stop();
    stopStream(this.stream);
    this.cb.onEnded();
  }
}
