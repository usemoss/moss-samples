import * as vscode from "vscode";
import { MossSessionManager } from "./moss/client";
import {
  clearWorkspaceIndexed,
  getSettingsSnapshot,
  isCloudSyncEnabled,
  markWorkspaceIndexed,
  promptAndStoreCredentials,
  resolveCredentials,
  setCloudSyncEnabled,
  storeCredentials,
  workspaceSessionName,
} from "./moss/config";
import {
  clearIndexCache,
  ensureIndexCacheDir,
  indexCacheDir,
  indexCacheExists,
  pathChunkCountsFromDocs,
  readIndexMeta,
  workspaceRootPath,
  writeIndexMeta,
} from "./moss/persistence";
import { CodebaseIndexer } from "./indexer/indexer";
import { SemanticSearch, type SearchHit } from "./search/search";
import { MossSearchViewProvider } from "./ui/sidebar";

let statusBarItem: vscode.StatusBarItem | undefined;
let outputChannel: vscode.OutputChannel | undefined;
let persistTimer: NodeJS.Timeout | undefined;

function log(message: string): void {
  outputChannel?.appendLine(`[${new Date().toISOString()}] ${message}`);
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  outputChannel = vscode.window.createOutputChannel("Moss Code Search");
  context.subscriptions.push(outputChannel);
  log("Moss Code Search activating…");

  context.subscriptions.push(
    vscode.commands.registerCommand("moss.logs.show", () => {
      outputChannel?.show(true);
    }),
  );

  try {
    await activateExtension(context);
    log("Moss Code Search activated.");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    log(`Activation failed: ${message}`);
    if (err instanceof Error && err.stack) {
      log(err.stack);
    }
    outputChannel.show(true);
    vscode.window.showErrorMessage(`Moss Code Search failed to start: ${message}`);
    throw err;
  }
}

