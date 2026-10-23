"use client";

import { useCallback, useState } from "react";
import { useDataChannel } from "@livekit/components-react";
import type { Doc, RetrievalPayload } from "@/lib/types";

// Reused across data-channel messages to avoid allocating a decoder per update.
const decoder = new TextDecoder();

function isDoc(value: unknown): value is Doc {
  if (!value || typeof value !== "object") return false;
  const d = value as Record<string, unknown>;
  // Match Doc.id: string | undefined only (reject number/null to keep the type guard sound).
  const idOk = d.id === undefined || typeof d.id === "string";
  return (
    idOk &&
    typeof d.text === "string" &&
    typeof d.score === "number" &&
    Number.isFinite(d.score)
  );
}

function normalizeDoc(d: Doc, index: number): Doc & { key: string } {
  const key = d.id && d.id.length > 0 ? d.id : `idx-${index}`;
  return { ...d, id: key, key };
}

function isRetrievalPayload(value: unknown): value is RetrievalPayload {
  if (!value || typeof value !== "object") return false;
  const p = value as Record<string, unknown>;
  return (
    typeof p.query === "string" &&
    Array.isArray(p.catalog) &&
    p.catalog.every(isDoc) &&
    Array.isArray(p.session) &&
    p.session.every(isDoc) &&
    typeof p.catalog_ms === "number" &&
    Number.isFinite(p.catalog_ms) &&
    typeof p.session_ms === "number" &&
    Number.isFinite(p.session_ms)
  );
}

function Hits({ docs, empty }: { docs: Doc[]; empty: string }) {
  if (!docs.length) return <div className="panel-empty">{empty}</div>;
  return (
    <div className="hits">
      {docs.map((d, i) => {
        const doc = normalizeDoc(d, i);
        const pct = Math.max(0, Math.min(1, doc.score)) * 100;
        return (
          <div className="hit" key={doc.key}>
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
        const parsed: unknown = JSON.parse(decoder.decode(msg.payload));
        if (!isRetrievalPayload(parsed)) {
          console.error("ignored malformed moss.retrieval payload", parsed);
          return;
        }
        setData(parsed);
      } catch (err) {
        console.error("failed to parse moss.retrieval payload", err);
      }
    }, []),
  );

  const status =
    data == null
      ? "Waiting for retrieval results."
      : `Updated retrieval for “${data.query}”: ${data.catalog.length} catalog hits, ${data.session.length} session facts.`;

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

      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {status}
      </div>

      <div className="panels">
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
          <Hits
            docs={data?.session ?? []}
            empty="Nothing yet. Tell the concierge about your trip and it remembers it here."
          />
        </div>
      </div>
    </div>
  );
}
