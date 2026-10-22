import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { MossClient, type DocumentInfo, type SessionIndex } from "@moss-dev/moss";
import { configValue } from "@/lib/runtime-config";

export type JarvisTask = {
  title: string;
  due?: string;
  recurrence?: string;
  priority?: "low" | "normal" | "high";
};

export type RetrievedMemory = {
  id: string;
  text: string;
  score?: number;
  metadata?: Record<string, unknown>;
  source: "working" | "long-term";
};

export type BrainMemory = {
  id: string;
  title: string;
  source: string;
  heading: string;
  type: string;
  text: string;
  createdAt: string;
  score?: number;
  tags: string[];
  url?: string;
};

export type BrainGraph = {
  nodes: Array<{ id: string; title: string; type: string; chunks: number; degree: number }>;
  edges: Array<{ a: string; b: string; weight: number }>;
};

type StoredDocument = Omit<DocumentInfo, "metadata"> & { metadata?: Record<string, unknown> };

type JarvisSession = {
  id: string;
  startedAt: string;
  client: MossClient | null;
  localIndex: SessionIndex | null;
  working: StoredDocument[];
  documents: StoredDocument[];
  longTermIndex: string;
  memoryOnline: boolean;
  localMossReady: boolean;
  memoryError?: string;
};

type LocalStore = {
  version: 1;
  updatedAt: string;
  documents: StoredDocument[];
};

const globalState = globalThis as typeof globalThis & {
  __jarvisSessions?: Map<string, JarvisSession>;
};

const sessions = globalState.__jarvisSessions ?? new Map<string, JarvisSession>();
globalState.__jarvisSessions = sessions;

function dataDirectory() {
  return process.env.JARVIS_DATA_DIR?.trim() || path.join(process.cwd(), ".jarvis-data");
}

function memoryFile() {
  return path.join(dataDirectory(), "second-brain.json");
}

function localMossFile() {
  return path.join(dataDirectory(), "second-brain.moss");
}

