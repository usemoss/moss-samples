"use client";

import { useCallback, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { AgentSide } from "@/components/AgentSide";
import { DualPanel } from "@/components/DualPanel";

type Conn = { serverUrl: string; roomName: string; participantToken: string };

export default function Page() {
  const [conn, setConn] = useState<Conn | null>(null);
  const [roomLive, setRoomLive] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [needsGate, setNeedsGate] = useState(false);
  const [gateSecret, setGateSecret] = useState("");

  const reset = useCallback(() => {
    setConn(null);
    setRoomLive(false);
  }, []);

  const fetchToken = useCallback(async () => {
    const res = await fetch("/api/token");
    if (res.status === 401) {
      setNeedsGate(true);
      throw new Error("gate");
    }
    if (res.status === 429) {
      throw new Error("rate-limit");
    }
    if (!res.ok) throw new Error(await res.text());
    return (await res.json()) as Conn;
  }, []);

  const connect = useCallback(async () => {
    setConnecting(true);
    try {
      if (needsGate && gateSecret) {
        const gateRes = await fetch("/api/gate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ secret: gateSecret }),
        });
        if (gateRes.status === 401) {
          alert("Access code rejected.");
          return;
        }
        if (gateRes.status === 429) {
          alert("Too many attempts. Please wait and try again.");
          return;
        }
        if (!gateRes.ok) {
          alert("Could not unlock the demo. Please try again.");
          return;
        }
        // Cookie is set — clear the code now so a later token failure retries with the cookie only.
        setGateSecret("");
        setNeedsGate(false);
      }
      const next = await fetchToken();
      setConn(next);
      setRoomLive(false);
    } catch (err) {
      if (err instanceof Error && err.message === "gate") {
        // Prompt for access code; do not alert.
        return;
      }
      if (err instanceof Error && err.message === "rate-limit") {
        alert("Too many requests. Please wait and try again.");
        return;
      }
      console.error("failed to get token", err);
      alert("Could not reach the token endpoint. Is the app running and LiveKit reachable?");
      reset();
    } finally {
      setConnecting(false);
    }
  }, [fetchToken, gateSecret, needsGate, reset]);

  const statusLabel = connecting
    ? "connecting"
    : conn
      ? roomLive
        ? "live"
        : "connecting"
      : "offline";

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/moss-wordmark.svg" alt="Moss" />
          <span className="divider" />
          <span className="title">Wander · travel concierge</span>
        </div>
        <div className={`status ${roomLive ? "live" : ""}`}>
          <span className="dot" />
          {statusLabel}
        </div>
      </header>

      {conn ? (
        <LiveKitRoom
          className="main"
          serverUrl={conn.serverUrl}
          token={conn.participantToken}
          connect
          audio
          video={false}
          onConnected={() => setRoomLive(true)}
          onError={(err) => {
            console.error("LiveKit room error", err);
            alert("Could not connect to the voice room. Check LiveKit and try again.");
            reset();
          }}
          onDisconnected={() => reset()}
        >
          <AgentSide />
          <DualPanel />
          <RoomAudioRenderer />
        </LiveKitRoom>
      ) : (
        <main className="main" style={{ gridTemplateColumns: "1fr" }}>
          <div className="card connect">
            <h1>
              Plan a trip out loud — it <span className="accent">remembers</span> what you say.
            </h1>
            <p>
              Ask about destinations from the catalog, tell it your budget, dates, and who&apos;s coming.
              Watch Moss pull from the pre-loaded catalog and your live conversation, together.
            </p>
            <form
              className="connect-form"
              onSubmit={(e) => {
                e.preventDefault();
                void connect();
              }}
            >
              {needsGate && (
                <label className="gate">
                  <span>Access code</span>
                  <input
                    type="password"
                    autoComplete="off"
                    value={gateSecret}
                    onChange={(e) => setGateSecret(e.target.value)}
                    placeholder="Enter APP_SECRET"
                  />
                </label>
              )}
              <button
                type="submit"
                className="btn"
                disabled={connecting || (needsGate && !gateSecret)}
              >
                {connecting ? "Connecting…" : needsGate ? "Unlock & start" : "Start planning"}
              </button>
            </form>
          </div>
        </main>
      )}

      <footer className="footer">
        <a href="https://docs.moss.dev/docs/integrate/sessions" target="_blank" rel="noreferrer">
          docs.moss.dev
        </a>
        <span className="sep">·</span>
        <a href="https://github.com/usemoss/moss" target="_blank" rel="noreferrer">
          github.com/usemoss/moss
        </a>
      </footer>
    </div>
  );
}