async function activateExtension(context: vscode.ExtensionContext): Promise<void> {
  const sessionManager = new MossSessionManager(context.extensionPath, log);
  const indexer = new CodebaseIndexer();
  const search = new SemanticSearch(
    () => (indexer.canSearch() ? sessionManager.getSession() : undefined),
    () => indexer.canSearch(),
  );

  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    100,
  );
  statusBarItem.text = "$(search) Moss";
  statusBarItem.command = "moss.search.focus";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  const persistNow = async (): Promise<void> => {
    await persistIndex(context, sessionManager, indexer);
  };

  const schedulePersist = (): void => {
    if (persistTimer) {
      clearTimeout(persistTimer);
    }
    persistTimer = setTimeout(() => {
      void persistNow().catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        log(`Debounced persist failed: ${message}`);
      });
    }, 1500);
  };

  indexer.setPersistHandler(schedulePersist);

  const createIndex = async (): Promise<void> => {
    await runCreateIndex(context, sessionManager, indexer, provider);
  };

  let provider: MossSearchViewProvider;
  provider = new MossSearchViewProvider(context.extensionUri, {
    onQuery: async (query) => search.query(query),
    onOpen: async (hit) => openHit(hit),
    onCreateIndex: createIndex,
    onSyncCloud: async () => syncIndexToCloud(context, sessionManager, indexer, provider),
    onGetSettings: async () => getSettingsSnapshot(context),
    onSaveSettings: async (settings) => {
      await setCloudSyncEnabled(settings.cloudSync);
      const projectId = settings.projectId.trim();
      const projectKey = settings.projectKey?.trim();
      if (projectId) {
        const creds = await storeCredentials(context, projectId, projectKey);
        if (!creds) {
          return {
            ok: false,
            message: "Enter a project key, or save a key first.",
          };
        }
      } else if (projectKey) {
        return { ok: false, message: "Enter a project ID with the project key." };
      }
      const hasCreds = !!(await resolveCredentials(context));
      if (!hasCreds && !indexCacheExists(context)) {
        provider.setStatus({
          state: "error",
          message: "Missing credentials. Add your Moss project ID and key.",
        });
      } else if (!indexer.isIndexed() && !indexCacheExists(context)) {
        provider.setStatus({ state: "unindexed" });
      }
      return { ok: true, message: "Settings saved." };
    },
  });

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      MossSearchViewProvider.viewType,
      provider,
    ),
  );

  context.subscriptions.push(
    indexer.onStatus((status) => {
      provider.setStatus(status);
      updateStatusBar(status);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("moss.search.focus", async () => {
      await vscode.commands.executeCommand("moss.searchView.focus");
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("moss.credentials.configure", async () => {
      await vscode.commands.executeCommand("moss.searchView.focus");
      provider.openSettings();
      const creds = await promptAndStoreCredentials(context);
      if (creds) {
        if (!indexCacheExists(context)) {
          provider.setStatus({ state: "unindexed" });
        }
        vscode.window.showInformationMessage(
          "Moss credentials saved. Click Create Index in the sidebar if this workspace is not indexed yet.",
        );
      }
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("moss.index.create", createIndex),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("moss.index.rebuild", async () => {
      await runCreateIndex(context, sessionManager, indexer, provider, true);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("moss.index.syncCloud", async () => {
      await syncIndexToCloud(context, sessionManager, indexer, provider);
    }),
  );

  context.subscriptions.push({
    dispose: () => {
      if (persistTimer) {
        clearTimeout(persistTimer);
      }
      indexer.dispose();
      sessionManager.dispose();
    },
  });

  await bootstrap(context, sessionManager, indexer, provider);
}

function updateStatusBar(status: import("./indexer/indexer").IndexStatus): void {
  if (!statusBarItem) {
    return;
  }
  if (status.state === "indexing") {
    statusBarItem.text = `$(sync~spin) Moss: indexing ${status.processed}/${status.total}`;
    statusBarItem.tooltip = undefined;
  } else if (status.state === "ready") {
    statusBarItem.text = `$(check) Moss: ${status.files} files`;
    statusBarItem.tooltip = undefined;
  } else if (status.state === "error") {
    statusBarItem.text = "$(error) Moss: error";
    statusBarItem.tooltip = status.message;
  } else if (status.state === "unindexed") {
    statusBarItem.text = "$(database) Moss: not indexed";
    statusBarItem.tooltip = "Click Create Index in the Moss Search sidebar";
  }
}

async function persistIndex(
  context: vscode.ExtensionContext,
  sessionManager: MossSessionManager,
  indexer: CodebaseIndexer,
  options: { skipCloudPush?: boolean } = {},
): Promise<void> {
  if (!sessionManager.isReady || !indexer.isIndexed()) {
    return;
  }
  const cacheDir = await ensureIndexCacheDir(context);
  const session = sessionManager.getSession();
  await session.saveToDisk(cacheDir);
  const status = indexer.getStatus();
  const files = status.state === "ready" ? status.files : 0;
  const chunks = status.state === "ready" ? status.chunks : 0;
  const existingMeta = await readIndexMeta(context);
  const meta = {
    workspaceRoot: workspaceRootPath(),
    sessionName: workspaceSessionName(),
    files,
    chunks,
    pathChunkCounts: indexer.getPathChunkCounts(),
    savedAt: new Date().toISOString(),
    cloudPushedAt: existingMeta?.cloudPushedAt,
  };
  await writeIndexMeta(context, meta);
  await markWorkspaceIndexed(context);
  log(`Persisted index to ${cacheDir} (${files} files, ${chunks} chunks)`);

  if (!options.skipCloudPush && isCloudSyncEnabled()) {
    await pushIndexToCloud(context, sessionManager, indexer, meta);
  }
}

async function pushIndexToCloud(
  context: vscode.ExtensionContext,
  sessionManager: MossSessionManager,
  indexer: CodebaseIndexer,
  meta?: Awaited<ReturnType<typeof readIndexMeta>>,
  provider?: MossSearchViewProvider,
): Promise<boolean> {
  if (!sessionManager.isReady || !indexer.isIndexed()) {
    return false;
  }
  const sessionName = workspaceSessionName();
  provider?.setCloudSyncState("syncing");
  if (statusBarItem) {
    statusBarItem.text = "$(cloud-upload) Moss: syncing to cloud…";
  }
  try {
    const pushed = await sessionManager.getSession().pushIndex();
    const currentMeta = meta ?? (await readIndexMeta(context));
    if (currentMeta) {
      await writeIndexMeta(context, {
        ...currentMeta,
        cloudPushedAt: new Date().toISOString(),
      });
    }
    log(
      `Pushed index "${sessionName}" to Moss Cloud — ${pushed.docCount} docs (job ${pushed.jobId})`,
    );
    provider?.setCloudSyncState("success");
    updateStatusBar(indexer.getStatus());
    return true;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    log(`Cloud push failed: ${message}`);
    provider?.setCloudSyncState("error", `Cloud sync failed: ${message}`);
    vscode.window.showWarningMessage(
      `Moss could not sync the index to the cloud. Local search still works. (${message})`,
    );
    updateStatusBar(indexer.getStatus());
    return false;
  }
}

async function syncIndexToCloud(
  context: vscode.ExtensionContext,
  sessionManager: MossSessionManager,
  indexer: CodebaseIndexer,
  provider?: MossSearchViewProvider,
): Promise<void> {
  if (!indexer.isIndexed()) {
    provider?.setCloudSyncState("error", "Create an index before syncing to Moss Cloud.");
    vscode.window.showInformationMessage("Create an index before syncing to Moss Cloud.");
    return;
  }
  if (!isCloudSyncEnabled()) {
    provider?.setCloudSyncState(
      "error",
      "Cloud sync is disabled. Enable moss.cloudSync in settings.",
    );
    vscode.window.showInformationMessage(
      "Cloud sync is disabled. Enable moss.cloudSync in settings.",
    );
    return;
  }
  const ok = await pushIndexToCloud(context, sessionManager, indexer, undefined, provider);
  if (ok) {
    vscode.window.showInformationMessage("Moss index synced to the cloud.");
  }
}

async function bootstrap(
  context: vscode.ExtensionContext,
  sessionManager: MossSessionManager,
  indexer: CodebaseIndexer,
  provider: MossSearchViewProvider,
): Promise<void> {
  const credentials = await resolveCredentials(context);
  if (!credentials) {
    provider.setStatus({
      state: "error",
      message: "Missing credentials. Run “Moss: Configure Credentials”.",
    });
    if (statusBarItem) {
      statusBarItem.text = "$(warning) Moss: credentials needed";
    }
    return;
  }

  const meta = await readIndexMeta(context);
  const hasLocalCache =
    !!meta && Object.keys(meta.pathChunkCounts).length > 0 && indexCacheExists(context);

  if (!hasLocalCache && !isCloudSyncEnabled()) {
    provider.setStatus({ state: "unindexed" });
    log(`Workspace ${workspaceSessionName()} ready — waiting for Create Index`);
    return;
  }

  if (!hasLocalCache) {
    try {
      if (statusBarItem) {
        statusBarItem.text = "$(cloud-download) Moss: checking cloud index…";
      }
      log(`No local cache — trying Moss Cloud index ${workspaceSessionName()}`);
      const session = await sessionManager.initialize(credentials);
      indexer.attachSession(session);
      let docCount = session.docCount;
      if (docCount <= 0) {
        try {
          docCount = await session.loadIndex(workspaceSessionName());
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          log(`Cloud index not found: ${message}`);
        }
      }
      if (docCount <= 0 && session.docCount <= 0) {
        sessionManager.dispose();
        provider.setStatus({ state: "unindexed" });
        log(`Workspace ${workspaceSessionName()} ready — waiting for Create Index`);
        return;
      }
      const docs = await session.getDocs();
      const pathChunkCounts = pathChunkCountsFromDocs(docs);
      if (Object.keys(pathChunkCounts).length === 0) {
        throw new Error("Cloud index had no file metadata");
      }
      indexer.restoreFromMeta(pathChunkCounts);
      indexer.startWatching(context.subscriptions);
      await persistIndex(context, sessionManager, indexer, { skipCloudPush: true });
      await markWorkspaceIndexed(context);
      const restored = indexer.getStatus();
      const restoredFiles = restored.state === "ready" ? restored.files : 0;
      const restoredChunks = restored.state === "ready" ? restored.chunks : 0;
      log(
        `Restored index from Moss Cloud for ${workspaceSessionName()} — ${restoredFiles} files, ${restoredChunks} chunks`,
      );
      return;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      log(`Cloud restore failed: ${message}`);
      sessionManager.dispose();
      provider.setStatus({ state: "unindexed" });
      if (statusBarItem) {
        statusBarItem.text = "$(database) Moss: not indexed";
      }
      return;
    }
  }

  try {
    if (statusBarItem) {
      statusBarItem.text = "$(sync~spin) Moss: loading saved index…";
    }
    log(`Restoring index from ${indexCacheDir(context)}`);
    const session = await sessionManager.initialize(credentials);
    indexer.attachSession(session);
    const loaded = await session.loadFromDisk(indexCacheDir(context));
    if (loaded <= 0 && session.docCount <= 0) {
      throw new Error("Saved index was empty");
    }
    indexer.restoreFromMeta(meta.pathChunkCounts);
    indexer.startWatching(context.subscriptions);
    await markWorkspaceIndexed(context);
    log(
      `Restored index for ${workspaceSessionName()} — ${meta.files} files, ${meta.chunks} chunks (loaded=${loaded}, docCount=${session.docCount})`,
    );
    if (isCloudSyncEnabled() && meta.cloudPushedAt) {
      log(`Last cloud sync: ${meta.cloudPushedAt}`);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    log(`Restore failed: ${message}`);
    await clearWorkspaceIndexed(context);
    // Best-effort here: the workspace-indexed marker is already cleared above,
    // so a leftover directory cannot be restored from. Still log it rather than
    // discarding the reason silently.
    await clearIndexCache(context).catch((cacheErr: unknown) => {
      log(`Could not remove the unusable index cache: ${String(cacheErr)}`);
    });
    sessionManager.dispose();
    indexer.restoreFromMeta({});
    provider.setStatus({ state: "unindexed" });
    if (statusBarItem) {
      statusBarItem.text = "$(database) Moss: not indexed";
    }
    vscode.window.showWarningMessage(
      `Moss could not restore the saved index. Click Create Index to rebuild. (${message})`,
    );
  }
}

async function runCreateIndex(
  context: vscode.ExtensionContext,
  sessionManager: MossSessionManager,
  indexer: CodebaseIndexer,
  provider: MossSearchViewProvider,
  rebuild = false,
): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length) {
    vscode.window.showWarningMessage("Open a folder before creating an index.");
    return;
  }

  let credentials = await resolveCredentials(context);
  if (!credentials) {
    const choice = await vscode.window.showInformationMessage(
      "Moss needs project credentials before indexing.",
      "Configure",
    );
    if (choice === "Configure") {
      credentials = await promptAndStoreCredentials(context);
    }
  }
  if (!credentials) {
    provider.setStatus({
      state: "error",
      message: "Missing credentials. Run “Moss: Configure Credentials”.",
    });
    return;
  }

  if (indexer.getStatus().state === "indexing") {
    vscode.window.showInformationMessage("Moss is already indexing this workspace.");
    return;
  }

  try {
    if (!sessionManager.isReady) {
      if (statusBarItem) {
        statusBarItem.text = "$(sync~spin) Moss: connecting…";
      }
      const session = await sessionManager.initialize(credentials);
      indexer.attachSession(session);
      indexer.startWatching(context.subscriptions);
    }

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: rebuild ? "Moss: rebuilding index…" : "Moss: creating index…",
        cancellable: true,
      },
      async (_progress, token) => {
        await indexer.rebuild(token);
      },
    );

    if (indexer.isIndexed()) {
      await persistIndex(context, sessionManager, indexer);
      const status = indexer.getStatus();
      const files = status.state === "ready" ? status.files : 0;
      log(`Index created for ${workspaceSessionName()}`);
      vscode.window.showInformationMessage(
        `Moss index ready — ${files} files indexed (saved for next time).`,
      );
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    log(`Create index failed: ${message}`);
    provider.setStatus({ state: "error", message });
    vscode.window.showErrorMessage(`Moss indexing failed: ${message}`);
    if (statusBarItem) {
      statusBarItem.text = "$(error) Moss: error";
      statusBarItem.tooltip = message;
    }
  } finally {
    // rebuild() deletes the previous documents before scanning, so any run that
    // got that far and did not end ready leaves the on-disk cache describing
    // documents that no longer exist — cancelled, or thrown from
    // readFileForIndex()/addDocs() midway. persistIndex() refuses to write
    // while unindexed, so drop the cache here instead, in a finally so the
    // throw path cannot skip it.
    //
    // Gated on hasDiscardedPreviousIndex() so a failure *before* deletion began
    // (session setup, workspace scan) keeps the cache — those documents are
    // still intact and re-indexing from scratch would be wasted work.
    if (!indexer.isIndexed() && indexer.hasDiscardedPreviousIndex()) {
      try {
        await clearIndexCache(context);
        log("Index not ready; cleared stale index cache.");
      } catch (err) {
        // Only reached if the cache directory could not be removed. Leaving it
        // would let the next activation restore metadata describing documents
        // this rebuild deleted, so drop the workspace-indexed marker as a
        // second line of defence and make the failure visible rather than
        // logging a success that did not happen.
        const message = err instanceof Error ? err.message : String(err);
        log(`Failed to clear stale index cache: ${message}`);
        await clearWorkspaceIndexed(context).catch(() => undefined);
        vscode.window.showWarningMessage(
          `Moss could not clear its stale index cache (${message}). Run “Moss: Create Index” to rebuild.`,
        );
      }
    }
  }
}

async function openHit(hit: SearchHit): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length) {
    return;
  }

  let target: vscode.Uri | undefined;
  for (const folder of folders) {
    const candidate = vscode.Uri.joinPath(folder.uri, hit.filePath);
    try {
      await vscode.workspace.fs.stat(candidate);
      target = candidate;
      break;
    } catch {
      // try next folder
    }
  }

  if (!target) {
    vscode.window.showWarningMessage(`Could not open ${hit.filePath}`);
    return;
  }

  const line = Math.max(0, (hit.startLine || 1) - 1);
  const doc = await vscode.workspace.openTextDocument(target);
  const editor = await vscode.window.showTextDocument(doc, { preview: true });
  const position = new vscode.Position(line, 0);
  editor.selection = new vscode.Selection(position, position);
  editor.revealRange(
    new vscode.Range(position, position),
    vscode.TextEditorRevealType.InCenter,
  );
}

export function deactivate(): void {
  // disposed via subscriptions
}
