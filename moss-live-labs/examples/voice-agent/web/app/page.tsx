"use client";

import { useCallback, useRef, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { AgentSide } from "@/components/AgentSide";
import { RetrievalPanel } from "@/components/RetrievalPanel";

type Conn = { serverUrl: string; participantToken: string };

const TOKEN_TIMEOUT_MS = 12_000;

export default function Page() {
  const [conn, setConn] = useState<Conn | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [roomLive, setRoomLive] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const connect = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), TOKEN_TIMEOUT_MS);

    setConnecting(true);
    try {
      const res = await fetch("/api/token", { signal: controller.signal });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as Conn;
      setRoomLive(false);
      setConn(data);
    } catch (err) {
      if (controller.signal.aborted) {
        console.error("token request timed out or was cancelled", err);
        alert("Connecting timed out. Is the app running and LiveKit reachable?");
      } else {
        console.error("failed to get token", err);
        alert("Could not reach the token endpoint. Is the app running and LiveKit reachable?");
      }
    } finally {
      window.clearTimeout(timeout);
      setConnecting(false);
    }
  }, []);

  const statusLabel = roomLive ? "live" : conn ? "connecting" : "offline";

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/moss-wordmark.svg" alt="Moss" />
          <span className="divider" />
          <span className="title">Northwind Support · voice agent</span>
        </div>
        <div className={`status ${roomLive ? "live" : ""}`} role="status" aria-live="polite">
          <span className="dot" />
          {statusLabel}
        </div>
      </header>

      {conn ? (
        <LiveKitRoom
          className="main"
          role="main"
          serverUrl={conn.serverUrl}
          token={conn.participantToken}
          connect
          audio
          video={false}
          onConnected={() => setRoomLive(true)}
          onDisconnected={() => {
            setRoomLive(false);
            setConn(null);
          }}
          onError={(err) => {
            console.error("LiveKit room error", err);
            alert(
              err?.message?.toLowerCase().includes("permission") ||
                err?.message?.toLowerCase().includes("device")
                ? "Microphone access failed. Allow mic permission and try again."
                : `Connection error: ${err?.message ?? "unknown"}. Disconnect and retry.`,
            );
          }}
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