function bootstrapDocument(): StoredDocument {
  return {
    id: "jarvis-memory-bootstrap",
    text: "Jarvis persistent second brain initialized.",
    metadata: { type: "system", createdAt: new Date().toISOString() },
  };
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function validDocument(value: unknown): value is StoredDocument {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<StoredDocument>;
  return typeof candidate.id === "string" && typeof candidate.text === "string";
}

function mergeDocuments(...groups: StoredDocument[][]) {
  const merged = new Map<string, StoredDocument>();
  for (const group of groups) {
    for (const doc of group) {
      if (validDocument(doc)) merged.set(doc.id, doc);
    }
  }
  return [...merged.values()];
}

async function readLocalDocuments() {
  try {
    const parsed = JSON.parse(await readFile(memoryFile(), "utf8")) as Partial<LocalStore>;
    const docs = Array.isArray(parsed.documents) ? parsed.documents.filter(validDocument) : [];
    return docs.length ? docs : [bootstrapDocument()];
  } catch (error) {
    if ((error as NodeJS.ErrnoException)?.code !== "ENOENT") {
      console.error("Jarvis local memory read failed", error);
    }
    return [bootstrapDocument()];
  }
}

async function writeLocalDocuments(documents: StoredDocument[]) {
  const directory = dataDirectory();
  const destination = memoryFile();
  const temporary = `${destination}.${process.pid}.tmp`;
  const payload: LocalStore = {
    version: 1,
    updatedAt: new Date().toISOString(),
    documents,
  };
  await mkdir(directory, { recursive: true });
  await writeFile(temporary, JSON.stringify(payload, null, 2), { encoding: "utf8", mode: 0o600 });
  await rename(temporary, destination);
}

function credentials() {
  const projectId = configValue("mossProjectId", "MOSS_PROJECT_ID");
  const projectKey = configValue("mossProjectKey", "MOSS_PROJECT_KEY");
  return projectId && projectKey ? { projectId, projectKey } : null;
}

function toMemory(
  docs: Array<{ id: string; text: string; score?: number; metadata?: Record<string, unknown> }>,
  source: RetrievedMemory["source"],
): RetrievedMemory[] {
  return docs.map((doc) => ({ ...doc, source }));
}

function tokens(value: string) {
  return new Set(value.toLowerCase().match(/[a-z0-9]{2,}/g) || []);
}

const EMBEDDING_DIMENSIONS = 384;

function hashFeature(value: string, seed = 2166136261) {
  let hash = seed >>> 0;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function localEmbedding(value: string) {
  const vector = Array.from({ length: EMBEDDING_DIMENSIONS }, () => 0);
  const normalized = value.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
  const words = normalized.split(" ").filter(Boolean);
  const features = [
    ...words.map((word) => `w:${word}`),
    ...words.flatMap((word) => {
      const padded = `^${word}$`;
      return Array.from({ length: Math.max(0, padded.length - 2) }, (_, index) => `g:${padded.slice(index, index + 3)}`);
    }),
  ];

  for (const feature of features) {
    const bucket = hashFeature(feature) % EMBEDDING_DIMENSIONS;
    const sign = hashFeature(feature, 2246822519) % 2 === 0 ? 1 : -1;
    vector[bucket] += sign;
  }
  const magnitude = Math.sqrt(vector.reduce((sum, component) => sum + component * component, 0)) || 1;
  return vector.map((component) => component / magnitude);
}

function withoutEmbedding(doc: StoredDocument): StoredDocument {
  const { embedding: _embedding, ...rest } = doc;
  return rest;
}

function withEmbedding(doc: StoredDocument): DocumentInfo {
  const metadata = doc.metadata
    ? Object.fromEntries(Object.entries(doc.metadata)
      .filter(([, value]) => value !== undefined)
      .map(([key, value]) => [key, typeof value === "string" ? value : JSON.stringify(value)]))
    : undefined;
  return { id: doc.id, text: doc.text, metadata, embedding: localEmbedding(doc.text) };
}

function createdAt(doc: StoredDocument) {
  const value = typeof doc.metadata?.createdAt === "string" ? Date.parse(doc.metadata.createdAt) : 0;
  return Number.isFinite(value) ? value : 0;
}

function searchLocal(documents: StoredDocument[], query: string, topK: number) {
  const queryTokens = tokens(query);
  return documents
    .filter((doc) => doc.metadata?.type !== "system")
    .map((doc) => {
      const docTokens = tokens(doc.text);
      let overlap = 0;
      for (const token of queryTokens) if (docTokens.has(token)) overlap += 1;
      return { ...doc, score: overlap + Math.min(0.99, createdAt(doc) / 1e15) };
    })
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || createdAt(b) - createdAt(a))
    .slice(0, topK);
}

function cosineSimilarity(a: number[], b: number[]) {
  let sum = 0;
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) sum += a[index] * b[index];
  return sum;
}

function documentSource(doc: StoredDocument) {
  const explicit = typeof doc.metadata?.source === "string" ? doc.metadata.source.trim() : "";
  if (explicit) return explicit;
  const type = typeof doc.metadata?.type === "string" ? doc.metadata.type : "memory";
  const date = typeof doc.metadata?.createdAt === "string" ? doc.metadata.createdAt.slice(0, 10) : "archive";
  if (type === "conversation-summary") return `jarvis/conversations/${date}`;
  if (type === "fact") return "jarvis/facts";
  if (type === "task") return "jarvis/tasks";
  if (type === "remembered") return `remembered/${date}`;
  return `jarvis/${type}`;
}

function documentTitle(doc: StoredDocument) {
  const title = typeof doc.metadata?.title === "string" ? doc.metadata.title.trim() : "";
  if (title) return title;
  const firstLine = doc.text.replace(/^\[[^\]]+\]\s*/, "").split("\n").find((line) => line.trim())?.trim() || "Untitled memory";
  return firstLine.replace(/^#+\s*/, "").slice(0, 92);
}

