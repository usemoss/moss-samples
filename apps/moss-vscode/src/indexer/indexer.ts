import type { DocumentInfo } from "@moss-dev/moss";
import * as vscode from "vscode";
import type { LocalMossSession } from "../moss/client";
import { chunkFile } from "./chunker";
import { isExcludedFromIndex } from "./excludes";
import { readFileForIndex, scanWorkspaceFiles, toWorkspaceRelative } from "./scanner";

const BATCH_SIZE = 64;
const YIELD_EVERY_FILES = 25;

export type IndexStatus =
  | { state: "unindexed" }
  | { state: "indexing"; processed: number; total: number }
  | { state: "ready"; files: number; chunks: number }
  | { state: "error"; message: string };

export type StatusListener = (status: IndexStatus) => void;

export class CodebaseIndexer {
  private session: LocalMossSession | undefined;
  private status: IndexStatus = { state: "unindexed" };
  private listeners = new Set<StatusListener>();
  private pathChunkCounts = new Map<string, number>();
  private watchers: vscode.Disposable[] = [];
  private indexing = false;
  private watchingEnabled = false;
  /** True once rebuild() has begun destroying the previous index. */
  private discardedPreviousIndex = false;
  /** Bumped by each rebuild so watcher work started earlier can bail out. */
  private generation = 0;
  /** Watcher operations already past their `indexing` guard. */
  private watcherOps = new Set<Promise<void>>();
  private onPersist: (() => void) | undefined;

  setPersistHandler(handler: (() => void) | undefined): void {
    this.onPersist = handler;
  }

  onStatus(listener: StatusListener): vscode.Disposable {
    this.listeners.add(listener);
    listener(this.status);
    return new vscode.Disposable(() => this.listeners.delete(listener));
  }

  getStatus(): IndexStatus {
    return this.status;
  }

  getPathChunkCounts(): Record<string, number> {
    return Object.fromEntries(this.pathChunkCounts.entries());
  }

  /**
   * Whether the last rebuild got far enough to destroy the previous index.
   *
   * Lets the caller decide if a non-ready outcome must also invalidate the
   * persisted cache, or whether the old documents are still intact.
   */
  hasDiscardedPreviousIndex(): boolean {
    return this.discardedPreviousIndex;
  }

  isIndexed(): boolean {
    return this.status.state === "ready" && this.pathChunkCounts.size > 0;
  }

