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
  idle: "idle",
  failed: "failed",
  disconnected: "disconnected",
  "pre-connect-buffering": "connecting",
};

export function AgentSide() {
  const { state, audioTrack } = useVoiceAssistant();
  const label = STATE_LABEL[state] ?? "…";
  const idle = !state || state === "disconnected" || state === "idle";
  const failed = state === "failed";

  return (
    <div className="card agent">
      <div className="orb">
        <BarVisualizer state={state} barCount={7} trackRef={audioTrack} />
      </div>
      <div className={`agent-state ${idle ? "idle" : ""} ${failed ? "failed" : ""}`}>{label}</div>
      <Transcript />
      <VoiceAssistantControlBar />
    </div>
  );
}