function asBrainMemory(doc: StoredDocument & { score?: number }): BrainMemory {
  let tags: string[] = [];
  if (Array.isArray(doc.metadata?.tags)) {
    tags = doc.metadata.tags.filter((tag): tag is string => typeof tag === "string");
  } else if (typeof doc.metadata?.tags === "string") {
    try {
      const parsed = JSON.parse(doc.metadata.tags) as unknown;
      if (Array.isArray(parsed)) tags = parsed.filter((tag): tag is string => typeof tag === "string");
    } catch {
      tags = doc.metadata.tags.split(",").map((tag) => tag.trim()).filter(Boolean);
    }
  }
  return {
    id: doc.id,
    title: documentTitle(doc),
    source: documentSource(doc),
    heading: typeof doc.metadata?.heading === "string" ? doc.metadata.heading : "",
    type: typeof doc.metadata?.type === "string" ? doc.metadata.type : "memory",
    text: doc.text,
    createdAt: typeof doc.metadata?.createdAt === "string" ? doc.metadata.createdAt : "",
    score: doc.score,
    tags,
    url: typeof doc.metadata?.url === "string" ? doc.metadata.url : undefined,
  };
}

function recencyFactor(doc: StoredDocument, halfLifeDays = 45) {
  const timestamp = createdAt(doc);
  if (!timestamp) return 1;
  const ageDays = Math.max(0, (Date.now() - timestamp) / 86_400_000);
  return 0.45 + 0.55 * Math.exp(-ageDays / halfLifeDays);
}

async function connectAndSyncMoss(indexName: string, localDocuments: StoredDocument[]) {
  const mossCredentials = credentials();
  if (!mossCredentials) {
    return {
      client: null,
      documents: localDocuments,
      memoryOnline: false,
      memoryError: "Moss credentials are not configured. Memories are safe on local disk.",
    };
  }

  const client = new MossClient(mossCredentials.projectId, mossCredentials.projectKey);
  let stage = "listing indexes";
  try {
    const indexes = await client.listIndexes();
    const existing = indexes.find((index) => index.name === indexName);
    const exists = Boolean(existing);
    let documents = localDocuments;

    if (exists) {
      stage = "reading the existing index";
      if (existing?.model.id !== "custom") {
        throw new Error(`Existing index '${indexName}' uses ${existing?.model.id || "an unknown model"}. Delete that one index once so Jarvis can recreate it with quota-free local embeddings.`);
      }
      const remoteDocuments = (await client.getDocs(indexName)).filter(validDocument).map(withoutEmbedding);
      const remoteById = new Map(remoteDocuments.map((doc) => [doc.id, JSON.stringify(doc)]));
      documents = mergeDocuments(remoteDocuments, localDocuments);
      const pending = documents.filter((doc) => remoteById.get(doc.id) !== JSON.stringify(doc));
      if (pending.length) {
        stage = "uploading locally embedded memories";
        await client.addDocs(indexName, pending.map(withEmbedding), { upsert: true });
      }
    } else {
      stage = "creating the locally embedded index";
      await client.createIndex(indexName, documents.map(withEmbedding), { modelId: "custom" });
    }

    stage = "loading the synchronized index";
    await client.loadIndex(indexName);
    await writeLocalDocuments(documents);
    return { client, documents, memoryOnline: true, memoryError: undefined };
  } catch (error) {
    return {
      client,
      documents: localDocuments,
      memoryOnline: false,
      memoryError: `Moss sync unavailable while ${stage}: ${errorMessage(error)}`,
    };
  }
}

async function createLocalMossIndex(client: MossClient | null, documents: StoredDocument[]) {
  if (!client) return { localIndex: null, localMossReady: false, localMossError: "Moss credentials are required for its local index engine." };
  try {
    const localIndex = await client.session("jarvis-local-second-brain", "custom");
    await localIndex.addDocs(documents.map(withEmbedding), { upsert: true });
    await localIndex.saveToDisk(localMossFile());
    return { localIndex, localMossReady: true, localMossError: undefined };
  } catch (error) {
    return { localIndex: null, localMossReady: false, localMossError: `Local Moss index unavailable: ${errorMessage(error)}` };
  }
}

