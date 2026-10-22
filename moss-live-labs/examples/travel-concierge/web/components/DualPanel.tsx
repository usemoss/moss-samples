"use client";

import { useCallback, useState } from "react";
import { useDataChannel } from "@livekit/components-react";
import type { Doc, RetrievalPayload } from "@/lib/types";

// Reused across data-channel messages to avoid allocating a decoder per update.
const decoder = new TextDecoder();

function Hits({ docs, empty }: { docs: Doc[]; empty: string }) {
  if (!docs.length) return <div className="panel-empty">{empty}</div>;
  return (
    <div className="hits">
      {docs.map((d, i) => {
        const pct = Math.max(0, Math.min(1, d.score)) * 100;
        return (
          <div className="hit" key={d.id ?? i}>
            <div className="top">
              <div className="bar">
                <span style={{ width: `${pct}%` }} />
              </div>
              <span className="score">{d.score.toFixed(2)}</span>
            </div>
            <div className="text">{d.text}</div>
          </div>
        );
      })}
    </div>
  );
}

// Two Moss indexes, side by side: the pre-loaded catalog (cloud, long-term) and
// the live session (this call, short-term). Both update on every turn.
export function DualPanel() {
  const [data, setData] = useState<RetrievalPayload | null>(null);

  useDataChannel(
    "moss.retrieval",
    useCallback((msg: { payload: Uint8Array }) => {
      try {
        setData(JSON.parse(decoder.decode(msg.payload)) as RetrievalPayload);
      } catch (err) {
        console.error("failed to parse moss.retrieval payload", err);
      }
    }, []),
  );

  return (
    <div className="stack">
      <div className="qline">
        {data ? (
          <>
            you asked: <b>{data.query}</b>
          </>
        ) : (
          "Two Moss indexes, one call — the catalog you're browsing and everything you say."
        )}
      </div>

      <div className="card panel panel--cloud">
        <div className="panel-head">
          <span className="label">
            <span className="dot-sq" />
            Catalog · cloud index
          </span>
          <span className="tag">{data ? `${data.catalog_ms.toFixed(1)}ms · pre-loaded` : "pre-loaded"}</span>
        </div>
        <Hits docs={data?.catalog ?? []} empty="Trips matching your question show up here." />
      </div>

      <div className="card panel panel--live">
        <div className="panel-head">
          <span className="label">
            <span className="dot-sq" />
            This call · live session
          </span>
          <span className="tag">{data ? `${data.session_ms.toFixed(1)}ms · in-memory` : "in-memory"}</span>
        </div>
        <Hits docs={data?.session ?? []} empty="Nothing yet. Tell the concierge about your trip and it remembers it here." />
      </div>
    </div>
  );
}
