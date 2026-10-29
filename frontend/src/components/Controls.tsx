import { useState } from "react";

interface Props {
  sharing: boolean;
  hasAudio: boolean;
  onStart(opts: { audio: boolean; focusHint: string }): void;
  onStop(): void;
  onClear(): void;
  busy?: boolean;
}

export default function Controls({ sharing, hasAudio, onStart, onStop, onClear, busy }: Props) {
  const [consentOpen, setConsentOpen] = useState(false);
  const [audio, setAudio] = useState(true);
  const [focusHint, setFocusHint] = useState("");

  return (
    <div className="controls">
      {sharing ? (
        <>
          <span className="sharing-pill" role="status">
            <span className="dot" /> Sharing{hasAudio ? " + audio" : ""}
          </span>
          <button className="btn danger" onClick={onStop}>
            Stop
          </button>
        </>
      ) : (
        <button className="btn primary" disabled={busy} onClick={() => setConsentOpen(true)}>
          Start Sift
        </button>
      )}
      <input
        className="focus-hint"
        placeholder="Focus hint (optional): AI, cycling, cooking"
        value={focusHint}
        disabled={sharing}
        onChange={(e) => setFocusHint(e.target.value)}
      />
      <button className="btn ghost" onClick={onClear} title="Delete everything from this session">
        Clear session
      </button>

      {consentOpen && (
        <div className="modal-backdrop" onClick={() => setConsentOpen(false)}>
          <div className="modal" role="dialog" aria-labelledby="consent-title" onClick={(e) => e.stopPropagation()}>
            <h2 id="consent-title">Before you share</h2>
            <ul>
              <li>Your browser will ask which tab or window to share. Sift sees only that, and only until you press Stop.</li>
              <li>Frames are analyzed in memory by Meta's Muse Spark model. Raw frames and audio are never saved.</li>
              <li>Sift keeps short text cards and small thumbnails for this session only. "Clear session" deletes them.</li>
              <li>Sift learns topics and formats you like, never personal attributes.</li>
            </ul>
            <label className="check">
              <input type="checkbox" checked={audio} onChange={(e) => setAudio(e.target.checked)} />
              Also share tab audio (for reels with speech)
            </label>
            <div className="modal-actions">
              <button className="btn ghost" onClick={() => setConsentOpen(false)}>
                Cancel
              </button>
              <button
                className="btn primary"
                onClick={() => {
                  setConsentOpen(false);
                  onStart({ audio, focusHint });
                }}
              >
                I understand, choose what to share
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
