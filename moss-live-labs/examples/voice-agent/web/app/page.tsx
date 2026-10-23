"use client";

import { useCallback, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { AgentSide } from "@/components/AgentSide";
import { RetrievalPanel } from "@/components/RetrievalPanel";

type Conn = { serverUrl: string; roomName: string; participantToken: string };

export default function Page() {
  const [conn, setConn] = useState<Conn | null>(null);
  const [connecting, setConnecting] = useState(false);

  const connect = useCallback(async () => {
    setConnecting(true);
    try {
      const res = await fetch("/api/token");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as Conn;
      setConn(data);
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
          <span className="title">Northwind Support · voice agent</span>
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
          <RetrievalPanel />
          <RoomAudioRenderer />
        </LiveKitRoom>
      ) : (
        <main className="main" style={{ gridTemplateColumns: "1fr" }}>
          <div className="card connect">
            <h1>
              Talk to a support agent that <span className="accent">actually knows</span> the answers.
            </h1>
            <p>
              Grounded in a Moss knowledge base. Ask a question out loud and watch Moss retrieve the
              answer live, on-device, in milliseconds.
            </p>
            <button className="btn" onClick={connect} disabled={connecting}>
              {connecting ? "Connecting…" : "Start the demo"}
            </button>
          </div>
        </main>
      )}

      <footer className="footer">
        <a href="https://docs.moss.dev" target="_blank" rel="noreferrer">
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
