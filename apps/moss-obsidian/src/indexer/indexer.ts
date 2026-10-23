import type { DocumentInfo } from "@moss-dev/moss";
import type { LocalMossSession } from "../moss/client";
import { chunkIdsForPath, chunkNote, type ChunkOptions } from "./chunker";
import { isExcludedFromIndex, isMarkdownPath } from "./excludes";

/**
 * Minimal view of a vault the indexer needs. `main.ts` adapts Obsidian's
 * `Vault` to this; tests use an in-memory fake.
 */
export interface VaultReader {
  /** Vault-relative paths of all markdown notes. */
  listMarkdownPaths(): string[];
  /** Read a note's content, or `undefined` when it no longer exists. */
  read(relativePath: string): Promise<string | undefined>;
  /** Modification time (ms) of a note, or `undefined` when it no longer exists. */
  mtime(relativePath: string): number | undefined;
}

export interface IndexerConfig {
  excludedFolders: string[];
  chunk: ChunkOptions;
}

export type IndexStatus =
  | { state: "unindexed" }
  | { state: "indexing"; processed: number; total: number }
  | { state: "ready"; files: number; chunks: number }
  | { state: "error"; message: string };

export type StatusListener = (status: IndexStatus) => void;

const BATCH_SIZE = 8;
const YIELD_EVERY_FILES = 25;
// UTF-16 code units, not bytes — a cheap guard against pathological notes.
const MAX_NOTE_CHARS = 1024 * 1024;

export class VaultIndexer {
  private session: LocalMossSession | undefined;
  private status: IndexStatus = { state: "unindexed" };
  private listeners = new Set<StatusListener>();
  private pathChunkCounts = new Map<string, number>();
  private pathMtimes = new Map<string, number>();
  private indexing = false;
  private cancelRequested = false;
  private watchingEnabled = false;
  /** Vault events that arrived while a rebuild was running; drained after it. */
  private pendingEventPaths = new Set<string>();
  private onPersist: (() => void) | undefined;

  constructor(
    private readonly vault: VaultReader,
    private readonly getConfig: () => IndexerConfig,
  ) {}

  setPersistHandler(handler: (() => void) | undefined): void {
    this.onPersist = handler;
  }

  onStatus(listener: StatusListener): () => void {
    this.listeners.add(listener);
    listener(this.status);
    return () => this.listeners.delete(listener);
  }

  getStatus(): IndexStatus {
    return this.status;
  }

  getPathChunkCounts(): Record<string, number> {
    return Object.fromEntries(this.pathChunkCounts.entries());
  }

  getPathMtimes(): Record<string, number> {
    return Object.fromEntries(this.pathMtimes.entries());
  }

  isIndexed(): boolean {
    return this.status.state === "ready" && this.pathChunkCounts.size > 0;
  }

  canSearch(): boolean {
    return this.isIndexed() && !this.indexing;
  }

  isIndexing(): boolean {
    return this.indexing;
  }

  attachSession(session: LocalMossSession): void {
    this.session = session;
  }

  /** Drop the session reference, e.g. after a worker crash. The in-memory
   * index died with the worker, so the status must not stay "ready". */
  detachSession(): void {
    this.session = undefined;
    this.watchingEnabled = false;
    this.pendingEventPaths.clear();
    if (this.status.state === "ready" || this.status.state === "indexing") {
      this.setStatus({ state: "error", message: "Moss worker stopped. Run “Moss: Restart Moss worker”." });
    }
  }

  cancel(): void {
    if (this.indexing) {
      this.cancelRequested = true;
    }
  }

  /** Restore bookkeeping after `loadFromDisk` / cloud restore. */
  restoreFromMeta(pathChunkCounts: Record<string, number>, pathMtimes: Record<string, number> = {}): void {
    this.pathChunkCounts.clear();
    this.pathMtimes.clear();
    let chunks = 0;
    for (const [rel, count] of Object.entries(pathChunkCounts)) {
      if (typeof count === "number" && count > 0) {
        this.pathChunkCounts.set(rel, count);
        chunks += count;
        const mtime = pathMtimes[rel];
        if (typeof mtime === "number") {
          this.pathMtimes.set(rel, mtime);
        }
      }
    }
    if (this.pathChunkCounts.size === 0) {
      this.watchingEnabled = false;
      this.setStatus({ state: "unindexed" });
      return;
    }
    this.watchingEnabled = true;
    this.setStatus({ state: "ready", files: this.pathChunkCounts.size, chunks });
  }

