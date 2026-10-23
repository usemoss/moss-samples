import { spawn, spawnSync, type ChildProcess } from "child_process";
import * as fs from "fs";
import * as path from "path";
import type {
  DocumentInfo,
  GetDocumentsOptions,
  MutationOptions,
  PushIndexResult,
  QueryOptions,
  SearchResult,
} from "@moss-dev/moss";
import type { WorkerMethod } from "../worker/mossWorker";

type WorkerResponse =
  | { id: number; ok: true; result: unknown }
  | { id: number; ok: false; error: string };

export type MossModelId = "moss-minilm" | "moss-mediumlm";

export interface MossCredentials {
  projectId: string;
  projectKey: string;
}

/** The subset of `SessionIndex` the plugin uses, proxied over IPC. */
export interface LocalMossSession {
  readonly docCount: number;
  addDocs(docs: DocumentInfo[], options?: MutationOptions): Promise<{ added: number; updated: number }>;
  deleteDocs(docIds: string[]): Promise<number>;
  query(query: string, options?: QueryOptions): Promise<SearchResult>;
  getDocs(options?: GetDocumentsOptions): Promise<DocumentInfo[]>;
  loadIndex(indexName: string): Promise<number>;
  pushIndex(): Promise<PushIndexResult>;
  saveToDisk(cachePath: string): Promise<void>;
  loadFromDisk(cachePath: string): Promise<number>;
}

export type Logger = (message: string) => void;

/**
 * Owns the worker child process that hosts the native Moss runtime.
 *
 * Why a worker: `@moss-dev/moss-core` is a N-API native module. Loading it in
 * Obsidian's renderer would (a) block the UI thread during embedding and
 * (b) turn any native fault into an Obsidian crash. A forked process gives us
 * a crash boundary — the same design as `apps/moss-vscode`.
 */
