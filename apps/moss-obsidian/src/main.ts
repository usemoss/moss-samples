import * as path from "path";
import { FileSystemAdapter, Notice, Plugin, TFile, TFolder, type TAbstractFile } from "obsidian";
import { VaultIndexer, type IndexStatus, type VaultReader } from "./indexer/indexer";
import { isMarkdownPath, parseExcludedFolders } from "./indexer/excludes";
import { MossSessionManager, type LocalMossSession } from "./moss/client";
import { generateVaultId, IndexCache, pathChunkCountsFromDocs, vaultSessionName } from "./moss/persistence";
import { dedupeByNote, mapHit, type SearchHit } from "./search/search";
import { DEFAULT_SETTINGS, MossSettingTab, type MossSearchSettings } from "./settings";
import { MossSearchModal } from "./ui/searchModal";

const PERSIST_DEBOUNCE_MS = 1500;
const CLOUD_PUSH_DEBOUNCE_MS = 30_000;
const FILE_EVENT_DEBOUNCE_MS = 1200;

export default class MossSearchPlugin extends Plugin {
  settings: MossSearchSettings = { ...DEFAULT_SETTINGS };

  private sessionManager!: MossSessionManager;
  private indexer!: VaultIndexer;
  private cache!: IndexCache;
  private statusBar!: HTMLElement;
  private persistTimer: ReturnType<typeof setTimeout> | undefined;
  private cloudPushTimer: ReturnType<typeof setTimeout> | undefined;
  private fileTimers = new Map<string, ReturnType<typeof setTimeout>>();
  /** Per-path chain so rapid edits index in order, never older-over-newer. */
  private fileOps = new Map<string, Promise<void>>();
  private bootstrapped = false;
  private bootstrapping: Promise<void> | undefined;

  // ── lifecycle ────────────────────────────────────────────────────────

  async onload(): Promise<void> {
    await this.loadSettings();

    const pluginDir = this.pluginDir();
    this.cache = new IndexCache(path.join(pluginDir, "cache"));
    this.sessionManager = new MossSessionManager(
      pluginDir,
      () => this.settings.nodePath || undefined,
      (message) => this.log(message),
      () => {
        // Unexpected worker death: stop feeding a dead session and tell the user.
        this.indexer.detachSession();
        this.bootstrapped = false;
        new Notice("Moss worker stopped unexpectedly. Run “Moss: Restart Moss worker”.");
      },
    );

    const reader: VaultReader = {
      listMarkdownPaths: () => this.app.vault.getMarkdownFiles().map((f) => f.path),
      read: async (relativePath) => {
        const file = this.app.vault.getAbstractFileByPath(relativePath);
        if (!(file instanceof TFile)) {
          return undefined;
        }
        return this.app.vault.cachedRead(file);
      },
      mtime: (relativePath) => {
        const file = this.app.vault.getAbstractFileByPath(relativePath);
        return file instanceof TFile ? file.stat.mtime : undefined;
      },
    };
    this.indexer = new VaultIndexer(reader, () => ({
      excludedFolders: parseExcludedFolders(this.settings.excludedFolders),
      chunk: { maxCharsPerChunk: this.settings.maxCharsPerChunk },
    }));
    this.indexer.setPersistHandler(() => this.schedulePersist());

    this.statusBar = this.addStatusBarItem();
    this.statusBar.addClass("moss-status");
    this.statusBar.onClickEvent(() => this.openSearch());
    this.indexer.onStatus((status) => this.renderStatus(status));

    this.addSettingTab(new MossSettingTab(this.app, this));
    this.addRibbonIcon("search", "Moss semantic search", () => this.openSearch());

    this.addCommand({ id: "search", name: "Search vault by meaning", callback: () => this.openSearch() });
    this.addCommand({ id: "create-index", name: "Create index", callback: () => void this.rebuildIndex() });
    this.addCommand({ id: "rebuild-index", name: "Rebuild index", callback: () => void this.rebuildIndex() });
    this.addCommand({ id: "cancel-indexing", name: "Cancel indexing", callback: () => this.indexer.cancel() });
    this.addCommand({ id: "sync-cloud", name: "Sync index to Moss Cloud", callback: () => void this.syncToCloud(true) });
    this.addCommand({ id: "restart-worker", name: "Restart Moss worker", callback: () => void this.restartWorker() });

    // Vault events fire for every existing file during startup; wait for the
    // layout so we only see real user edits.
    this.app.workspace.onLayoutReady(() => {
      this.registerVaultEvents();
      void this.bootstrap();
    });
  }

  async onunload(): Promise<void> {
    if (this.persistTimer) clearTimeout(this.persistTimer);
    if (this.cloudPushTimer) clearTimeout(this.cloudPushTimer);
    for (const t of this.fileTimers.values()) clearTimeout(t);
    this.fileTimers.clear();
    this.indexer.dispose();
    await this.sessionManager.dispose();
  }