  /**
   * Bring a restored index in line with the vault: notes created, edited or
   * deleted while the plugin was not running (sync, git, another device) are
   * re-indexed or dropped. Cheap when nothing changed — one mtime per note.
   */
  async reconcile(): Promise<{ upserted: number; removed: number }> {
    if (!this.session || !this.watchingEnabled || this.indexing) {
      return { upserted: 0, removed: 0 };
    }
    const live = new Set(this.vault.listMarkdownPaths().filter((p) => this.shouldIndex(p)));
    let upserted = 0;
    let removed = 0;
    for (const rel of [...this.pathChunkCounts.keys()]) {
      if (!live.has(rel)) {
        await this.removePath(rel);
        removed += 1;
      }
    }
    for (const rel of live) {
      const known = this.pathChunkCounts.has(rel);
      const recorded = this.pathMtimes.get(rel);
      const current = this.vault.mtime(rel);
      // Any mtime difference counts: git checkouts and sync tools can hand
      // back changed files with OLDER timestamps.
      if (!known || recorded === undefined || (current !== undefined && current !== recorded)) {
        await this.upsertPath(rel);
        upserted += 1;
      }
    }
    return { upserted, removed };
  }

  shouldIndex(relativePath: string): boolean {
    if (!isMarkdownPath(relativePath)) {
      return false;
    }
    return !isExcludedFromIndex(relativePath, this.getConfig().excludedFolders);
  }

  /** Full (re)index of the vault. Safe to call while unindexed or ready. */
  async rebuild(): Promise<void> {
    if (!this.session) {
      throw new Error("Moss session not ready");
    }
    if (this.indexing) {
      return;
    }
    this.indexing = true;
    this.cancelRequested = false;

    try {
      const paths = this.vault.listMarkdownPaths().filter((p) => this.shouldIndex(p));
      this.setStatus({ state: "indexing", processed: 0, total: paths.length });
      this.pathMtimes.clear();

      // Drop chunks of everything we previously indexed (covers deleted and
      // newly excluded notes; addDocs upserts the rest).
      const staleIds: string[] = [];
      for (const [rel, count] of this.pathChunkCounts) {
        staleIds.push(...chunkIdsForPath(rel, count));
      }
      if (staleIds.length) {
        await this.deleteInBatches(staleIds);
      }
      this.pathChunkCounts.clear();

      let processed = 0;
      let totalChunks = 0;
      const pending: DocumentInfo[] = [];

      const flush = async () => {
        if (!pending.length || !this.session) {
          return;
        }
        const batch = pending.splice(0, pending.length);
        await this.session.addDocs(batch, { upsert: true });
      };

      for (const rel of paths) {
        if (this.cancelRequested) {
          break;
        }
        const content = await this.readNote(rel);
        processed += 1;
        if (processed % YIELD_EVERY_FILES === 0) {
          await new Promise<void>((resolve) => setTimeout(resolve, 0));
        }
        this.setStatus({ state: "indexing", processed, total: paths.length });
        if (content === undefined) {
          continue;
        }
        const chunks = chunkNote(rel, content, this.getConfig().chunk);
        if (!chunks.length) {
          continue;
        }
        this.pathChunkCounts.set(rel, chunks.length);
        const mtime = this.vault.mtime(rel);
        if (mtime !== undefined) {
          this.pathMtimes.set(rel, mtime);
        }
        totalChunks += chunks.length;
        pending.push(...chunks);
        if (pending.length >= BATCH_SIZE) {
          await flush();
        }
      }

      await flush();
      if (this.cancelRequested) {
        // A partial index would silently drop the unvisited notes: refuse to
        // call it ready, and don't persist it over a good cache.
        this.watchingEnabled = false;
        this.setStatus({ state: "error", message: "Indexing cancelled — index is incomplete. Run “Rebuild index”." });
        return;
      }
      if (this.pathChunkCounts.size === 0) {
        this.watchingEnabled = false;
        this.setStatus({ state: "error", message: "No indexable notes found in this vault." });
        return;
      }
      this.watchingEnabled = true;
      this.setStatus({ state: "ready", files: this.pathChunkCounts.size, chunks: totalChunks });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      // The session now holds an unknown subset; letting file events keep
      // writing into it (and persisting) would enshrine the partial state.
      this.watchingEnabled = false;
      this.setStatus({ state: "error", message });
      throw err;
    } finally {
      this.indexing = false;
      this.cancelRequested = false;
      await this.drainPendingEvents();
    }
  }

  /** Apply vault events that arrived while a rebuild was in flight. */
  private async drainPendingEvents(): Promise<void> {
    if (!this.pendingEventPaths.size) {
      return;
    }
    const paths = [...this.pendingEventPaths];
    this.pendingEventPaths.clear();
    if (!this.session || !this.watchingEnabled) {
      return;
    }
    for (const rel of paths) {
      try {
        await this.upsertPath(rel);
      } catch (err) {
        // Best effort; the note will be caught by the next event or reconcile.
        void err;
      }
    }
  }