export class MossSessionManager {
  private worker: ChildProcess | undefined;
  private session: WorkerBackedSession | undefined;
  private ready = false;
  private nextId = 1;
  /** Serializes initialize/dispose so bootstrap can't race a manual rebuild or restart. */
  private lifecycle: Promise<unknown> = Promise.resolve();
  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (err: Error) => void }>();

  constructor(
    private readonly pluginDir: string,
    private readonly getNodePath: () => string | undefined,
    private readonly log: Logger = () => undefined,
    /** Invoked when the worker dies unexpectedly (not on `dispose`). */
    private readonly onCrash: (detail: string) => void = () => undefined,
  ) {}

  /** What the live session was opened with, so callers can detect drift. */
  private initParams: { projectId: string; projectKey: string; name: string; modelId: MossModelId } | undefined;

  matchesInit(credentials: MossCredentials, name: string, modelId: MossModelId): boolean {
    const p = this.initParams;
    return (
      !!p &&
      p.projectId === credentials.projectId &&
      p.projectKey === credentials.projectKey &&
      p.name === name &&
      p.modelId === modelId
    );
  }

  get isReady(): boolean {
    return this.ready && !!this.session;
  }

  getSession(): LocalMossSession | undefined {
    return this.session;
  }

  initialize(credentials: MossCredentials, name: string, modelId: MossModelId): Promise<LocalMossSession> {
    const run = this.lifecycle.then(() => this.doInitialize(credentials, name, modelId));
    this.lifecycle = run.catch(() => undefined);
    return run;
  }

  private async doInitialize(
    credentials: MossCredentials,
    name: string,
    modelId: MossModelId,
  ): Promise<LocalMossSession> {
    // A caller may have raced us here and already opened the same session.
    if (this.ready && this.session && this.matchesInit(credentials, name, modelId)) {
      return this.session;
    }
    this.ready = false;
    this.session = undefined;
    this.initParams = undefined;
    this.ensureWorker();
    const result = await this.call<{ docCount: number }>("initialize", {
      projectId: credentials.projectId,
      projectKey: credentials.projectKey,
      name,
      modelId,
    });
    this.session = new WorkerBackedSession(result.docCount, (method, args) => this.call(method, args));
    this.initParams = { projectId: credentials.projectId, projectKey: credentials.projectKey, name, modelId };
    this.ready = true;
    return this.session;
  }

  /**
   * Stop the worker. Detaches listeners first so the dying process cannot
   * clobber a replacement started right after (restart / re-initialize).
   */
  dispose(): Promise<void> {
    const run = this.lifecycle.then(() => this.doDispose());
    this.lifecycle = run.catch(() => undefined);
    return run;
  }

  private async doDispose(): Promise<void> {
    this.ready = false;
    this.session = undefined;
    this.initParams = undefined;
    const worker = this.worker;
    this.worker = undefined;
    for (const { reject } of this.pending.values()) {
      reject(new Error("Moss worker was disposed"));
    }
    this.pending.clear();
    if (!worker) {
      return;
    }
    worker.removeAllListeners();
    worker.stdout?.removeAllListeners();
    worker.stderr?.removeAllListeners();
    worker.on("error", () => undefined);
    if (worker.connected) {
      // Best effort: let the native session release its resources before SIGTERM.
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, 1500);
        worker.once("message", () => {
          clearTimeout(timer);
          resolve();
        });
        worker.send({ id: 0, method: "close", args: {} }, () => undefined);
      });
    }
    if (!worker.killed) {
      worker.kill();
    }
  }

  private ensureWorker(): void {
    if (this.worker && !this.worker.killed && this.worker.connected) {
      return;
    }

    const workerPath = path.join(this.pluginDir, "mossWorker.js");
    if (!fs.existsSync(workerPath)) {
      throw new Error(`Moss worker not found at ${workerPath}. Run \`npm run build\` in apps/moss-obsidian.`);
    }
    const modulesPath = path.join(this.pluginDir, "node_modules", "@moss-dev", "moss");
    if (!fs.existsSync(modulesPath)) {
      throw new Error(
        `@moss-dev/moss is not installed next to the plugin (${modulesPath}). ` +
          "Run `npm install --omit=dev` in the plugin folder, or use `npm run install-to-vault`.",
      );
    }

    const { execPath, usingElectron } = findNodeBinary(this.getNodePath(), this.log);
    this.log(`Starting Moss worker: ${workerPath}`);
    this.log(`Moss worker execPath: ${execPath}${usingElectron ? " (Obsidian's Electron as Node)" : ""}`);

    // spawn (not fork) so `windowsHide` is honoured: a GUI parent spawning a
    // console-subsystem node.exe would otherwise pop a console window.
    const child = spawn(execPath, [workerPath], {
      cwd: this.pluginDir,
      stdio: ["ignore", "pipe", "pipe", "ipc"],
      windowsHide: true,
      env: {
        ...process.env,
        ELECTRON_RUN_AS_NODE: "1",
        // Never let Electron-specific vars leak into a plain Node child.
        ELECTRON_NO_ATTACH_CONSOLE: "1",
      },
    });
    this.worker = child;

    child.stdout?.on("data", (chunk: Buffer) => {
      this.log(`[worker] ${chunk.toString().trimEnd()}`);
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      this.log(`[worker:stderr] ${chunk.toString().trimEnd()}`);
    });
    child.on("message", (message: WorkerResponse) => {
      const pending = this.pending.get(message.id);
      if (!pending) {
        return;
      }
      this.pending.delete(message.id);
      if (message.ok) {
        pending.resolve(message.result);
      } else {
        pending.reject(new Error(message.error));
      }
    });
    const onGone = (detail: string) => {
      // Ignore events from a process we already replaced or disposed.
      if (this.worker !== child) {
        return;
      }
      this.log(detail);
      this.ready = false;
      this.session = undefined;
      this.initParams = undefined;
      this.worker = undefined;
      for (const { reject } of this.pending.values()) {
        reject(new Error(`${detail}. The native Moss runtime may have crashed.`));
      }
      this.pending.clear();
      this.onCrash(detail);
    };
    child.on("exit", (code, signal) => {
      onGone(`Moss worker exited (code=${code ?? "null"}, signal=${signal ?? "null"})`);
    });
    child.on("error", (err) => {
      onGone(`Moss worker error: ${err.message}`);
    });
  }

  private call<T>(method: WorkerMethod, args: unknown): Promise<T> {
    if (method === "initialize") {
      this.ensureWorker();
    }
    const worker = this.worker;
    if (!worker || !worker.connected) {
      // Never auto-fork for a session call: a fresh process has no session.
      return Promise.reject(new Error("Moss worker is not running. Run “Moss: Restart Moss worker”."));
    }
    const id = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: (value) => resolve(value as T), reject });
      worker.send({ id, method, args }, (err) => {
        if (!err) {
          return;
        }
        this.pending.delete(id);
        reject(err);
      });
    });
  }
}

function findSystemNode(): string | undefined {
  try {
    if (process.platform === "win32") {
      const result = spawnSync("where", ["node"], { encoding: "utf8", shell: true, windowsHide: true });
      return result.stdout?.split(/\r?\n/).map((s) => s.trim()).find(Boolean) || undefined;
    }
    // Obsidian's PATH is often minimal (launched from the Dock/Finder), so
    // `which` may miss a Node installed by nvm/volta/homebrew. Fall through to
    // the well-known locations below.
    const result = spawnSync("which", ["node"], { encoding: "utf8" });
    return result.stdout?.trim() || undefined;
  } catch {
    return undefined;
  }
}

/** Highest-versioned `node` under an nvm/fnm-style versions directory, if any. */
function newestNvmNode(versionsDir: string): string | undefined {
  try {
    const versions = fs
      .readdirSync(versionsDir)
      .filter((v) => /^v?\d+/.test(v))
      .sort((a, b) => {
        const pa = a.replace(/^v/, "").split(".").map(Number);
        const pb = b.replace(/^v/, "").split(".").map(Number);
        for (let i = 0; i < 3; i++) {
          if ((pa[i] ?? 0) !== (pb[i] ?? 0)) return (pb[i] ?? 0) - (pa[i] ?? 0);
        }
        return 0;
      });
    for (const v of versions) {
      for (const candidate of [
        path.join(versionsDir, v, "bin", "node"),
        path.join(versionsDir, v, "installation", "bin", "node"),
      ]) {
        if (fs.existsSync(candidate)) return candidate;
      }
    }
  } catch {
    // directory missing
  }
  return undefined;
}

