"use client";

import { useCallback, useEffect, useState } from "react";
import {
  useDataChannel,
  useRoomContext,
  useConnectionState,
} from "@livekit/components-react";
import { ConnectionState } from "livekit-client";
import type { RetrievalPayload } from "@/lib/types";

const REGIONS = ["US", "EU"] as const;
type Region = (typeof REGIONS)[number];

// Shows what Moss retrieved for the latest turn, plus a region picker that
// live-updates the metadata filter the agent applies (no restart needed).
export function RetrievalPanel() {
  const room = useRoomContext();
  const connState = useConnectionState();
  const [data, setData] = useState<RetrievalPayload | null>(null);
  const [region, setRegion] = useState<Region>("US");

  useDataChannel(
    "moss.retrieval",
    useCallback((msg: { payload: Uint8Array }) => {
      try {
        setData(JSON.parse(new TextDecoder().decode(msg.payload)) as RetrievalPayload);
      } catch (err) {
        console.error("failed to parse moss.retrieval payload", err);
      }
    }, []),
  );

  const publishRegion = useCallback(
    (r: Region) => {
      try {
        room.localParticipant?.publishData(
          new TextEncoder().encode(JSON.stringify({ region: r })),
          { reliable: true, topic: "moss.region" },
        );
      } catch (err) {
        console.error("failed to publish region", err);
      }
    },
    [room],
  );

  // Sync the agent to the picker whenever we connect or the region changes.
  useEffect(() => {
    if (connState === ConnectionState.Connected) publishRegion(region);
  }, [connState, region, publishRegion]);

  return (
    <div className="card">
      <div className="retrieval-head" style={{ justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="diamond" />
          Moss · knowledge base
        </span>
        <span style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 999, overflow: "hidden" }}>
          {REGIONS.map((r) => (
            <button
              key={r}
              type="button"
              aria-pressed={region === r}
              onClick={() => setRegion(r)}
              style={{
                padding: "6px 18px",
                border: "none",
                cursor: "pointer",
                fontFamily: "var(--font-mono)",
                fontSize: 14,
                letterSpacing: 1,
                background: region === r ? "var(--mint)" : "transparent",
                color: region === r ? "var(--bg)" : "var(--muted)",
                fontWeight: region === r ? 600 : 400,
              }}
            >
              {r}
            </button>
          ))}
        </span>
      </div>

      <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--sage)", marginTop: 8, letterSpacing: 0.3 }}>
        region: {region} + global
      </div>

      {data ? (
        <>
          <div className="retrieval-query">
            <span className="label">query</span>
            {data.query}
          </div>
          <div className="chunks">
            {data.docs.map((doc, i) => {
              const pct = Math.max(0, Math.min(1, doc.score)) * 100;
              return (
                <div className="chunk" key={doc.id ?? i}>
                  <div className="top">
                    <div className="bar">
                      <span style={{ width: `${pct}%` }} />
                    </div>
                    <span className="score">{doc.score.toFixed(2)}</span>
                  </div>
                  <div className="text">{doc.text}</div>
                </div>
              );
            })}
          </div>
          <div className="retrieval-foot">
            <span className="ms">{data.took_ms.toFixed(1)}ms</span>
            <span>·</span>
            <span>
              {data.docs.length} result{data.docs.length === 1 ? "" : "s"} · on-device
            </span>
          </div>
        </>
      ) : (
        <div className="retrieval-empty">
          Pick a region, then ask the agent a question. The chunks Moss retrieves for that region appear here.
        </div>
      )}
    </div>
  );
}
