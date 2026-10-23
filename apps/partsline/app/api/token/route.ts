import { createHmac, randomUUID } from "node:crypto";

export const runtime = "nodejs";

const DEFAULT_ROOM_NAME = "partsline-voice-test";
const AGENT_NAME = "partsline-retrieval";
const TOKEN_TTL_SECONDS = 10 * 60;

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error("missing-livekit-config");
  }
  return value;
}

function readLiveKitConfig() {
  return {
    serverUrl: requiredEnv("LIVEKIT_URL"),
    apiKey: requiredEnv("LIVEKIT_API_KEY"),
    apiSecret: requiredEnv("LIVEKIT_API_SECRET"),
  };
}

function nonEmptyString(value, fallback) {
  return typeof value === "string" && value.trim() ? value : fallback;
}

async function readJsonBody(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

function encodeBase64Url(value) {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function signHs256(value, secret) {
  return createHmac("sha256", secret).update(value).digest("base64url");
}

export function createParticipantToken({
  apiKey,
  apiSecret,
  roomName,
  participantIdentity,
  nowSeconds = Math.floor(Date.now() / 1000),
}) {
  const header = { alg: "HS256", typ: "JWT" };
  const claims = {
    iss: apiKey,
    sub: participantIdentity,
    nbf: nowSeconds,
    exp: nowSeconds + TOKEN_TTL_SECONDS,
    video: {
      room: roomName,
      roomJoin: true,
      canPublish: true,
      canPublishData: true,
      canSubscribe: true,
    },
    roomConfig: {
      agents: [{ agentName: AGENT_NAME }],
    },
  };

  const unsignedToken = `${encodeBase64Url(header)}.${encodeBase64Url(claims)}`;
  return `${unsignedToken}.${signHs256(unsignedToken, apiSecret)}`;
}

export async function POST(request) {
  let config;
  try {
    config = readLiveKitConfig();
  } catch {
    return Response.json(
      { error: "LiveKit environment is not configured" },
      { status: 500 },
    );
  }

  const body = await readJsonBody(request);
  const roomName = nonEmptyString(body.room_name, DEFAULT_ROOM_NAME);
  const participantIdentity = nonEmptyString(
    body.participant_identity,
    `browser-${randomUUID()}`,
  );

  const participantToken = createParticipantToken({
    apiKey: config.apiKey,
    apiSecret: config.apiSecret,
    roomName,
    participantIdentity,
  });

  return Response.json(
    {
      server_url: config.serverUrl,
      participant_token: participantToken,
    },
    { status: 201 },
  );
}
