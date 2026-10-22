"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  useDataChannel,
  useRoomContext,
  useConnectionState,
} from "@livekit/components-react";
import { ConnectionState, RoomEvent } from "livekit-client";
import type { RetrievalDoc, RetrievalPayload } from "@/lib/types";

const REGIONS = ["US", "EU"] as const;
type Region = (typeof REGIONS)[number];

function isRetrievalDoc(value: unknown): value is RetrievalDoc {
  if (!value || typeof value !== "object") return false;
  const doc = value as Record<string, unknown>;
  const idOk =
    doc.id === undefined || doc.id === null || typeof doc.id === "string";
  return idOk && typeof doc.text === "string" && typeof doc.score === "number";
}

function parseRetrievalPayload(value: unknown): RetrievalPayload | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.query !== "string") return null;
  if (!Array.isArray(raw.docs) || !raw.docs.every(isRetrievalDoc)) return null;
  if (typeof raw.took_ms !== "number" || Number.isNaN(raw.took_ms)) return null;
  if (typeof raw.region !== "string" || !raw.region) return null;
  return {
    query: raw.query,
    docs: raw.docs,
    took_ms: raw.took_ms,
    region: raw.region,
  };
}

// Shows what Moss retrieved for the latest turn, plus a region picker that
// live-updates the metadata filter the agent applies (no restart needed).
export function RetrievalPanel() {
  const room = useRoomContext();
  const connState = useConnectionState();
  const [data, setData] = useState<RetrievalPayload | null>(null);
  const [region, setRegion] = useState<Region>("US");
  const [regionError, setRegionError] = useState<string | null>(null);
  // Filter/display region — updated immediately on click so stale chunks never
  // appear under the wrong label while publish is in flight.
  const filterRegionRef = useRef<Region>("US");
  const committedRegionRef = useRef<Region>("US");
  // Monotonic id so only the latest select/sync callback may mutate UI state.
  const opIdRef = useRef(0);
  const publishChainRef = useRef(Promise.resolve());

  useDataChannel(
    "moss.retrieval",
    useCallback((msg: { payload: Uint8Array }) => {
      try {
        const parsed = parseRetrievalPayload(
          JSON.parse(new TextDecoder().decode(msg.payload)),
        );
        if (!parsed) {
          console.error("invalid moss.retrieval payload shape");
          return;
        }
        // region is mandatory — drop mismatches (and never accept untagged payloads).
        if (parsed.region !== filterRegionRef.current) return;
        setData(parsed);
      } catch (err) {
        console.error("failed to parse moss.retrieval payload", err);
      }
    }, []),
  );

  const publishRegion = useCallback(
    async (r: Region): Promise<boolean> => {
      try {
        await room.localParticipant?.publishData(
          new TextEncoder().encode(JSON.stringify({ region: r })),
          { reliable: true, topic: "moss.region" },
        );
        return true;
      } catch (err) {
        console.error("failed to publish region", err);
        return false;
      }
    },
    [room],
  );

  const runRegionOp = useCallback(
    (r: Region, opts: { clearResults: boolean; failMessage: string }) => {
      const opId = ++opIdRef.current;
      filterRegionRef.current = r;
      setRegion(r);
      setRegionError(null);
      if (opts.clearResults) setData(null);

      publishChainRef.current = publishChainRef.current
        .catch(() => undefined)
        .then(async () => {
          // Always run the publish (chain serializes). Record successful agent
          // sync even if a newer op has superseded this one for UI updates.
          const ok = await publishRegion(r);
          if (ok) {
            committedRegionRef.current = r;
          }

          if (opId !== opIdRef.current) return;

          if (!ok) {
            // Roll back to whatever the agent last successfully accepted.
            const rollback = committedRegionRef.current;
            filterRegionRef.current = rollback;
            setRegion(rollback);
            setRegionError(opts.failMessage);
            return;
          }

          filterRegionRef.current = r;
          setRegion(r);
          setRegionError(null);
        });
    },
    [publishRegion],
  );

  // Sync the agent to the picker whenever we connect or the agent joins.
  useEffect(() => {
    if (connState !== ConnectionState.Connected) return;
    const sync = () => {
      // Re-send the UI's current selection (may be in-flight), not only the last commit,
      // so an agent join during a pending EU switch cannot overwrite it back to US.
      runRegionOp(filterRegionRef.current, {
        clearResults: false,
        failMessage: "Couldn't sync region with the agent — try again.",
      });
    };
    sync();
    const onParticipant = () => sync();
    room.on(RoomEvent.ParticipantConnected, onParticipant);
    return () => {
      room.off(RoomEvent.ParticipantConnected, onParticipant);
    };
  }, [connState, runRegionOp, room]);

  const selectRegion = (r: Region) => {
    if (r === region) return;
    runRegionOp(r, {
      clearResults: true,
      failMessage: "Couldn't update region — try again.",
    });
  };

  return (
    <div className="card">
      <div className="retrieval-head">
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
              onClick={() => selectRegion(r)}
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
      {regionError ? (
        <div role="alert" style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "#e8a0a0", marginTop: 6 }}>
          {regionError}
        </div>
      ) : null}

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
