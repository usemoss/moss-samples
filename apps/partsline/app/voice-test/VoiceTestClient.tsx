"use client";

import { useEffect, useState } from "react";
import { RoomAudioRenderer, RoomContext } from "@livekit/components-react";
import { Room, RoomEvent, type AudioCaptureOptions } from "livekit-client";

type TokenResponse = {
  server_url: string;
  participant_token: string;
};

type TranscriptLine = {
  id: string;
  isFinal: boolean;
  text: string;
};

type AudioWindow = Window &
  typeof globalThis & {
    webkitAudioContext?: typeof AudioContext;
  };

const AUDIO_CAPTURE_OPTIONS: AudioCaptureOptions = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

function uniqueName(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

async function unlockBrowserAudio() {
  const AudioContextClass =
    window.AudioContext ?? (window as AudioWindow).webkitAudioContext;

  if (!AudioContextClass) {
    return;
  }

  const audioContext = new AudioContextClass();
  await audioContext.resume();
  await audioContext.close();
}

async function requestMicrophoneAccess() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  stream.getTracks().forEach((track) => track.stop());
}

export default function VoiceTestClient() {
  const [room, setRoom] = useState<Room | null>(null);
  const [status, setStatus] = useState("Idle");
  const [transcriptLines, setTranscriptLines] = useState<TranscriptLine[]>([]);

  useEffect(() => {
    if (!room) {
      return;
    }

    const resetConnectionState = () => {
      setRoom(null);
      setStatus("Idle");
    };

    const handleParticipantDisconnected = () => {
      void room.disconnect();
      resetConnectionState();
    };

    room.on(RoomEvent.Disconnected, resetConnectionState);
    room.on(RoomEvent.ParticipantDisconnected, handleParticipantDisconnected);

    return () => {
      room.off(RoomEvent.Disconnected, resetConnectionState);
      room.off(RoomEvent.ParticipantDisconnected, handleParticipantDisconnected);
      void room.disconnect();
    };
  }, [room]);

  async function connect() {
    if (room) {
      return;
    }

    setStatus("Requesting microphone");
    await requestMicrophoneAccess();
    await unlockBrowserAudio();

    const room_name = uniqueName("partsline-voice-test");
    const participant_identity = uniqueName("browser");

    setStatus("Fetching token");
    const tokenResponse = await fetch("/api/token", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ room_name, participant_identity }),
    });

    if (!tokenResponse.ok) {
      throw new Error("token-request-failed");
    }

    const { server_url, participant_token } =
      (await tokenResponse.json()) as TokenResponse;

    const nextRoom = new Room({
      audioCaptureDefaults: AUDIO_CAPTURE_OPTIONS,
    });

    nextRoom.registerTextStreamHandler("lk.transcription", async (reader) => {
      const text = await reader.readAll();
      const attributes = reader.info.attributes ?? {};
      const isFinal = attributes["lk.transcription_final"] === "true";

      setTranscriptLines((current) => [
        ...current,
        {
          id: `${Date.now()}-${current.length}`,
          isFinal,
          text,
        },
      ]);
    });

    setStatus("Connecting");
    await nextRoom.connect(server_url, participant_token);
    await nextRoom.localParticipant.setMicrophoneEnabled(
      true,
      AUDIO_CAPTURE_OPTIONS,
    );

    setRoom(nextRoom);
    setStatus("Connected");
  }

  return (
    <main>
      <h1>PartsLine Voice Test</h1>
      <button
        type="button"
        onClick={connect}
        disabled={status !== "Idle"}
      >Connect</button>
      <p>Status: {status}</p>
      <section aria-live="polite">
        <h2>Transcript</h2>
        {transcriptLines.length === 0 ? (
          <p>No transcript yet.</p>
        ) : (
          <ol>
            {transcriptLines.map((line) => (
              <li key={line.id}>
                {line.isFinal ? "Final" : "Interim"}: {line.text}
              </li>
            ))}
          </ol>
        )}
      </section>
      {room ? (
        <RoomContext.Provider value={room}>
          <RoomAudioRenderer />
        </RoomContext.Provider>
      ) : null}
    </main>
  );
}
