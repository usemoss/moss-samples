"use client";

import {
  BarVisualizer,
  VoiceAssistantControlBar,
  useVoiceAssistant,
} from "@livekit/components-react";
import { Transcript } from "./Transcript";

const STATE_LABEL: Record<string, string> = {
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
  connecting: "connecting",
  initializing: "warming up",
  "pre-connect-buffering": "buffering",
  idle: "idle",
  disconnected: "disconnected",
  failed: "failed",
};

export function AgentSide() {
  const { state, audioTrack } = useVoiceAssistant();
  const label = STATE_LABEL[state] ?? state;
  const inactive =
    state === "idle" || state === "disconnected" || state === "failed";

  return (
    <div className="card agent">
      <div className="orb">
        <BarVisualizer state={state} barCount={7} track={audioTrack} />
      </div>
      <div
        className={`agent-state ${inactive ? "idle" : ""} ${state === "failed" ? "failed" : ""}`}
        role="status"
        aria-live="polite"
      >
        {label}
      </div>
      <Transcript />
      <VoiceAssistantControlBar />
    </div>
  );
}
