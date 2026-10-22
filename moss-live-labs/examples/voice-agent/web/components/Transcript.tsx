"use client";

import { useEffect, useRef, useState } from "react";
import { useRoomContext } from "@livekit/components-react";
import { RoomEvent, type TranscriptionSegment, type Participant } from "livekit-client";

type Turn = { id: string; text: string; isUser: boolean };

const MAX_TURNS = 100;

// Renders live STT (user) + TTS (agent) transcriptions. Keyed by segment id so
// interim results update in place; object insertion order preserves turn order.
export function Transcript() {
  const room = useRoomContext();
  const [turns, setTurns] = useState<Record<string, Turn>>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    const onTranscription = (segments: TranscriptionSegment[], participant?: Participant) => {
      setTurns((prev) => {
        const next = { ...prev };
        for (const seg of segments) {
          const text = seg.text;
          if (!text.trim()) {
            // Drop blank interim artifacts so they never consume the history cap.
            delete next[seg.id];
            continue;
          }
          next[seg.id] = { id: seg.id, text, isUser: Boolean(participant?.isLocal) };
        }
        const ids = Object.keys(next);
        if (ids.length > MAX_TURNS) {
          for (const id of ids.slice(0, ids.length - MAX_TURNS)) delete next[id];
        }
        return next;
      });
    };
    room.on(RoomEvent.TranscriptionReceived, onTranscription);
    return () => {
      room.off(RoomEvent.TranscriptionReceived, onTranscription);
    };
  }, [room]);

  const ordered = Object.values(turns);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      stickToBottomRef.current = distanceFromBottom < 80;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [turns]);

  return (
    <div
      className={`transcript${ordered.length === 0 ? " transcript-empty" : ""}`}
      ref={containerRef}
      role="log"
      aria-live="polite"
      aria-relevant="additions text"
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