// `@moss-dev/moss` declares engines.node ">=20.4"; anything older can fail to
// load the SDK, so the probe has to compare minor versions too.
const MIN_NODE = [20, 4] as const;

export function isNodeVersionSupported(version: string): boolean {
  const [major, minor] = version.trim().split(".").map((part) => Number.parseInt(part, 10));
  if (!Number.isFinite(major)) {
    return false;
  }
  if (major !== MIN_NODE[0]) {
    return major > MIN_NODE[0];
  }
  return Number.isFinite(minor) && minor >= MIN_NODE[1];
}

/** True when `filePath` runs and reports a Node the Moss SDK supports. */
function isUsableNode(filePath: string): boolean {
  try {
    if (!fs.existsSync(filePath)) {
      return false;
    }
    const result = spawnSync(filePath, ["-p", "process.versions.node"], {
      encoding: "utf8",
      timeout: 5000,
      windowsHide: true,
      env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" },
    });
    return isNodeVersionSupported(result.stdout ?? "");
  } catch {
    return false;
  }
}

/**
 * Pick a Node binary for the worker. A standalone Node 20.4+ (the SDK's
 * declared engine) is preferred — each candidate is probed for its version,
 * so an older distro `node` earlier in PATH is skipped rather than selected.
 * As a last resort we run Obsidian's own Electron binary with
 * `ELECTRON_RUN_AS_NODE=1`, which behaves as plain Node.
 */
export function findNodeBinary(
  fromSetting: string | undefined,
  log: Logger = () => undefined,
): { execPath: string; usingElectron: boolean } {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? "";
  const candidates = [
    fromSetting?.trim(),
    process.env.NODE_BINARY,
    findSystemNode(),
    process.platform === "win32" ? "C:\\Program Files\\nodejs\\node.exe" : undefined,
    "/opt/homebrew/bin/node",
    "/usr/local/bin/node",
    "/usr/bin/node",
    home ? path.join(home, ".volta", "bin", "node") : undefined,
    home ? newestNvmNode(path.join(home, ".nvm", "versions", "node")) : undefined,
    home ? newestNvmNode(path.join(home, ".fnm", "node-versions")) : undefined,
  ].filter(Boolean) as string[];

  for (const candidate of new Set(candidates)) {
    if (isUsableNode(candidate)) {
      return { execPath: candidate, usingElectron: false };
    }
    log(`Skipping ${candidate}: not a Node ${MIN_NODE[0]}.${MIN_NODE[1]}+ binary`);
  }

  log(
    `No standalone Node ${MIN_NODE[0]}.${MIN_NODE[1]}+ binary found; using Obsidian's Electron runtime as Node ` +
      "(set Node path in settings to override)",
  );
  return { execPath: process.execPath, usingElectron: true };
}

class WorkerBackedSession implements LocalMossSession {
  constructor(
    private count: number,
    private readonly call: <T>(method: WorkerMethod, args: unknown) => Promise<T>,
  ) {}

  get docCount(): number {
    return this.count;
  }

  async addDocs(docs: DocumentInfo[], options?: MutationOptions): Promise<{ added: number; updated: number }> {
    const result = await this.call<{ added: number; updated: number; docCount: number }>("addDocs", {
      docs,
      options,
    });
    this.count = result.docCount;
    return { added: result.added, updated: result.updated };
  }

  async deleteDocs(docIds: string[]): Promise<number> {
    const result = await this.call<{ deleted: number; docCount: number }>("deleteDocs", { docIds });
    this.count = result.docCount;
    return result.deleted;
  }

  async query(query: string, options?: QueryOptions): Promise<SearchResult> {
    return this.call<SearchResult>("query", { query, options });
  }

  async getDocs(options?: GetDocumentsOptions): Promise<DocumentInfo[]> {
    const result = await this.call<{ docs: DocumentInfo[]; docCount: number }>("getDocs", { options });
    this.count = result.docCount;
    return result.docs;
  }

  async loadIndex(indexName: string): Promise<number> {
    const result = await this.call<{ loaded: number; docCount: number }>("loadIndex", { indexName });
    this.count = result.docCount;
    return result.loaded;
  }

  async pushIndex(): Promise<PushIndexResult> {
    const result = await this.call<PushIndexResult & { docCount: number }>("pushIndex", {});
    this.count = result.docCount;
    return result;
  }

  async saveToDisk(cachePath: string): Promise<void> {
    const result = await this.call<{ docCount: number }>("saveToDisk", { cachePath });
    this.count = result.docCount;
  }

  async loadFromDisk(cachePath: string): Promise<number> {
    const result = await this.call<{ loaded: number; docCount: number }>("loadFromDisk", { cachePath });
    this.count = result.docCount;
    return result.loaded;
  }
}