export async function createJarvisSession() {
  const id = crypto.randomUUID();
  const longTermIndex = configValue("mossLongTermIndex", "MOSS_LONG_TERM_INDEX", "jarvis-second-brain");
  const localDocuments = await readLocalDocuments();
  await writeLocalDocuments(localDocuments);
  const moss = await connectAndSyncMoss(longTermIndex, localDocuments);
  const localMoss = await createLocalMossIndex(moss.client, moss.documents);

  const session: JarvisSession = {
    id,
    startedAt: new Date().toISOString(),
    client: moss.client,
    localIndex: localMoss.localIndex,
    working: [],
    documents: moss.documents,
    longTermIndex,
    memoryOnline: moss.memoryOnline,
    localMossReady: localMoss.localMossReady,
    memoryError: moss.memoryError || localMoss.localMossError,
  };
  sessions.set(id, session);

  return {
    id,
    workingIndex: "in-memory-recent-turns",
    longTermIndex,
    workingDocs: 0,
    memoryDocs: session.documents.length,
    memoryOnline: session.memoryOnline,
    localMossReady: session.localMossReady,
    memoryError: session.memoryError,
    memoryFile: memoryFile(),
    localMossFile: localMossFile(),
  };
}

export function getJarvisSession(id: string) {
  const session = sessions.get(id);
  if (!session) throw new Error("Jarvis session expired. Reinitialize the core.");
  return session;
}

export async function addWorkingTurn(sessionId: string, role: "user" | "assistant", text: string) {
  const session = getJarvisSession(sessionId);
  const createdAtValue = new Date().toISOString();
  session.working.push({
    id: `turn-${createdAtValue}-${crypto.randomUUID()}`,
    text: `${role === "user" ? "User" : "Jarvis"}: ${text}`,
    metadata: { type: "conversation-turn", role, createdAt: createdAtValue },
  });
  session.working = session.working.slice(-40);
}

export async function queryBoth(sessionId: string, query: string, topK = 5) {
  const session = getJarvisSession(sessionId);
  const started = performance.now();
  const working = searchLocal(session.working, query, topK);
  let longTerm: Array<StoredDocument & { score?: number }> = searchLocal(session.documents, query, topK);

  if (session.localIndex) {
    try {
      const localResult = await session.localIndex.query(query, { topK, embedding: localEmbedding(query) });
      longTerm = localResult.docs;
    } catch (error) {
      session.localMossReady = false;
      session.memoryError = `Local Moss query unavailable: ${errorMessage(error)}`;
    }
  }

  if (session.client && session.memoryOnline) {
    try {
      const mossResult = await session.client.query(session.longTermIndex, query, { topK, embedding: localEmbedding(query) });
      longTerm = mergeDocuments(
        mossResult.docs.filter(validDocument),
        longTerm,
      ).slice(0, topK);
    } catch (error) {
      session.memoryOnline = false;
      session.memoryError = `Moss query unavailable: ${errorMessage(error)}`;
    }
  }

  return {
    working: toMemory(working, "working"),
    longTerm: toMemory(longTerm, "long-term"),
    elapsedMs: Math.round((performance.now() - started) * 10) / 10,
    memoryOnline: session.memoryOnline,
    localMossReady: session.localMossReady,
    memoryError: session.memoryError,
  };
}