  /** Incremental: (re)index one note after create/modify. */
  async upsertPath(relativePath: string): Promise<void> {
    if (this.indexing) {
      // Don't drop the event: the rebuild scans a snapshot, so a note edited
      // after the scan passed it would otherwise stay stale until re-touched.
      this.pendingEventPaths.add(relativePath);
      return;
    }
    if (!this.session || !this.watchingEnabled) {
      return;
    }
    if (!this.shouldIndex(relativePath)) {
      // Might have been excluded after it was indexed — drop stale chunks.
      if (this.pathChunkCounts.has(relativePath)) {
        await this.removePath(relativePath);
      }
      return;
    }
    const content = await this.readNote(relativePath);
    if (content === undefined) {
      await this.removePath(relativePath);
      return;
    }

    const previous = this.pathChunkCounts.get(relativePath) ?? 0;
    const chunks = chunkNote(relativePath, content, this.getConfig().chunk);
    const next = chunks.length;

    if (previous > next) {
      const toDelete = chunkIdsForPath(relativePath, previous).slice(next);
      await this.session.deleteDocs(toDelete);
    }

    if (chunks.length) {
      await this.session.addDocs(chunks, { upsert: true });
      this.pathChunkCounts.set(relativePath, next);
      const mtime = this.vault.mtime(relativePath);
      if (mtime !== undefined) {
        this.pathMtimes.set(relativePath, mtime);
      }
    } else {
      this.pathChunkCounts.delete(relativePath);
      this.pathMtimes.delete(relativePath);
    }

    this.refreshReadyStatus();
    this.requestPersist();
  }

  /** Incremental: drop a note's chunks after delete. */
  async removePath(relativePath: string): Promise<void> {
    if (this.indexing) {
      // upsertPath handles a missing file by removing its chunks.
      this.pendingEventPaths.add(relativePath);
      return;
    }
    if (!this.session || !this.watchingEnabled) {
      return;
    }
    const count = this.pathChunkCounts.get(relativePath) ?? 0;
    if (!count) {
      return;
    }
    await this.session.deleteDocs(chunkIdsForPath(relativePath, count));
    this.pathChunkCounts.delete(relativePath);
    this.pathMtimes.delete(relativePath);
    this.refreshReadyStatus();
    this.requestPersist();
  }

  /** Incremental: a note moved. Chunk ids embed the path, so drop + re-add. */
  async renamePath(oldPath: string, newPath: string): Promise<void> {
    await this.removePath(oldPath);
    await this.upsertPath(newPath);
  }

  /** Indexed note paths that live under `folderPath`. */
  private indexedPathsUnder(folderPath: string): string[] {
    const prefix = `${folderPath.replace(/\/+$/, "")}/`;
    return [...this.pathChunkCounts.keys()].filter((p) => p.startsWith(prefix));
  }

  /**
   * A folder moved. Obsidian fires one rename event for the folder, not one
   * per note inside it, so every indexed note under the old prefix has to be
   * re-keyed here or its chunk ids keep pointing at paths that no longer exist.
   */
  async renameFolder(oldPath: string, newPath: string): Promise<void> {
    const oldPrefix = `${oldPath.replace(/\/+$/, "")}/`;
    const newPrefix = `${newPath.replace(/\/+$/, "")}/`;
    for (const stale of this.indexedPathsUnder(oldPath)) {
      await this.removePath(stale);
      await this.upsertPath(`${newPrefix}${stale.slice(oldPrefix.length)}`);
    }
  }

  /** A folder was deleted: drop every indexed note that lived under it. */
  async removeFolder(folderPath: string): Promise<void> {
    for (const stale of this.indexedPathsUnder(folderPath)) {
      await this.removePath(stale);
    }
  }

  dispose(): void {
    this.listeners.clear();
    this.pathChunkCounts.clear();
    this.pathMtimes.clear();
    this.session = undefined;
    this.watchingEnabled = false;
  }

  private async readNote(relativePath: string): Promise<string | undefined> {
    const content = await this.vault.read(relativePath);
    if (content === undefined) {
      return undefined;
    }
    if (content.length > MAX_NOTE_CHARS || content.includes("\u0000")) {
      return undefined;
    }
    return content;
  }

  private setStatus(status: IndexStatus): void {
    this.status = status;
    for (const listener of this.listeners) {
      listener(status);
    }
  }

  private requestPersist(): void {
    this.onPersist?.();
  }

  private refreshReadyStatus(): void {
    let chunks = 0;
    for (const count of this.pathChunkCounts.values()) {
      chunks += count;
    }
    if (this.pathChunkCounts.size === 0) {
      this.setStatus({ state: "unindexed" });
      return;
    }
    this.setStatus({ state: "ready", files: this.pathChunkCounts.size, chunks });
  }

  private async deleteInBatches(ids: string[]): Promise<void> {
    if (!this.session) {
      return;
    }
    for (let i = 0; i < ids.length; i += 64) {
      await this.session.deleteDocs(ids.slice(i, i + 64));
    }
  }
}