  async loadSettings(): Promise<void> {
    const stored = (await this.loadData()) as Partial<MossSearchSettings> | null;
    this.settings = { ...DEFAULT_SETTINGS, ...(stored ?? {}) };
    if (!this.settings.vaultId) {
      // Generated once and stored in data.json: gives this vault a cloud
      // identity that display-name collisions can't break, and that follows
      // the vault when its .obsidian folder is synced across devices.
      this.settings.vaultId = generateVaultId();
      await this.saveSettings();
    }
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  /** Called by the settings tab when project ID/key or model changed. */
  noteSessionSettingsChanged(): void {
    if (this.sessionManager.getSession() && !this.sessionMatchesSettings()) {
      new Notice("Moss: connection settings changed — run “Moss: Rebuild index” to reopen the session.");
    }
  }

  // ── public actions (commands / settings) ─────────────────────────────

  openSearch(): void {
    if (!this.indexer.canSearch()) {
      const status = this.indexer.getStatus();
      if (status.state === "indexing") {
        new Notice(`Moss is still indexing (${status.processed}/${status.total}).`);
      } else if (!this.hasCredentials()) {
        new Notice("Moss: add your project ID and key in settings, then run “Create index”.");
      } else {
        new Notice("Moss: no index yet. Run “Moss: Create index”.");
      }
      return;
    }
    new MossSearchModal(this.app, {
      search: (query) => this.search(query),
      statusLine: () => this.statusText(this.indexer.getStatus()),
    }).open();
  }

  async rebuildIndex(): Promise<void> {
    if (!this.hasCredentials()) {
      new Notice("Moss: add your project ID and key in settings first.");
      return;
    }
    if (this.indexer.isIndexing()) {
      new Notice("Moss is already indexing.");
      return;
    }
    try {
      const session = await this.ensureSession();
      this.indexer.attachSession(session);
      const started = Date.now();
      await this.indexer.rebuild();
      const status = this.indexer.getStatus();
      if (status.state === "ready") {
        const secs = ((Date.now() - started) / 1000).toFixed(1);
        new Notice(`Moss indexed ${status.files} notes (${status.chunks} sections) in ${secs}s.`);
        await this.persistNow();
        if (this.settings.cloudSync) {
          await this.syncToCloud(false);
        }
      } else if (status.state === "error") {
        new Notice(`Moss indexing failed: ${status.message}`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.log(`Index build failed: ${message}`);
      new Notice(`Moss indexing failed: ${message}`);
    }
  }

  async syncToCloud(interactive: boolean): Promise<void> {
    const session = this.sessionManager.getSession();
    if (!session || !this.indexer.isIndexed()) {
      if (interactive) new Notice("Moss: build an index before syncing.");
      return;
    }
    if (!this.sessionMatchesSettings()) {
      this.log("Skipping cloud sync: session was opened with different settings; rebuild first.");
      if (interactive) new Notice("Moss: settings changed since this index was built — run “Rebuild index” first.");
      return;
    }
    try {
      const result = await session.pushIndex();
      this.log(`Pushed ${result.docCount} docs to cloud index ${result.indexName} (${result.status})`);
      const meta = await this.cache.readMeta();
      if (meta) {
        await this.cache.writeMeta({ ...meta, cloudPushedAt: new Date().toISOString() });
      }
      if (interactive) new Notice(`Moss: uploaded ${result.docCount} sections to ${result.indexName} (${result.status}).`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.log(`Cloud sync failed: ${message}`);
      if (interactive) new Notice(`Moss cloud sync failed: ${message}`);
    }
  }

  async restartWorker(): Promise<void> {
    if (this.indexer.isIndexing()) {
      new Notice("Moss is indexing — cancel it before restarting the worker.");
      return;
    }
    await this.sessionManager.dispose();
    this.indexer.detachSession();
    this.bootstrapped = false;
    await this.bootstrap();
    new Notice("Moss worker restarted.");
  }

  // ── internals ────────────────────────────────────────────────────────

  private hasCredentials(): boolean {
    return !!(this.settings.projectId && this.settings.projectKey);
  }

  private pluginDir(): string {
    const adapter = this.app.vault.adapter;
    const base = adapter instanceof FileSystemAdapter ? adapter.getBasePath() : "";
    const rel = this.manifest.dir ?? `${this.app.vault.configDir}/plugins/${this.manifest.id}`;
    return path.join(base, rel);
  }

  private vaultPath(): string {
    const adapter = this.app.vault.adapter;
    return adapter instanceof FileSystemAdapter ? adapter.getBasePath() : this.app.vault.getName();
  }

  private sessionName(): string {
    return vaultSessionName(this.settings.vaultId);
  }

  private log(message: string): void {
    console.log(`[moss] ${message}`);
  }

  private async ensureSession(): Promise<LocalMossSession> {
    const credentials = { projectId: this.settings.projectId, projectKey: this.settings.projectKey };
    const name = this.sessionName();
    const existing = this.sessionManager.getSession();
    if (existing && this.sessionManager.isReady) {
      if (this.sessionManager.matchesInit(credentials, name, this.settings.model)) {
        return existing;
      }
      // Credentials or model changed since the session was opened: a session
      // embeds with the model it was created with, so reopen rather than
      // silently indexing with the old one.
      this.log("Settings changed; reopening Moss session.");
      this.indexer.detachSession();
      await this.sessionManager.dispose();
    }
    return this.sessionManager.initialize(credentials, name, this.settings.model);
  }

  /**
   * Startup: open the session and restore the index from the on-disk cache
   * (or from Moss Cloud when sync is on and no cache exists). Never builds a
   * fresh index on its own — that is an explicit user action.
   */
  private bootstrap(): Promise<void> {
    if (this.bootstrapped) return Promise.resolve();
    if (this.bootstrapping) return this.bootstrapping;
    this.bootstrapping = this.doBootstrap().finally(() => {
      this.bootstrapping = undefined;
    });
    return this.bootstrapping;
  }

  private async doBootstrap(): Promise<void> {
    if (!this.hasCredentials()) {
      this.log("No credentials configured; waiting for settings.");
      return;
    }
    try {
      const session = await this.ensureSession();
      this.indexer.attachSession(session);
      this.bootstrapped = true;

      const meta = await this.cache.readMeta();
      if (meta && meta.sessionName === this.sessionName()) {
        if (meta.maxCharsPerChunk !== undefined && meta.maxCharsPerChunk !== this.settings.maxCharsPerChunk) {
          this.log("Cache was built with a different chunk size — ignoring cache.");
          new Notice("Moss: chunk size changed. Run “Moss: Rebuild index”.");
        } else if (meta.model && meta.model !== this.settings.model) {
          // Vectors from another model in this session would be garbage:
          // treat the cache as absent and ask for a rebuild.
          this.log(`Cache was built with ${meta.model}, settings say ${this.settings.model} — ignoring cache.`);
          new Notice("Moss: embedding model changed. Run “Moss: Rebuild index”.");
        } else {
          const loaded = await session.loadFromDisk(this.cache.dir);
          if (loaded > 0) {
            this.log(`Restored ${loaded} sections from disk cache.`);
            this.indexer.restoreFromMeta(meta.pathChunkCounts, meta.pathMtimes ?? {});
            await this.reconcileAfterRestore();
            return;
          }
          // meta.json without session files (partial copy, cleared cache):
          // don't pretend an empty index is ready.
          this.log("Disk cache was empty or unreadable — clearing it.");
          await this.cache.clear();
        }
      }

      if (this.settings.cloudSync) {
        try {
          const loaded = await session.loadIndex(this.sessionName());
          if (loaded > 0) {
            const docs = await session.getDocs();
            this.indexer.restoreFromMeta(pathChunkCountsFromDocs(docs));
            this.log(`Restored ${loaded} sections from Moss Cloud.`);
            await this.reconcileAfterRestore();
            await this.persistNow();
            return;
          }
        } catch (err) {
          this.log(`No cloud index to restore: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
      this.log("No index yet. Run “Moss: Create index”.");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.log(`Startup failed: ${message}`);
      new Notice(`Moss failed to start: ${message}`);
    }
  }

  /** Catch up on notes changed while the plugin was not running. */
  private async reconcileAfterRestore(): Promise<void> {
    try {
      const { upserted, removed } = await this.indexer.reconcile();
      if (upserted || removed) {
        this.log(`Reconciled restored index: ${upserted} notes re-indexed, ${removed} removed.`);
        await this.persistNow();
      }
    } catch (err) {
      this.log(`Reconcile failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  private async search(query: string): Promise<SearchHit[]> {
    const session = this.sessionManager.getSession();
    if (!session || !this.indexer.canSearch()) {
      return [];
    }
    const result = await session.query(query, {
      topK: this.settings.topK,
      alpha: this.settings.alpha,
    });
    const hits = (result.docs ?? []).map(mapHit);
    return dedupeByNote(hits, this.settings.onePerNote);
  }

  private registerVaultEvents(): void {
    const onFile = (file: TAbstractFile, fn: (p: string) => Promise<void>) => {
      // Filter on file type only — upsertPath itself handles exclusions, and
      // must see events for excluded notes to drop their stale chunks.
      if (!(file instanceof TFile) || !isMarkdownPath(file.path)) {
        return;
      }
      this.debounceFile(file.path, () => fn(file.path));
    };

    this.registerEvent(this.app.vault.on("modify", (file) => onFile(file, (p) => this.indexer.upsertPath(p))));
    this.registerEvent(this.app.vault.on("create", (file) => onFile(file, (p) => this.indexer.upsertPath(p))));
    this.registerEvent(
      this.app.vault.on("delete", (file) => {
        if (file instanceof TFile) {
          void this.indexer.removePath(file.path).catch((err) => this.log(`delete failed: ${String(err)}`));
        } else if (file instanceof TFolder) {
          // Obsidian reports the folder only — its notes get no events of
          // their own, so drop them here or they linger in the index.
          void this.indexer
            .removeFolder(file.path)
            .catch((err) => this.log(`folder delete failed: ${String(err)}`));
        }
      }),
    );
    this.registerEvent(
      this.app.vault.on("rename", (file, oldPath) => {
        if (file instanceof TFile) {
          void this.indexer.renamePath(oldPath, file.path).catch((err) => this.log(`rename failed: ${String(err)}`));
        } else if (file instanceof TFolder) {
          void this.indexer
            .renameFolder(oldPath, file.path)
            .catch((err) => this.log(`folder rename failed: ${String(err)}`));
        }
      }),
    );
  }

  private debounceFile(relativePath: string, fn: () => Promise<void>): void {
    const existing = this.fileTimers.get(relativePath);
    if (existing) clearTimeout(existing);
    this.fileTimers.set(
      relativePath,
      setTimeout(() => {
        this.fileTimers.delete(relativePath);
        const previous = this.fileOps.get(relativePath) ?? Promise.resolve();
        const run = previous
          .then(() => fn())
          .catch((err) => this.log(`incremental index failed for ${relativePath}: ${String(err)}`))
          .finally(() => {
            if (this.fileOps.get(relativePath) === run) {
              this.fileOps.delete(relativePath);
            }
          });
        this.fileOps.set(relativePath, run);
      }, FILE_EVENT_DEBOUNCE_MS),
    );
  }

  private schedulePersist(): void {
    if (this.persistTimer) clearTimeout(this.persistTimer);
    this.persistTimer = setTimeout(() => {
      void this.persistNow().catch((err) => this.log(`persist failed: ${String(err)}`));
    }, PERSIST_DEBOUNCE_MS);

    if (this.settings.cloudSync) {
      if (this.cloudPushTimer) clearTimeout(this.cloudPushTimer);
      this.cloudPushTimer = setTimeout(() => {
        // Re-check at fire time: the user may have turned sync off meanwhile.
        if (this.settings.cloudSync) {
          void this.syncToCloud(false);
        }
      }, CLOUD_PUSH_DEBOUNCE_MS);
    }
  }

  private sessionMatchesSettings(): boolean {
    return this.sessionManager.matchesInit(
      { projectId: this.settings.projectId, projectKey: this.settings.projectKey },
      this.sessionName(),
      this.settings.model,
    );
  }

  private async persistNow(): Promise<void> {
    const session = this.sessionManager.getSession();
    const status = this.indexer.getStatus();
    if (status.state === "unindexed") {
      // The index emptied out (last note deleted or excluded): a stale cache
      // must not resurrect the old contents on next launch.
      await this.cache.clear();
      return;
    }
    if (!session || status.state !== "ready") {
      return;
    }
    if (!this.sessionMatchesSettings()) {
      this.log("Skipping persist: session was opened with different settings.");
      return;
    }
    await this.cache.ensureDir();
    await session.saveToDisk(this.cache.dir);
    const previous = await this.cache.readMeta();
    await this.cache.writeMeta({
      vaultPath: this.vaultPath(),
      sessionName: this.sessionName(),
      model: this.settings.model,
      files: status.files,
      chunks: status.chunks,
      pathChunkCounts: this.indexer.getPathChunkCounts(),
      pathMtimes: this.indexer.getPathMtimes(),
      maxCharsPerChunk: this.settings.maxCharsPerChunk,
      savedAt: new Date().toISOString(),
      cloudPushedAt: previous?.cloudPushedAt,
    });
  }

  private statusText(status: IndexStatus): string {
    switch (status.state) {
      case "unindexed":
        return "Moss: no index";
      case "indexing":
        return `Moss: indexing ${status.processed}/${status.total}`;
      case "ready":
        return `Moss: ${status.files} notes · ${status.chunks} sections`;
      case "error":
        return `Moss: error`;
    }
  }

  private renderStatus(status: IndexStatus): void {
    this.statusBar.setText(this.statusText(status));
    this.statusBar.setAttr("aria-label", status.state === "error" ? status.message : "Open Moss semantic search");
  }
}