export async function persistTurn(
  sessionId: string,
  userText: string,
  response: string,
  facts: string[],
  tasks: JarvisTask[],
) {
  const session = getJarvisSession(sessionId);
  const now = new Date().toISOString();
  const docs: StoredDocument[] = [
    {
      id: `memory-${crypto.randomUUID()}`,
      text: `Conversation ${now}. User: ${userText}\nJarvis: ${response}`,
      metadata: { type: "conversation-summary", createdAt: now },
    },
    ...facts.filter(Boolean).map((fact) => ({
      id: `fact-${crypto.randomUUID()}`,
      text: fact,
      metadata: { type: "fact", createdAt: now },
    })),
    ...tasks.map((task) => ({
      id: `task-${crypto.randomUUID()}`,
      text: task.title,
      metadata: {
        type: "task",
        status: "open",
        due: task.due || "unscheduled",
        recurrence: task.recurrence || "none",
        priority: task.priority || "normal",
        createdAt: now,
      },
    })),
  ];

  const latestLocal = await readLocalDocuments();
  session.documents = mergeDocuments(latestLocal, session.documents, docs);
  await writeLocalDocuments(session.documents);

  if (session.localIndex) {
    try {
      await session.localIndex.addDocs(docs.map(withEmbedding), { upsert: true });
      await session.localIndex.saveToDisk(localMossFile());
      session.localMossReady = true;
    } catch (error) {
      session.localMossReady = false;
      session.memoryError = `Local Moss write unavailable: ${errorMessage(error)}`;
    }
  }

  if (session.client && session.memoryOnline) {
    try {
      const mutation = await session.client.addDocs(session.longTermIndex, docs.map(withEmbedding), { upsert: true });
      await session.client.loadIndex(session.longTermIndex);
      return {
        stored: session.documents.length,
        synced: true,
        localMossReady: session.localMossReady,
        mossDocCount: mutation.docCount,
        tasksAdded: tasks.length,
      };
    } catch (error) {
      session.memoryOnline = false;
      session.memoryError = `Moss write unavailable: ${errorMessage(error)}`;
    }
  }

  return {
    stored: session.documents.length,
    synced: false,
    localMossReady: session.localMossReady,
    tasksAdded: tasks.length,
    error: session.memoryError || "Moss is offline; this memory is stored locally and will sync later.",
  };
}

export async function openTasks(sessionId: string) {
  const session = getJarvisSession(sessionId);
  return session.documents
    .filter((doc) => doc.metadata?.type === "task" && doc.metadata?.status === "open")
    .map((doc) => ({
      id: doc.id,
      title: doc.text,
      due: String(doc.metadata?.due || "unscheduled"),
      recurrence: String(doc.metadata?.recurrence || "none"),
      priority: String(doc.metadata?.priority || "normal"),
    }));
}

async function storeBrainDocuments(session: JarvisSession, docs: StoredDocument[]) {
  if (!docs.length) return { added: 0, total: session.documents.length, synced: session.memoryOnline };
  const latestLocal = await readLocalDocuments();
  session.documents = mergeDocuments(latestLocal, session.documents, docs);
  await writeLocalDocuments(session.documents);

  if (session.localIndex) {
    try {
      await session.localIndex.addDocs(docs.map(withEmbedding), { upsert: true });
      await session.localIndex.saveToDisk(localMossFile());
      session.localMossReady = true;
    } catch (error) {
      session.localMossReady = false;
      session.memoryError = `Local Moss write unavailable: ${errorMessage(error)}`;
    }
  }

  if (session.client && session.memoryOnline) {
    try {
      await session.client.addDocs(session.longTermIndex, docs.map(withEmbedding), { upsert: true });
      await session.client.loadIndex(session.longTermIndex);
    } catch (error) {
      session.memoryOnline = false;
      session.memoryError = `Moss sync unavailable: ${errorMessage(error)}`;
    }
  }

  return {
    added: docs.length,
    total: session.documents.filter((doc) => doc.metadata?.type !== "system").length,
    synced: session.memoryOnline,
    localMossReady: session.localMossReady,
    memoryError: session.memoryError,
  };
}

export async function rememberInBrain(sessionId: string, text: string, options?: { title?: string; tags?: string[] }) {
  const session = getJarvisSession(sessionId);
  const now = new Date().toISOString();
  const title = options?.title?.trim() || text.trim().split(/[.!?\n]/)[0].slice(0, 80) || "Remembered memory";
  const doc: StoredDocument = {
    id: `remembered-${crypto.randomUUID()}`,
    text: `[remembered/${now.slice(0, 10)} — ${title}]\n${text.trim()}`.slice(0, 4000),
    metadata: {
      type: "remembered",
      source: `remembered/${now.slice(0, 10)}`,
      title,
      tags: options?.tags || [],
      createdAt: now,
      importedAt: now,
    },
  };
  return { memory: asBrainMemory(doc), ...(await storeBrainDocuments(session, [doc])) };
}

