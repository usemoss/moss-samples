"use client";

import { useCallback, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { AgentSide } from "@/components/AgentSide";
import { DualPanel } from "@/components/DualPanel";

type Conn = { serverUrl: string; roomName: string; participantToken: string };

export default function Page() {
  const [conn, setConn] = useState<Conn | null>(null);
  const [connecting, setConnecting] = useState(false);

  const connect = useCallback(async () => {
    setConnecting(true);
    try {
      const res = await fetch("/api/token");
      if (!res.ok) throw new Error(await res.text());
      setConn((await res.json()) as Conn);
    } catch (err) {
      console.error("failed to get token", err);
      alert("Could not reach the token endpoint. Is the app running and LiveKit reachable?");
    } finally {
      setConnecting(false);
    }
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/moss-wordmark.svg" alt="Moss" />
          <span className="divider" />
          <span className="title">Wander · travel concierge</span>
        </div>
        <div className={`status ${conn ? "live" : ""}`}>
          <span className="dot" />
          {conn ? "live" : "offline"}
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
          onDisconnected={() => setConn(null)}
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
              Ask about destinations from the catalog, tell it your budget, dates, and who's coming.
              Watch Moss pull from the pre-loaded catalog and your live conversation, together.
            </p>
            <button className="btn" onClick={connect} disabled={connecting}>
              {connecting ? "Connecting…" : "Start planning"}
            </button>
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
