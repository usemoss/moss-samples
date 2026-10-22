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
};

export function AgentSide() {
  const { state, audioTrack } = useVoiceAssistant();
  const label = STATE_LABEL[state] ?? "idle";
  const idle = !state || state === "disconnected" || state === "idle";

  return (
    <div className="card agent">
      <div className="orb">
        <BarVisualizer state={state} barCount={7} trackRef={audioTrack} />
      </div>
      <div className={`agent-state ${idle ? "idle" : ""}`}>{label}</div>
      <Transcript />
      <VoiceAssistantControlBar />
    </div>
  );
}
