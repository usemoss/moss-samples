import { useEffect, useMemo, useState } from 'react';
import { RoomEvent } from 'livekit-client';
import { useRoomContext } from '@livekit/components-react';

const textDecoder = new TextDecoder();

export type LlmUsageEvent = {
  id: string;
  model?: string | null;
  promptTokens?: number | null;
  completionTokens?: number | null;
  totalTokens?: number | null;
  timestamp: number;
};

const MAX_EVENTS_DEFAULT = 20;

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
}

function parseUsagePayload(payload: Uint8Array): LlmUsageEvent | null {
  try {
    const raw = textDecoder.decode(payload);
    const message = JSON.parse(raw);

    if (!message || message.type !== 'llm_usage' || typeof message.data !== 'object') {
      return null;
    }

    const data = message.data as Record<string, unknown>;
    const rawTimestamp =
      typeof data.timestamp === 'number' && Number.isFinite(data.timestamp)
        ? data.timestamp
        : Date.now();
    const timestampValue = Math.floor(rawTimestamp);
    const tokenKey =
      data.total_tokens ?? data.prompt_tokens ?? data.completion_tokens ?? data.model ?? 'usage';
    const id = `${timestampValue}-${tokenKey}`;

    return {
      id,
      model: typeof data.model === 'string' ? data.model : null,
      promptTokens: toNumber(data.prompt_tokens),
      completionTokens: toNumber(data.completion_tokens),
      totalTokens: toNumber(data.total_tokens),
      timestamp: timestampValue,
    };
  } catch (error) {
    console.warn('Failed to parse llm usage payload', error);
    return null;
  }
}

export function useLlmUsageEvents(maxEvents = MAX_EVENTS_DEFAULT) {
  const room = useRoomContext();
  const [events, setEvents] = useState<LlmUsageEvent[]>([]);

  useEffect(() => {
    if (!room) return;

    const handleData = (payload: Uint8Array) => {
      const parsed = parseUsagePayload(payload);
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