export async function ingestBrainChunks(sessionId: string, chunks: StoredDocument[]) {
  const session = getJarvisSession(sessionId);
  const safe = chunks.filter(validDocument).map(withoutEmbedding);
  return storeBrainDocuments(session, safe);
}

export async function searchBrain(
  sessionId: string,
  query: string,
  options?: { limit?: number; recent?: boolean; type?: string; source?: string },
) {
  const session = getJarvisSession(sessionId);
  const limit = Math.min(100, Math.max(1, options?.limit || 30));
  const needle = query.trim();
  let docs: Array<StoredDocument & { score?: number }>;

  if (needle) {
    const queryVector = localEmbedding(needle);
    docs = session.documents
      .filter((doc) => doc.metadata?.type !== "system")
      .map((doc) => ({ ...doc, score: cosineSimilarity(queryVector, localEmbedding(doc.text)) }));
    if (session.localIndex) {
      try {
        const result = await session.localIndex.query(needle, { topK: Math.min(100, limit * 3), embedding: queryVector });
        const merged = new Map(docs.map((doc) => [doc.id, doc]));
        for (const hit of result.docs.filter(validDocument)) merged.set(hit.id, { ...hit, score: hit.score });
        docs = [...merged.values()];
      } catch (error) {
        session.localMossReady = false;
        session.memoryError = `Local Moss query unavailable: ${errorMessage(error)}`;
      }
    }
  } else {
    docs = session.documents.filter((doc) => doc.metadata?.type !== "system");
  }

  if (options?.type && options.type !== "all") docs = docs.filter((doc) => doc.metadata?.type === options.type);
  if (options?.source) docs = docs.filter((doc) => documentSource(doc) === options.source);
  docs.sort((a, b) => {
    const aScore = needle ? (a.score || 0) * (options?.recent ? recencyFactor(a) : 1) : createdAt(a);
    const bScore = needle ? (b.score || 0) * (options?.recent ? recencyFactor(b) : 1) : createdAt(b);
    return bScore - aScore;
  });
  return {
    memories: docs.slice(0, limit).map(asBrainMemory),
    total: docs.length,
    elapsedMs: 0,
    memoryOnline: session.memoryOnline,
    localMossReady: session.localMossReady,
    memoryError: session.memoryError,
  };
}

export async function relatedBrainMemories(sessionId: string, memoryId: string, limit = 8) {
  const session = getJarvisSession(sessionId);
  const selected = session.documents.find((doc) => doc.id === memoryId);
  if (!selected) throw new Error("That memory is no longer in the second brain.");
  const source = documentSource(selected);
  const vector = localEmbedding(selected.text);
  const seen = new Set<string>([source]);
  const related = session.documents
    .filter((doc) => doc.metadata?.type !== "system" && doc.id !== selected.id)
    .map((doc) => ({ ...doc, score: cosineSimilarity(vector, localEmbedding(doc.text)) }))
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .filter((doc) => {
      const docSource = documentSource(doc);
      if (seen.has(docSource)) return false;
      seen.add(docSource);
      return true;
    })
    .slice(0, Math.min(24, Math.max(1, limit)));
  return { selected: asBrainMemory(selected), related: related.map(asBrainMemory) };
}

