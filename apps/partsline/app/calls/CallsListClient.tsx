"use client";

import { useEffect, useState, type CSSProperties } from "react";
import type { CallLogRow } from "./callLog";

type CallsApiResponse = {
  calls: CallLogRow[];
};

function formatVehicle(call: CallLogRow) {
  return [
    call.vehicle.year,
    call.vehicle.make,
    call.vehicle.model,
    call.vehicle.engine ? `${call.vehicle.engine} engine` : "",
    call.vehicle.trim,
  ]
    .filter(Boolean)
    .join(" ");
}

function formatParts(call: CallLogRow) {
  if (call.parts.length === 0) {
    return "No parts recorded";
  }

  return call.parts
    .map((part) => {
      const details = [
        part.part_number,
        part.name,
        part.price ? `$${part.price}` : "",
        part.stock !== undefined ? `stock ${part.stock}` : "",
      ].filter(Boolean);
      return details.join(" - ");
    })
    .join("; ");
}

function formatOutcome(outcome: string) {
  return outcome.replaceAll("_", " ");
}

function formatTime(value: string) {
  return new Date(value).toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function CallsListClient() {
  const [calls, setCalls] = useState<CallLogRow[] | null>(null);

  useEffect(() => {
    let active = true;

    async function loadCalls() {
      const response = await fetch("/api/calls", { cache: "no-store" });
      if (!response.ok) {
        throw new Error("calls-request-failed");
      }
      const body = (await response.json()) as CallsApiResponse;
      if (active) {
        setCalls(body.calls);
      }
    }

    void loadCalls().catch(() => {
      if (active) {
        setCalls([]);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <main style={styles.shell}>
      <section style={styles.header}>
        <div>
          <p style={styles.kicker}>PartsLine</p>
          <h1 style={styles.title}>Call log</h1>
        </div>
        <div style={styles.count}>{calls?.length ?? 0} calls</div>
      </section>

      <section style={styles.list}>
        {calls === null ? <p style={styles.empty}>Loading calls.</p> : null}
        {calls?.length === 0 ? <p style={styles.empty}>No calls yet.</p> : null}
        {calls && calls.length > 0
          ? calls.map((call) => (
              <article key={call.call_id} style={styles.row}>
                <time dateTime={call.started_at} style={styles.time}>
                  {formatTime(call.started_at)}
                </time>
                <div style={styles.primary}>
                  <h2 style={styles.vehicle}>{formatVehicle(call)}</h2>
                  <p style={styles.parts}>{formatParts(call)}</p>
                </div>
                <div style={styles.meta}>
                  <span style={styles.outcome}>{formatOutcome(call.outcome)}</span>
                  {call.set_aside?.first_name ? (
                    <span style={styles.setAside}>
                      Hold: {call.set_aside.first_name}
                    </span>
                  ) : null}
                </div>
              </article>
            ))
          : null}
      </section>
    </main>
  );
}

const styles = {
  shell: {
    minHeight: "100vh",
    background: "#f5f7f9",
    color: "#16202a",
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "24px",
    padding: "28px 32px",
    borderBottom: "1px solid #d9e1e8",
    background: "#ffffff",
  },
  kicker: {
    margin: 0,
    color: "#3f6f8f",
    fontSize: "13px",
    fontWeight: 700,
    letterSpacing: 0,
  },
  title: {
    margin: "4px 0 0",
    fontSize: "28px",
    lineHeight: 1.15,
    letterSpacing: 0,
  },
  count: {
    minWidth: "96px",
    padding: "8px 12px",
    border: "1px solid #c9d5df",
    borderRadius: "6px",
    background: "#eef3f6",
    textAlign: "center" as const,
    fontSize: "14px",
  },
  list: {
    display: "grid",
    gap: "10px",
    padding: "24px 32px",
  },
  empty: {
    margin: 0,
    padding: "20px",
    border: "1px solid #d8e0e6",
    borderRadius: "6px",
    background: "#ffffff",
    color: "#65717c",
  },
  row: {
    display: "grid",
    gridTemplateColumns: "180px minmax(0, 1fr) 160px",
    gap: "18px",
    alignItems: "start",
    padding: "16px",
    border: "1px solid #d8e0e6",
    borderRadius: "6px",
    background: "#ffffff",
  },
  time: {
    color: "#546675",
    fontSize: "14px",
  },
  primary: {
    display: "grid",
    gap: "6px",
    minWidth: 0,
  },
  vehicle: {
    margin: 0,
    fontSize: "17px",
    lineHeight: 1.25,
    letterSpacing: 0,
  },
  parts: {
    margin: 0,
    color: "#425260",
    fontSize: "14px",
    lineHeight: 1.4,
  },
  meta: {
    display: "grid",
    justifyItems: "start",
    gap: "8px",
  },
  outcome: {
    padding: "4px 8px",
    borderRadius: "4px",
    background: "#e8f4ef",
    color: "#1f5e4e",
    fontSize: "13px",
    fontWeight: 700,
    textTransform: "capitalize" as const,
  },
  setAside: {
    color: "#455766",
    fontSize: "14px",
  },
} satisfies Record<string, CSSProperties>;
