import "server-only";

import { createHash } from "node:crypto";
import type { DraftPick, DraftPlayer, Position, ScoutSearchHit, SquadProfile } from "./types";
import { explainScoutMatch, getScoutPlayer, SCOUT_DOCUMENTS, SCOUT_INDEX_NAME } from "./scout-data";
import {
  buildSquadDnaQuery,
  profileCustomXi,
  rankSquadDna,
  SQUAD_DNA_DOCUMENTS,
  SQUAD_DNA_INDEX_NAME,
  SQUAD_PROFILES,
} from "./squad-dna";

type MossClientInstance = import("@moss-dev/moss").MossClient;

type CachedMossClient = {
  client: MossClientInstance;
  indexes: Map<string, Promise<{ created: boolean; count: number }>>;
  touchedAt: number;
};

declare global {
  var championsMossScoutClients: Map<string, CachedMossClient> | undefined;
}

const mossClients = globalThis.championsMossScoutClients ?? new Map<string, CachedMossClient>();
globalThis.championsMossScoutClients = mossClients;

function cacheKey(projectId: string, projectKey: string) {
  const fingerprint = createHash("sha256").update(projectKey).digest("hex").slice(0, 16);
  return `${projectId}:${fingerprint}`;
}

async function trimClientCache() {
  if (mossClients.size < 4) return;
  const oldest = [...mossClients.entries()].sort((a, b) => a[1].touchedAt - b[1].touchedAt)[0];
  if (!oldest) return;
  mossClients.delete(oldest[0]);
  await oldest[1].client.close().catch(() => undefined);
}

async function getClient(projectId: string, projectKey: string) {
  const key = cacheKey(projectId, projectKey);
  const cached = mossClients.get(key);
  if (cached) {
    cached.touchedAt = Date.now();
    return cached;
  }

  await trimClientCache();
  const { MossClient } = await import("@moss-dev/moss");
  const entry: CachedMossClient = {
    client: new MossClient(projectId, projectKey),
    indexes: new Map(),
    touchedAt: Date.now(),
  };
  mossClients.set(key, entry);
  return entry;
}

async function ensureIndex(input: {
  projectId: string;
  projectKey: string;
  name: string;
  documents: Array<{ id: string; text: string; metadata: Record<string, string>; payload: string }>;
}) {
  const entry = await getClient(input.projectId, input.projectKey);
  const existingReady = entry.indexes.get(input.name);
  if (existingReady) return { client: entry.client, ...(await existingReady) };

  const ready = (async () => {
    const indexes = await entry.client.listIndexes();
    const existing = indexes.find((index) => index.name === input.name);
    let created = false;
    if (!existing) {
      await entry.client.createIndex(input.name, input.documents, { modelId: "moss-minilm" });
      created = true;
    } else if (existing.docCount !== input.documents.length) {
      throw new Error(`The Moss index ${input.name} has ${existing.docCount} documents instead of ${input.documents.length}.`);
    }
    await entry.client.loadIndex(input.name);
    return { created, count: input.documents.length };
  })();
  entry.indexes.set(input.name, ready);
  try {
    return { client: entry.client, ...(await ready) };
  } catch (error) {
    entry.indexes.delete(input.name);
    throw error;
  }
}

function getReadyPlayerIndex(projectId: string, projectKey: string) {
  return ensureIndex({ projectId, projectKey, name: SCOUT_INDEX_NAME, documents: SCOUT_DOCUMENTS });
}

function getReadyDnaIndex(projectId: string, projectKey: string) {
  return ensureIndex({ projectId, projectKey, name: SQUAD_DNA_INDEX_NAME, documents: SQUAD_DNA_DOCUMENTS });
}

export async function connectMossScout(projectId: string, projectKey: string) {
  const startedAt = Date.now();
  const { created, count } = await getReadyPlayerIndex(projectId, projectKey);
  return { created, count, indexName: SCOUT_INDEX_NAME, loadTimeMs: Date.now() - startedAt };
}

export async function connectMossDna(projectId: string, projectKey: string) {
  const startedAt = Date.now();
  const { created, count } = await getReadyDnaIndex(projectId, projectKey);
  return { created, count, indexName: SQUAD_DNA_INDEX_NAME, loadTimeMs: Date.now() - startedAt };
}

export async function searchMossScout(input: {
  projectId: string;
  projectKey: string;
  query: string;
  position?: Position;
  year?: number;
  nation?: string;
  topK?: number;
}) {
  const { client } = await getReadyPlayerIndex(input.projectId, input.projectKey);
  const topK = Math.min(Math.max(input.topK ?? 18, 1), 30);
  const filters = [
    ...(input.position ? [{ field: "position", condition: { $eq: input.position } }] : []),
    ...(input.year ? [{ field: "year", condition: { $eq: String(input.year) } }] : []),
    ...(input.nation ? [{ field: "nation", condition: { $eq: input.nation } }] : []),
  ];
  const startedAt = Date.now();
  const result = await client.query(SCOUT_INDEX_NAME, input.query, {
    topK,
    alpha: 0.78,
    ...(filters.length === 1 ? { filter: filters[0] } : filters.length > 1 ? { filter: { $and: filters } } : {}),
  });

  const hits = result.docs.flatMap<ScoutSearchHit>((document) => {
    let player: DraftPlayer | null = null;
    if (document.payload) {
      try { player = JSON.parse(document.payload) as DraftPlayer; } catch { player = null; }
    }
    player ??= getScoutPlayer(document.id);
    if (!player) return [];
    return [{ player, score: document.score, explanation: explainScoutMatch(player) }];
  });

  return { hits, timeTakenMs: result.timeTakenInMs ?? Date.now() - startedAt, indexName: SCOUT_INDEX_NAME };
}

export async function analyzeSquadDna(input: { projectId: string; projectKey: string; xi: DraftPick[] }) {
  const { client } = await getReadyDnaIndex(input.projectId, input.projectKey);
  const custom = profileCustomXi(input.xi);
  const result = await client.query(SQUAD_DNA_INDEX_NAME, buildSquadDnaQuery(custom), { topK: 80, alpha: 0.72 });
  const candidates = result.docs.flatMap<{ profile: SquadProfile; mossScore: number }>((document) => {
    let profile: SquadProfile | undefined;
    if (document.payload) {
      try { profile = JSON.parse(document.payload) as SquadProfile; } catch { profile = undefined; }
    }
    profile ??= SQUAD_PROFILES.find((item) => item.id === document.id);
    return profile ? [{ profile, mossScore: document.score }] : [];
  });
  return { result: rankSquadDna(custom, candidates), timeTakenMs: result.timeTakenInMs };
}

export function friendlyMossError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes("401") || normalized.includes("403") || normalized.includes("unauthor") || normalized.includes("project key") || normalized.includes("authentication")) {
    return { status: 401, message: "Moss rejected those credentials. Check the project ID and project key, then try again." };
  }
  if (normalized.includes("429") || normalized.includes("rate limit") || normalized.includes("usage limit") || normalized.includes("quota") || normalized.includes("maximum number")) {
    return { status: 429, message: "This Moss project has reached an index or usage limit. Remove an unused index or check the project plan." };
  }
  if (normalized.includes("fetch") || normalized.includes("network") || normalized.includes("connect")) {
    return { status: 502, message: "The app could not reach Moss. Check your connection and try again." };
  }
  return { status: 500, message: "Moss could not prepare the requested archive index. Try again in a moment." };
}
