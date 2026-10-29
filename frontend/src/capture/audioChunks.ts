// Records the shared tab's audio in short chunks tied to the item on screen, and encodes each
// chunk as 16 kHz mono 16-bit WAV (what Muse Voice Transcribe accepts). Chunks are sent once and
// never stored. Silent chunks are dropped before they leave the browser.

export const TARGET_RATE = 16000;

export interface AudioChunkerOptions {
  chunkSeconds: number;
  minSeconds: number;
  maxChunksPerItem: number;
  silenceRms: number;
}

export const DEFAULT_AUDIO: AudioChunkerOptions = {
  chunkSeconds: 8,
  minSeconds: 1.5,
  maxChunksPerItem: 3,
  silenceRms: 0.004,
};

export class AudioChunker {
  private ctx: AudioContext;
  private node: ScriptProcessorNode;
  private source: MediaStreamAudioSourceNode;
  private mute: GainNode;
  private buf: Float32Array[] = [];
  private samples = 0;
  private itemId: string | null = null;
  private sent = new Map<string, number>();
  private opts: AudioChunkerOptions;

  constructor(
    stream: MediaStream,
    private onChunk: (itemId: string, wavDataUrl: string) => void,
    opts: Partial<AudioChunkerOptions> = {},
  ) {
    this.opts = { ...DEFAULT_AUDIO, ...opts };
    this.ctx = new AudioContext();
    this.source = this.ctx.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
    // ScriptProcessorNode is deprecated but universally available and plenty for 8 s chunks.
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.mute = this.ctx.createGain();
    this.mute.gain.value = 0; // the user already hears the tab; don't play it twice
    this.node.onaudioprocess = (e) => this.push(e.inputBuffer.getChannelData(0));
    this.source.connect(this.node);
    this.node.connect(this.mute);
    this.mute.connect(this.ctx.destination);
  }

  /** Call when the on-screen item changes (null while scrolling). Flushes the previous item. */
  setItem(itemId: string | null): void {
    if (itemId === this.itemId) return;
    this.flush();
    this.itemId = itemId;
  }

  stop(): void {
    this.flush();
    this.node.disconnect();
    this.source.disconnect();
    this.mute.disconnect();
    this.ctx.close().catch(() => {});
  }

  private push(data: Float32Array): void {
    if (!this.itemId) return;
    this.buf.push(new Float32Array(data));
    this.samples += data.length;
    if (this.samples >= this.opts.chunkSeconds * this.ctx.sampleRate) this.flush();
  }

  private flush(): void {
    const id = this.itemId;
    const pcm = concat(this.buf, this.samples);
    this.buf = [];
    this.samples = 0;
    if (import.meta.env.DEV && (window as { __siftDebug?: boolean }).__siftDebug && id) {
      console.debug("[sift audio]", id.slice(0, 6), (pcm.length / this.ctx.sampleRate).toFixed(1) + "s", "rms", rms(pcm).toFixed(4));
    }
    if (!id || pcm.length < this.opts.minSeconds * this.ctx.sampleRate) return;
    if ((this.sent.get(id) ?? 0) >= this.opts.maxChunksPerItem) return;
    if (rms(pcm) < this.opts.silenceRms) return;
    this.sent.set(id, (this.sent.get(id) ?? 0) + 1);
    this.onChunk(id, wavDataUrl(encodeWav(resample(pcm, this.ctx.sampleRate, TARGET_RATE), TARGET_RATE)));
  }
}

export function concat(parts: Float32Array[], total: number): Float32Array {
  const out = new Float32Array(total);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

export function rms(x: Float32Array): number {
  let s = 0;
  for (let i = 0; i < x.length; i++) s += x[i] * x[i];
  return Math.sqrt(s / Math.max(1, x.length));
}

/** Linear-interpolation resampler with a simple box pre-filter when downsampling. */
export function resample(x: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return x;
  const ratio = from / to;
  const out = new Float32Array(Math.floor(x.length / ratio));
  const half = Math.max(0, Math.floor(ratio / 2));
  for (let i = 0; i < out.length; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    let acc = 0;
    let n = 0;
    for (let k = i0 - half; k <= i0 + half; k++) {
      if (k >= 0 && k < x.length) {
        acc += x[k];
        n++;
      }
    }
    out[i] = n ? acc / n : 0;
  }
  return out;
}

/** 16-bit PCM mono WAV. */
export function encodeWav(pcm: Float32Array, rate: number): Uint8Array {
  const buf = new ArrayBuffer(44 + pcm.length * 2);
  const v = new DataView(buf);
  const str = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF");
  v.setUint32(4, 36 + pcm.length * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  str(36, "data");
  v.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) {
    const s = Math.max(-1, Math.min(1, pcm[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buf);
}

export function wavDataUrl(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return `data:audio/wav;base64,${btoa(bin)}`;
}
