"use client";

import { useEffect, useRef, useState } from "react";
import { useRoomContext } from "@livekit/components-react";
import { RoomEvent, type TranscriptionSegment, type Participant } from "livekit-client";

type Turn = { id: string; text: string; isUser: boolean };

const NEAR_BOTTOM_PX = 80;

// Renders live STT (user) + TTS (agent) transcriptions. Keyed by segment id so
// interim results update in place; object insertion order preserves turn order.
export function Transcript() {
  const room = useRoomContext();
  const [turns, setTurns] = useState<Record<string, Turn>>({});
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    const onTranscription = (segments: TranscriptionSegment[], participant?: Participant) => {
      setTurns((prev) => {
        const next = { ...prev };
        for (const seg of segments) {
          next[seg.id] = { id: seg.id, text: seg.text, isUser: Boolean(participant?.isLocal) };
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

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el || !stickToBottom.current) return;
    el.scrollTop = el.scrollHeight;
  }, [ordered]);

  return (
    <div
      ref={scrollerRef}
      className={`transcript${ordered.length === 0 ? " transcript-empty" : ""}`}
      role="log"
      aria-live="polite"
      aria-relevant="additions text"
      aria-label="Conversation transcript"
      onScroll={() => {
        const el = scrollerRef.current;
        if (!el) return;
        stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
      }}
    >
      {ordered.length === 0 ? (
        "Say hello to start the conversation."
      ) : (
        ordered.map((turn) => (
          <div className={`turn ${turn.isUser ? "user" : "agent"}`} key={turn.id}>
            <span className="who">{turn.isUser ? "You" : "Agent"}</span>
            <span className="text">{turn.text}</span>
          </div>
        ))
      )}
    </div>
  );
}
