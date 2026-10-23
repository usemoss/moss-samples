"use client";

import { useEffect, useState } from "react";
import { useRoomContext } from "@livekit/components-react";
import { RoomEvent, type TranscriptionSegment, type Participant } from "livekit-client";

type Turn = { id: string; text: string; isUser: boolean };

// Renders live STT (user) + TTS (agent) transcriptions. Keyed by segment id so
// interim results update in place; object insertion order preserves turn order.
export function Transcript() {
  const room = useRoomContext();
  const [turns, setTurns] = useState<Record<string, Turn>>({});

  useEffect(() => {
    const onTranscription = (segments: TranscriptionSegment[], participant?: Participant) => {
      setTurns((prev) => {
        const next = { ...prev };
        for (const seg of segments) {
          next[seg.id] = { id: seg.id, text: seg.text, isUser: Boolean(participant?.isLocal) };
        }
        // cap history so a long call doesn't grow memory without bound
        const ids = Object.keys(next);
        const MAX = 100;
        if (ids.length > MAX) {
          for (const id of ids.slice(0, ids.length - MAX)) delete next[id];
        }
        return next;
      });
    };
    room.on(RoomEvent.TranscriptionReceived, onTranscription);
    return () => {
      room.off(RoomEvent.TranscriptionReceived, onTranscription);
    };
  }, [room]);

  const ordered = Object.values(turns).filter((t) => t.text.trim().length > 0);

  if (ordered.length === 0) {
    return <div className="transcript transcript-empty">Say hello to start the conversation.</div>;
  }

  return (
    <div className="transcript">
      {ordered.map((turn) => (
        <div className={`turn ${turn.isUser ? "user" : "agent"}`} key={turn.id}>
          <span className="who">{turn.isUser ? "You" : "Agent"}</span>
          <span className="text">{turn.text}</span>
        </div>
      ))}
    </div>
  );
}