export async function brainStats(sessionId: string) {
  const session = getJarvisSession(sessionId);
  const documents = session.documents.filter((doc) => doc.metadata?.type !== "system");
  const sourceCounts = new Map<string, number>();
  const typeCounts = new Map<string, number>();
  for (const doc of documents) {
    sourceCounts.set(documentSource(doc), (sourceCounts.get(documentSource(doc)) || 0) + 1);
    const type = typeof doc.metadata?.type === "string" ? doc.metadata.type : "memory";
    typeCounts.set(type, (typeCounts.get(type) || 0) + 1);
  }
  return {
    documents: documents.length,
    sources: sourceCounts.size,
    connections: (await buildBrainGraph(sessionId)).edges.length,
    remembered: typeCounts.get("remembered") || 0,
    conversations: (typeCounts.get("conversation-summary") || 0) + (typeCounts.get("conversation-archive") || 0),
    tasks: typeCounts.get("task") || 0,
    types: Object.fromEntries([...typeCounts.entries()].sort((a, b) => b[1] - a[1])),
    storagePath: memoryFile(),
    cloud: session.memoryOnline,
    localMoss: session.localMossReady,
    memoryError: session.memoryError,
  };
}

export async function buildBrainGraph(sessionId: string): Promise<BrainGraph> {
  const session = getJarvisSession(sessionId);
  const grouped = new Map<string, StoredDocument[]>();
  for (const doc of session.documents) {
    if (doc.metadata?.type === "system") continue;
    const source = documentSource(doc);
    grouped.set(source, [...(grouped.get(source) || []), doc]);
  }
  const sources = [...grouped.entries()].map(([id, docs]) => ({
    id,
    docs,
    title: documentTitle(docs[0]),
    type: typeof docs[0].metadata?.type === "string" ? docs[0].metadata.type : "memory",
    vector: localEmbedding(docs[0].text.slice(0, 1800)),
  }));
  const edges = new Map<string, { a: string; b: string; weight: number }>();
  for (let left = 0; left < sources.length; left += 1) {
    const neighbors = [] as Array<{ index: number; weight: number }>;
    for (let right = 0; right < sources.length; right += 1) {
      if (left === right) continue;
      neighbors.push({ index: right, weight: cosineSimilarity(sources[left].vector, sources[right].vector) });
    }
    for (const neighbor of neighbors.sort((a, b) => b.weight - a.weight).slice(0, 6)) {
      if (neighbor.weight < 0.08) continue;
      const pair = [sources[left].id, sources[neighbor.index].id].sort();
      const key = pair.join("\u0000");
      const existing = edges.get(key);
      if (!existing || neighbor.weight > existing.weight) {
        edges.set(key, { a: pair[0], b: pair[1], weight: Math.round(neighbor.weight * 1000) / 1000 });
      }
    }
  }
  const degrees = new Map<string, number>();
  for (const edge of edges.values()) {
    degrees.set(edge.a, (degrees.get(edge.a) || 0) + 1);
    degrees.set(edge.b, (degrees.get(edge.b) || 0) + 1);
  }
  return {
    nodes: sources.map((source) => ({
      id: source.id,
      title: source.title,
      type: source.type,
      chunks: source.docs.length,
      degree: degrees.get(source.id) || 0,
    })),
    edges: [...edges.values()],
  };
}

export async function deleteBrainMemory(sessionId: string, memoryId: string) {
  const session = getJarvisSession(sessionId);
  const exists = session.documents.some((doc) => doc.id === memoryId && doc.metadata?.type !== "system");
  if (!exists) throw new Error("That memory was already removed.");
  session.documents = session.documents.filter((doc) => doc.id !== memoryId);
  await writeLocalDocuments(session.documents);
  if (session.localIndex) {
    try {
      await session.localIndex.deleteDocs([memoryId]);
      await session.localIndex.saveToDisk(localMossFile());
    } catch (error) {
      session.memoryError = `Local Moss delete unavailable: ${errorMessage(error)}`;
    }
  }
  if (session.client && session.memoryOnline) {
    try {
      await session.client.deleteDocs(session.longTermIndex, [memoryId]);
      await session.client.loadIndex(session.longTermIndex);
    } catch (error) {
      session.memoryOnline = false;
      session.memoryError = `Moss delete sync unavailable: ${errorMessage(error)}`;
    }
  }
  return { deleted: memoryId, total: session.documents.filter((doc) => doc.metadata?.type !== "system").length };
}
