/**
 * Moss worker process.
 *
 * Runs the native Moss runtime (`@moss-dev/moss` → `@moss-dev/moss-core`) in a
 * separate Node process so a native crash cannot take down Obsidian, and so
 * embedding work never blocks the renderer. Talks to the plugin over the
 * `child_process` IPC channel with a tiny request/response protocol.
 *
 * Mirrors `apps/moss-vscode/src/worker/mossWorker.ts`.
 */
import type {
  DocumentInfo,
  GetDocumentsOptions,
  MossClient,
  MutationOptions,
  PushIndexResult,
  QueryOptions,
  SearchResult,
  SessionIndex,
} from "@moss-dev/moss";

export type WorkerMethod =
  | "initialize"
  | "addDocs"
  | "deleteDocs"
  | "query"
  | "getDocs"
  | "loadIndex"
  | "pushIndex"
  | "saveToDisk"
  | "loadFromDisk"
  | "close";

type Request = { id: number; method: WorkerMethod; args: unknown };

let client: MossClient | undefined;
let session: SessionIndex | undefined;

function send(
  id: number,
  payload: { ok: true; result: unknown } | { ok: false; error: string },
): void {
  process.send?.({ id, ...payload });
}

async function getMoss(): Promise<typeof import("@moss-dev/moss")> {
  return import("@moss-dev/moss");
}

async function closeAll(): Promise<void> {
  if (session) {
    await session.close().catch(() => undefined);
    session = undefined;
  }
  if (client) {
    await client.close().catch(() => undefined);
    client = undefined;
  }
}

function requireSession(): SessionIndex {
  if (!session) {
    throw new Error("Moss worker session is not initialized");
  }
  return session;
}

async function handle(method: WorkerMethod, args: unknown): Promise<unknown> {
  if (method === "initialize") {
    const init = args as {
      projectId: string;
      projectKey: string;
      name: string;
      modelId: "moss-minilm" | "moss-mediumlm";
    };
    await closeAll();
    const { MossClient: MossClientCtor } = await getMoss();
    client = new MossClientCtor(init.projectId, init.projectKey);
    session = await client.session(init.name, init.modelId);
    return { docCount: session.docCount };
  }

  if (method === "addDocs") {
    const { docs, options } = args as { docs: DocumentInfo[]; options?: MutationOptions };
    const result = await requireSession().addDocs(docs, options);
    return { ...result, docCount: requireSession().docCount };
  }

  if (method === "deleteDocs") {
    const { docIds } = args as { docIds: string[] };
    const deleted = await requireSession().deleteDocs(docIds);
    return { deleted, docCount: requireSession().docCount };
  }

  if (method === "query") {
    const { query, options } = args as { query: string; options?: QueryOptions };
    const result: SearchResult = await requireSession().query(query, options);
    return result;
  }

  if (method === "getDocs") {
    const { options } = args as { options?: GetDocumentsOptions };
    const docs = await requireSession().getDocs(options);
    return { docs, docCount: requireSession().docCount };
  }

  if (method === "loadIndex") {
    const { indexName } = args as { indexName: string };
    const loaded = await requireSession().loadIndex(indexName);
    return { loaded, docCount: requireSession().docCount };
  }

  if (method === "pushIndex") {
    // The push result's docCount is the count the cloud accepted; the session
    // count is the same set, so either works for the proxy's bookkeeping.
    const result: PushIndexResult = await requireSession().pushIndex();
    return { ...result };
  }

  if (method === "saveToDisk") {
    const { cachePath } = args as { cachePath: string };
    await requireSession().saveToDisk(cachePath);
    return { docCount: requireSession().docCount };
  }

  if (method === "loadFromDisk") {
    const { cachePath } = args as { cachePath: string };
    const loaded = await requireSession().loadFromDisk(cachePath);
    return { loaded, docCount: requireSession().docCount };
  }

  if (method === "close") {
    await closeAll();
    return { closed: true };
  }

  throw new Error(`Unknown Moss worker method: ${String(method)}`);
}

// All requests run strictly in order: `SessionIndex` is mutable shared state,
// and letting a saveToDisk overlap an addDocs (or an initialize close a
// session mid-query) is a data race. Throughput matters less than a
// consistent index.
let queue: Promise<void> = Promise.resolve();

process.on("message", (message: Request) => {
  if (!message || typeof message.id !== "number") {
    return;
  }
  queue = queue.then(async () => {
    try {
      const result = await handle(message.method, message.args);
      send(message.id, { ok: true, result });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      send(message.id, { ok: false, error });
    }
  });
});

// Exit with the parent: when the IPC channel closes, there is nobody to talk to.
process.on("disconnect", () => {
  process.exit(0);
});
