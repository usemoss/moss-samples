import { useEffect, useMemo, useState } from 'react';
import { RoomEvent } from 'livekit-client';
import { useRoomContext } from '@livekit/components-react';

const textDecoder = new TextDecoder();

type MossMatch = {
  text: string;
  score?: number;
  metadata?: unknown;
};

export type MossContextEvent = {
  id: string;
  query: string;
  matches: MossMatch[];
  /** Timestamp in milliseconds since epoch */
  timestamp: number;
  timeTakenMs?: number | null;
};

const MAX_EVENTS_DEFAULT = 10;

function parsePayload(payload: Uint8Array): MossContextEvent | null {
  try {
    const raw = textDecoder.decode(payload);
    const message = JSON.parse(raw);
    if (!message || message.type !== 'moss_context' || typeof message.data !== 'object') {
      return null;
    }

    const data = message.data as Record<string, unknown>;
    const query = typeof data.query === 'string' ? data.query : '';
    if (!query) {
      return null;
    }

    const matchesInput = Array.isArray(data.matches) ? data.matches : [];
    const matches: MossMatch[] = matchesInput
      .filter((item) => item && typeof item === 'object')
      .map((item, index) => {
        const match = item as Record<string, unknown>;
        const text = typeof match.text === 'string' ? match.text : '';
        const score = typeof match.score === 'number' ? match.score : undefined;
        const metadata = match.metadata;
        return {
          text,
          score,
          metadata,
          // provide stable fallback text if missing
          ...(text ? {} : { text: `Match ${index + 1}` }),
        };
      });

    const timestampRaw = typeof data.timestamp === 'number' ? data.timestamp : Date.now() / 1000;
    const timestampMs = timestampRaw * 1000;
    const timeTakenMs = typeof data.time_taken_ms === 'number' ? data.time_taken_ms : null;

    return {
      id: `${timestampMs}-${query}`,
      query,
      matches,
      timestamp: timestampMs,
      timeTakenMs,
    };
  } catch (error) {
    console.warn('Failed to parse moss context payload', error);
    return null;
  }
}

export function useMossContextEvents(maxEvents = MAX_EVENTS_DEFAULT) {
  const room = useRoomContext();
  const [events, setEvents] = useState<MossContextEvent[]>([]);

  useEffect(() => {
    if (!room) return;

    const handleData = (payload: Uint8Array) => {
      const parsed = parsePayload(payload);
      if (!parsed) return;

      setEvents((prev) => {
        const next = [...prev, parsed];
        if (maxEvents > 0 && next.length > maxEvents) {
          return next.slice(-maxEvents);
        }
        return next;
      });
    };

    room.on(RoomEvent.DataReceived, handleData);

    return () => {
      room.off(RoomEvent.DataReceived, handleData);
    };
  }, [room, maxEvents]);

  return useMemo(() => events, [events]);
}
