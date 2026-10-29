// The only way Sift sees a feed: the browser's standard screen-share prompt (getDisplayMedia).
// The user picks the tab or window; capture ends when they press Stop or end sharing in the
// browser UI. Sift never reads another site's DOM or network traffic.

export interface ShareOptions {
  audio: boolean;
}

export async function startScreenShare(opts: ShareOptions): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    throw new Error("This browser does not support screen sharing (getDisplayMedia).");
  }
  return navigator.mediaDevices.getDisplayMedia({
    // Enough frames to see scroll motion between samples; frames are only hashed, not stored.
    video: { frameRate: { ideal: 15, max: 30 } },
    // Tab audio is only offered by Chromium browsers when sharing a tab.
    audio: opts.audio
      ? { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
      : false,
  } as DisplayMediaStreamOptions);
}

export function stopStream(stream: MediaStream | null): void {
  stream?.getTracks().forEach((t) => t.stop());
}

/** Calls `cb` once when the user ends sharing from the browser's own UI. */
export function onShareEnded(stream: MediaStream, cb: () => void): void {
  const v = stream.getVideoTracks()[0];
  if (v) v.addEventListener("ended", cb, { once: true });
}