  canSearch(): boolean {
    return this.isIndexed() && !this.indexing;
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

  attachSession(session: LocalMossSession): void {
    this.session = session;
  }

  restoreFromMeta(pathChunkCounts: Record<string, number>): void {
    this.pathChunkCounts.clear();
    let chunks = 0;
    for (const [rel, count] of Object.entries(pathChunkCounts)) {
      if (typeof count === "number" && count > 0) {
        this.pathChunkCounts.set(rel, count);
        chunks += count;
      }
    }
    if (this.pathChunkCounts.size === 0) {
      this.watchingEnabled = false;
      this.setStatus({ state: "unindexed" });
      return;
    }
    this.watchingEnabled = true;
    this.setStatus({
      state: "ready",
      files: this.pathChunkCounts.size,
      chunks,
    });
  }

  async rebuild(token?: vscode.CancellationToken): Promise<void> {
    if (!this.session) {
      throw new Error("Moss session not ready");
    }
    if (this.indexing) {
      return;
    }
    // `indexing` is already set, so no *new* watcher work can start.
    this.indexing = true;
    this.discardedPreviousIndex = false;

    try {
      // Drain before bumping the generation, not after. A watcher that has
      // already called addDocs() must be allowed to record those chunks in
      // pathChunkCounts — marking it stale first would make it return silently,
      // leaving its writes out of the staleIds we compute below and stranding
      // them in the index. Once everything in flight has settled, the bump
      // covers anything that slips through afterwards.
      await this.drainWatcherOps();
      this.generation += 1;

      const files = await scanWorkspaceFiles(token);
      this.setStatus({ state: "indexing", processed: 0, total: files.length });

      // Clear previous local docs for known paths when rebuilding
      const staleIds: string[] = [];
      for (const [rel, count] of this.pathChunkCounts) {
        for (let i = 0; i < count; i++) {
          staleIds.push(`${rel}#chunk-${i}`);
        }
      }
      if (staleIds.length) {
        await this.deleteInBatches(staleIds);
      }
      // Only once the stale delete has fully succeeded. If it throws partway,
      // some old documents survive — and the persisted cache is the only record
      // of their ids, so it must be kept for a later rebuild to retry the
      // cleanup. Clearing it there would strand those documents in the index
      // permanently, still answering searches for deleted or renamed files.
      //
      // From here on the previous index really is gone, so any exit that is not
      // "ready" must invalidate the cache. A failure before this point (scan,
      // session setup, a partial delete) leaves the old documents intact and
      // the cache with them.
      this.discardedPreviousIndex = true;
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

      let cancelled = false;
      for (const uri of files) {
        if (token?.isCancellationRequested) {
          cancelled = true;
          break;
        }
        const file = await readFileForIndex(uri);
        processed += 1;
        if (processed % YIELD_EVERY_FILES === 0) {
          await new Promise<void>((resolve) => setImmediate(resolve));
        }
        this.setStatus({
          state: "indexing",
          processed,
          total: files.length,
        });
        if (!file) {
          continue;
        }
        const chunks = chunkFile(file.relativePath, file.content);
        if (!chunks.length) {
          continue;
        }
        this.pathChunkCounts.set(file.relativePath, chunks.length);
        totalChunks += chunks.length;
        pending.push(...chunks);
        if (pending.length >= BATCH_SIZE) {
          await flush();
        }
      }

      // The loop only tests the token *before* each file, so cancellation
      // arriving during the last readFileForIndex() — or during the final
      // flush() below — would otherwise fall through and publish "ready" over
      // an incomplete scan.
      cancelled = cancelled || (token?.isCancellationRequested ?? false);
      if (!cancelled) {
        await flush();
        cancelled = token?.isCancellationRequested ?? false;
      }

      if (cancelled) {
        const pendingByPath = new Map<string, number>();
        for (const doc of pending) {
          const filePath = doc.metadata?.filePath;
          if (typeof filePath === "string") {
            pendingByPath.set(filePath, (pendingByPath.get(filePath) ?? 0) + 1);
          }
        }
        for (const [rel, unflushed] of pendingByPath) {
          const current = this.pathChunkCounts.get(rel) ?? 0;
          const remaining = current - unflushed;
          if (remaining <= 0) {
            this.pathChunkCounts.delete(rel);
          } else {
            this.pathChunkCounts.set(rel, remaining);
          }
        }
        pending.length = 0;

        // A cancelled scan only ever reached a prefix of the workspace, and the
        // watchers fire on *changes* — so files never scanned would stay absent
        // and searches would silently return partial results. The pre-index
        // snapshot is already gone (stale docs were deleted above), so discard
        // the partial index rather than presenting it as ready. The user re-runs
        // indexing from the "unindexed" state.
        await this.discardPartialIndex();
        this.watchingEnabled = false;
        this.setStatus({ state: "unindexed" });
        return;
      }

      if (this.pathChunkCounts.size === 0) {
        this.setStatus({
          state: "error",
          message: "No indexable files found in this workspace.",
        });
        return;
      }
      this.watchingEnabled = true;
      this.discardedPreviousIndex = false;
      this.setStatus({
        state: "ready",
        files: this.pathChunkCounts.size,
        chunks: totalChunks,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      // If the throw landed after the stale delete, documents from this run may
      // already be in the index while the persisted cache — soon to be dropped
      // by the caller — is the only record of their ids. Remove them now so
      // nothing is stranded answering searches for files that no longer exist.
      if (this.discardedPreviousIndex) {
        await this.discardPartialIndex();
      }
      this.watchingEnabled = false;
      this.setStatus({ state: "error", message });
      throw err;
    } finally {
      this.indexing = false;
    }
  }

  markReadyFromSession(fileCount: number, chunkCount: number): void {
    if (fileCount > 0 && chunkCount > 0) {
      this.watchingEnabled = true;
      this.setStatus({ state: "ready", files: fileCount, chunks: chunkCount });
    } else {
      this.setStatus({ state: "unindexed" });
    }
  }

  /**
   * Register a watcher operation so a rebuild can wait for it to finish.
   *
   * The `indexing` guard only stops watcher work from *starting*; an operation
   * already awaiting a file read would otherwise run its writes concurrently
   * with a rebuild's cleanup.
   */
  private trackWatcherOp(run: () => Promise<void>): Promise<void> {
    const op = run();
    this.watcherOps.add(op);
    void op.catch(() => undefined).finally(() => this.watcherOps.delete(op));
    return op;
  }

  /** Let watcher work that predates this rebuild settle before mutating. */
  private async drainWatcherOps(): Promise<void> {
    while (this.watcherOps.size) {
      const inflight = Array.from(this.watcherOps);
      await Promise.allSettled(inflight);
      for (const op of inflight) {
        this.watcherOps.delete(op);
      }
    }
  }

  async upsertFile(uri: vscode.Uri): Promise<void> {
    if (!this.session || !this.watchingEnabled || this.indexing) {
      return;
    }
    return this.trackWatcherOp(() => this.applyUpsert(uri, this.session!));
  }

  private async applyUpsert(uri: vscode.Uri, session: LocalMossSession): Promise<void> {
    // A rebuild starting mid-operation invalidates everything below: its
    // pathChunkCounts are being rewritten and its documents deleted, so writing
    // here would resurrect ids the rebuild has already accounted for.
    const generation = this.generation;
    const stale = () => generation !== this.generation;

    const relativePath = toWorkspaceRelative(uri);
    if (isExcludedFromIndex(relativePath)) {
      return;
    }
    const file = await readFileForIndex(uri);
    if (stale()) {
      return;
    }
    if (!file) {
      await this.applyRemove(uri, session);
      return;
    }

    const previous = this.pathChunkCounts.get(file.relativePath) ?? 0;
    const chunks = chunkFile(file.relativePath, file.content);
    const next = chunks.length;

    if (previous > next) {
      const toDelete: string[] = [];
      for (let i = next; i < previous; i++) {
        toDelete.push(`${file.relativePath}#chunk-${i}`);
      }
      if (toDelete.length) {
        await session.deleteDocs(toDelete);
        if (stale()) {
          return;
        }
      }
    }

    if (chunks.length) {
      await session.addDocs(chunks, { upsert: true });
      // Re-checked after the write: if a rebuild took over we must not record
      // these ids, and it will delete them as part of its own cleanup.
      if (stale()) {
        return;
      }
      this.pathChunkCounts.set(file.relativePath, next);
    } else {
      if (stale()) {
        return;
      }
      this.pathChunkCounts.delete(file.relativePath);
    }

    this.refreshReadyStatus();
    this.requestPersist();
  }

  async removeFile(uri: vscode.Uri): Promise<void> {
    if (!this.session || !this.watchingEnabled || this.indexing) {
      return;
    }
    return this.trackWatcherOp(() => this.applyRemove(uri, this.session!));
  }

  private async applyRemove(uri: vscode.Uri, session: LocalMossSession): Promise<void> {
    const generation = this.generation;
    const stale = () => generation !== this.generation;

    const relativePath = toWorkspaceRelative(uri);
    const count = this.pathChunkCounts.get(relativePath) ?? 0;
    if (!count) {
      // Best-effort: try deleting a reasonable number of chunks
      const guessIds = Array.from({ length: 64 }, (_, i) => `${relativePath}#chunk-${i}`);
      await session.deleteDocs(guessIds).catch(() => undefined);
      return;
    }
    const ids = Array.from({ length: count }, (_, i) => `${relativePath}#chunk-${i}`);
    await session.deleteDocs(ids);
    if (stale()) {
      return;
    }
    this.pathChunkCounts.delete(relativePath);
    this.refreshReadyStatus();
    this.requestPersist();
  }

  startWatching(disposables: vscode.Disposable[]): void {
    this.stopWatching();

    const save = vscode.workspace.onDidSaveTextDocument(async (doc) => {
      if (doc.uri.scheme !== "file") {
        return;
      }
      try {
        await this.upsertFile(doc.uri);
      } catch (err) {
        console.error("Moss incremental index failed", err);
      }
    });

    const create = vscode.workspace.onDidCreateFiles(async (e) => {
      for (const uri of e.files) {
        try {
          await this.upsertFile(uri);
        } catch (err) {
          console.error("Moss create index failed", err);
        }
      }
    });

    const del = vscode.workspace.onDidDeleteFiles(async (e) => {
      for (const uri of e.files) {
        try {
          await this.removeFile(uri);
        } catch (err) {
          console.error("Moss delete index failed", err);
        }
      }
    });

    const rename = vscode.workspace.onDidRenameFiles(async (e) => {
      for (const { oldUri, newUri } of e.files) {
        try {
          await this.removeFile(oldUri);
          await this.upsertFile(newUri);
        } catch (err) {
          console.error("Moss rename index failed", err);
        }
      }
    });

    this.watchers = [save, create, del, rename];
    disposables.push(...this.watchers);
  }

  stopWatching(): void {
    for (const d of this.watchers) {
      d.dispose();
    }
    this.watchers = [];
  }

  dispose(): void {
    this.stopWatching();
    this.listeners.clear();
    this.pathChunkCounts.clear();
    this.session = undefined;
    this.watchingEnabled = false;
  }

  private refreshReadyStatus(): void {
    let chunks = 0;
    for (const count of this.pathChunkCounts.values()) {
      chunks += count;
    }
    this.setStatus({
      state: "ready",
      files: this.pathChunkCounts.size,
      chunks,
    });
  }

  /**
   * Remove every document this rebuild added and forget their ids.
   *
   * If the delete fails, `pathChunkCounts` is kept so a retry in this session
   * can still remove what was missed, but `discardedPreviousIndex` stays true
   * so the caller still drops the persisted cache. That cache describes the
   * previous documents, which this rebuild already deleted — keeping it would
   * let `restoreFromMeta()` report a ready index for documents that no longer
   * exist on the next launch.
   */
  private async discardPartialIndex(): Promise<void> {
    const partialIds: string[] = [];
    for (const [rel, count] of this.pathChunkCounts) {
      for (let i = 0; i < count; i++) {
        partialIds.push(`${rel}#chunk-${i}`);
      }
    }
    if (partialIds.length) {
      try {
        await this.deleteInBatches(partialIds);
      } catch {
        // Deliberately leave discardedPreviousIndex true so the caller still
        // drops the persisted cache. That cache describes the *previous*
        // documents, which this rebuild already deleted — keeping it would let
        // restoreFromMeta() come back on the next launch reporting a ready
        // index for documents that no longer exist, which is worse than the
        // leftovers. pathChunkCounts is kept so a retry in this session can
        // still delete what we failed to remove here.
        return;
      }
    }
    this.pathChunkCounts.clear();
  }

  private async deleteInBatches(ids: string[]): Promise<void> {
    if (!this.session) {
      return;
    }
    for (let i = 0; i < ids.length; i += BATCH_SIZE) {
      const slice = ids.slice(i, i + BATCH_SIZE);
      await this.session.deleteDocs(slice);
    }
  }
}
