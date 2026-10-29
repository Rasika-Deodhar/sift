import { describe, expect, it } from "vitest";
import { encodeWav, resample, rms, wavDataUrl } from "./audioChunks";

describe("audio encoding", () => {
  it("resamples 48 kHz to 16 kHz", () => {
    const x = new Float32Array(48000).map((_, i) => Math.sin((2 * Math.PI * 440 * i) / 48000));
    const y = resample(x, 48000, 16000);
    expect(y.length).toBe(16000);
    expect(rms(y)).toBeGreaterThan(0.6); // a 440 Hz tone survives
  });

  it("writes a valid 16-bit mono WAV header", () => {
    const w = encodeWav(new Float32Array([0, 0.5, -0.5, 1, -1]), 16000);
    const v = new DataView(w.buffer);
    const tag = (o: number) => String.fromCharCode(...w.subarray(o, o + 4));
    expect([tag(0), tag(8), tag(12), tag(36)]).toEqual(["RIFF", "WAVE", "fmt ", "data"]);
    expect(v.getUint16(20, true)).toBe(1);
    expect(v.getUint16(22, true)).toBe(1);
    expect(v.getUint32(24, true)).toBe(16000);
    expect(v.getUint16(34, true)).toBe(16);
    expect(v.getInt16(44 + 3 * 2, true)).toBe(0x7fff);
    expect(v.getInt16(44 + 4 * 2, true)).toBe(-0x8000);
    expect(w.length).toBe(44 + 10);
    expect(wavDataUrl(w)).toMatch(/^data:audio\/wav;base64,UklGR/);
  });
});
