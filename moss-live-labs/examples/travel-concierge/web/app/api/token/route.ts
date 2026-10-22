import { NextResponse } from "next/server";
import { AccessToken, type VideoGrant } from "livekit-server-sdk";

// Copy web/.env.local.example to web/.env.local to get the `livekit-server --dev` defaults.
const LIVEKIT_URL = process.env.LIVEKIT_URL;
const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;

export const revalidate = 0;

export async function GET() {
  try {
    if (!LIVEKIT_URL) throw new Error("LIVEKIT_URL is not defined");
    if (!API_KEY) throw new Error("LIVEKIT_API_KEY is not defined");
    if (!API_SECRET) throw new Error("LIVEKIT_API_SECRET is not defined");

    // collision-resistant so concurrent visitors never share a room (and its audio / moss.retrieval data)
    const roomName = `travel-demo-${crypto.randomUUID()}`;
    const identity = `user-${crypto.randomUUID()}`;

    const at = new AccessToken(API_KEY, API_SECRET, { identity, name: "You", ttl: "15m" });
    const grant: VideoGrant = {
      room: roomName,
      roomJoin: true,
      canPublish: true, // publish mic
      canPublishData: true,
      canSubscribe: true,
    };
    at.addGrant(grant);

    return NextResponse.json(
      { serverUrl: LIVEKIT_URL, roomName, participantToken: await at.toJwt() },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Unknown error";
    return new NextResponse(msg, { status: 500 });
  }
}
