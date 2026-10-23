import { describe, expect, it } from "vitest";
import type { DocumentInfo } from "@moss-dev/moss";
import { VaultIndexer, type VaultReader } from "../src/indexer/indexer";
import type { LocalMossSession } from "../src/moss/client";

/** In-memory stand-in for the worker-backed Moss session. */
class FakeSession implements LocalMossSession {
  docs = new Map<string, DocumentInfo>();
  calls: string[] = [];
  lastAddOptions: { upsert?: boolean } | undefined;

  get docCount(): number {
    return this.docs.size;
  }

  async addDocs(docs: DocumentInfo[], options?: { upsert?: boolean }): Promise<{ added: number; updated: number }> {
    this.calls.push(`add:${docs.length}`);
    this.lastAddOptions = options;
    let added = 0;
    let updated = 0;
    for (const doc of docs) {
      if (this.docs.has(doc.id)) updated++;
      else added++;
      this.docs.set(doc.id, doc);
    }
    return { added, updated };
  }

  async deleteDocs(ids: string[]): Promise<number> {
    this.calls.push(`del:${ids.length}`);
    let n = 0;
    for (const id of ids) {
      if (this.docs.delete(id)) n++;
    }
    return n;
  }

  async query(): Promise<never> {
    throw new Error("not used");
  }
  async getDocs(): Promise<DocumentInfo[]> {
    return [...this.docs.values()];
  }
  async loadIndex(): Promise<number> {
    return 0;
  }
  async pushIndex(): Promise<never> {
    throw new Error("not used");
  }
  async saveToDisk(): Promise<void> {}
  async loadFromDisk(): Promise<number> {
    return 0;
  }
}

function makeVault(
  files: Record<string, string>,
  mtimes: Record<string, number> = {},
): VaultReader & { files: Record<string, string>; mtimes: Record<string, number> } {
  return {
    files,
    mtimes,
    listMarkdownPaths: () => Object.keys(files).filter((p) => p.endsWith(".md")),
    read: async (p) => files[p],
    mtime: (p) => (p in files ? mtimes[p] ?? 1000 : undefined),
  };
}

const config = () => ({ excludedFolders: ["templates"], chunk: { maxCharsPerChunk: 1600 } });

describe("VaultIndexer.rebuild", () => {
  it("indexes markdown notes, skips excluded folders and non-markdown files", async () => {
    const vault = makeVault({
      "A.md": "# One\nbody",
      "dir/B.md": "# Two\nbody\n## Three\nmore",
      "templates/T.md": "# Template",
      "img.png": "binary",
    });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.rebuild();

    expect(indexer.getStatus()).toEqual({ state: "ready", files: 2, chunks: 3 });
    expect(indexer.getPathChunkCounts()).toEqual({ "A.md": 1, "dir/B.md": 2 });
    expect(session.lastAddOptions).toEqual({ upsert: true });
    expect([...session.docs.keys()].sort()).toEqual(["A.md#chunk-0", "dir/B.md#chunk-0", "dir/B.md#chunk-1"]);
  });

  it("reports an error state when nothing is indexable", async () => {
    const indexer = new VaultIndexer(makeVault({ "templates/T.md": "# x" }), config);
    indexer.attachSession(new FakeSession());
    await indexer.rebuild();
    expect(indexer.getStatus().state).toBe("error");
    expect(indexer.canSearch()).toBe(false);
  });

  it("deletes stale chunks of previously indexed notes on rebuild", async () => {
    const vault = makeVault({ "A.md": "# One\nbody\n# Two\nbody" });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.rebuild();
    expect(session.docCount).toBe(2);

    vault.files["A.md"] = "# Only";
    await indexer.rebuild();
    expect(session.docCount).toBe(1);
    expect(session.calls).toContain("del:2");
  });

  it("throws without a session", async () => {
    const indexer = new VaultIndexer(makeVault({}), config);
    await expect(indexer.rebuild()).rejects.toThrow(/session/);
  });
});

describe("VaultIndexer incremental", () => {
  async function setup() {
    const vault = makeVault({ "A.md": "# One\nbody\n## Two\nmore", "B.md": "# B" });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    let persists = 0;
    indexer.setPersistHandler(() => persists++);
    await indexer.rebuild();
    return { vault, session, indexer, persists: () => persists };
  }

  it("upsertPath trims chunks when a note shrinks", async () => {
    const { vault, session, indexer } = await setup();
    vault.files["A.md"] = "# One\nbody";
    await indexer.upsertPath("A.md");
    expect(session.docs.has("A.md#chunk-1")).toBe(false);
    expect(indexer.getPathChunkCounts()["A.md"]).toBe(1);
  });

  it("upsertPath adds chunks when a note grows", async () => {
    const { vault, session, indexer } = await setup();
    vault.files["B.md"] = "# B\n## C\n## D";
    await indexer.upsertPath("B.md");
    expect(indexer.getPathChunkCounts()["B.md"]).toBe(3);
    expect(session.docs.has("B.md#chunk-2")).toBe(true);
  });

  it("removePath drops all chunks and updates status", async () => {
    const { session, indexer, persists } = await setup();
    const before = persists();
    await indexer.removePath("A.md");
    expect(session.docs.has("A.md#chunk-0")).toBe(false);
    expect(indexer.getStatus()).toEqual({ state: "ready", files: 1, chunks: 1 });
    expect(persists()).toBe(before + 1);
  });

  it("renamePath moves chunks to the new id namespace", async () => {
    const { vault, session, indexer } = await setup();
    vault.files["C.md"] = vault.files["A.md"];
    delete vault.files["A.md"];
    await indexer.renamePath("A.md", "C.md");
    expect([...session.docs.keys()].filter((k) => k.startsWith("A.md"))).toEqual([]);
    expect(indexer.getPathChunkCounts()).toEqual({ "B.md": 1, "C.md": 2 });
  });

  it("upsertPath on a now-excluded note removes its chunks", async () => {
    const vault = makeVault({ "A.md": "# One" });
    const session = new FakeSession();
    let excluded: string[] = [];
    const indexer = new VaultIndexer(vault, () => ({ excludedFolders: excluded, chunk: {} }));
    indexer.attachSession(session);
    await indexer.rebuild();
    excluded = ["A.md"];
    await indexer.upsertPath("A.md");
    expect(session.docCount).toBe(0);
  });

  it("ignores incremental events before any index exists", async () => {
    const vault = makeVault({ "A.md": "# One" });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.upsertPath("A.md");
    expect(session.docCount).toBe(0);
  });

  it("cancel leaves an error state, not a partial 'ready' index", async () => {
    const files: Record<string, string> = {};
    for (let i = 0; i < 60; i++) files[`n${i}.md`] = `# H${i}\nbody`;
    const vault = makeVault(files);
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    let persists = 0;
    indexer.setPersistHandler(() => persists++);
    indexer.onStatus((status) => {
      if (status.state === "indexing" && status.processed === 10) {
        indexer.cancel();
      }
    });
    await indexer.rebuild();
    const status = indexer.getStatus();
    expect(status.state).toBe("error");
    expect(status.state === "error" && status.message).toMatch(/cancelled/i);
    expect(indexer.canSearch()).toBe(false);
    expect(persists).toBe(0);
  });

  it("reconcile drops deleted notes and re-indexes new and changed ones", async () => {
    const vault = makeVault(
      { "A.md": "# A\nold", "B.md": "# B", "C.md": "# C" },
      { "A.md": 1000, "B.md": 1000, "C.md": 1000 },
    );
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.rebuild();

    // Simulate offline edits: A changed, B deleted, D created.
    vault.files["A.md"] = "# A\nnew\n## More\nbody";
    vault.mtimes["A.md"] = 2000;
    delete vault.files["B.md"];
    vault.files["D.md"] = "# D";
    vault.mtimes["D.md"] = 2000;

    // Fresh indexer restoring from persisted meta, as after a restart.
    const indexer2 = new VaultIndexer(vault, config);
    indexer2.attachSession(session);
    indexer2.restoreFromMeta(indexer.getPathChunkCounts(), indexer.getPathMtimes());
    const { upserted, removed } = await indexer2.reconcile();

    expect(removed).toBe(1);
    expect(upserted).toBe(2); // A (changed) + D (new)
    expect(session.docs.has("B.md#chunk-0")).toBe(false);
    expect(session.docs.has("D.md#chunk-0")).toBe(true);
    expect(session.docs.get("A.md#chunk-0")?.text).toContain("new");
    expect(indexer2.getPathChunkCounts()["A.md"]).toBe(2);
  });

  it("reconcile re-indexes a note whose mtime moved BACKWARD (git checkout/restore)", async () => {
    const vault = makeVault({ "A.md": "# A\nnew-old-content" }, { "A.md": 2000 });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.rebuild();

    // Restored file: different content, OLDER mtime than recorded.
    vault.files["A.md"] = "# A\nrestored";
    vault.mtimes["A.md"] = 1500;
    const indexer2 = new VaultIndexer(vault, config);
    indexer2.attachSession(session);
    indexer2.restoreFromMeta(indexer.getPathChunkCounts(), indexer.getPathMtimes());
    const { upserted } = await indexer2.reconcile();
    expect(upserted).toBe(1);
    expect(session.docs.get("A.md#chunk-0")?.text).toContain("restored");
  });

  it("queues vault events that arrive during a rebuild and applies them after", async () => {
    const files: Record<string, string> = {};
    for (let i = 0; i < 30; i++) files[`n${i}.md`] = `# H${i}\nbody`;
    const vault = makeVault(files);
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    let injected = false;
    indexer.onStatus((status) => {
      if (!injected && status.state === "indexing" && status.processed === 5) {
        injected = true;
        // Simulate an edit + a new note landing mid-rebuild.
        vault.files["n1.md"] = "# H1\nedited\n## More\nbody";
        vault.files["fresh.md"] = "# Fresh";
        void indexer.upsertPath("n1.md");
        void indexer.upsertPath("fresh.md");
      }
    });
    await indexer.rebuild();
    // Drained after rebuild: the edit and the new note are both in the index.
    expect(indexer.getPathChunkCounts()["n1.md"]).toBe(2);
    expect(session.docs.has("fresh.md#chunk-0")).toBe(true);
  });

  it("renameFolder re-keys every indexed note under the folder", async () => {
    const vault = makeVault({
      "Projects/A.md": "# A\nbody",
      "Projects/sub/B.md": "# B\nbody",
      "Other.md": "# O",
    });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.rebuild();

    // Obsidian renames the folder; note paths move with it.
    vault.files["Archive/A.md"] = vault.files["Projects/A.md"];
    vault.files["Archive/sub/B.md"] = vault.files["Projects/sub/B.md"];
    delete vault.files["Projects/A.md"];
    delete vault.files["Projects/sub/B.md"];

    await indexer.renameFolder("Projects", "Archive");

    expect(Object.keys(indexer.getPathChunkCounts()).sort()).toEqual([
      "Archive/A.md",
      "Archive/sub/B.md",
      "Other.md",
    ]);
    expect([...session.docs.keys()].some((k) => k.startsWith("Projects/"))).toBe(false);
    expect(session.docs.has("Archive/sub/B.md#chunk-0")).toBe(true);
  });

  it("removeFolder drops every indexed note under the folder", async () => {
    const vault = makeVault({ "Projects/A.md": "# A", "Projects/sub/B.md": "# B", "Other.md": "# O" });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.rebuild();

    delete vault.files["Projects/A.md"];
    delete vault.files["Projects/sub/B.md"];
    await indexer.removeFolder("Projects");

    expect(Object.keys(indexer.getPathChunkCounts())).toEqual(["Other.md"]);
    expect([...session.docs.keys()]).toEqual(["Other.md#chunk-0"]);
  });

  it("folder operations don't touch a sibling with a shared name prefix", async () => {
    const vault = makeVault({ "Notes/A.md": "# A", "NotesArchive/B.md": "# B" });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.rebuild();

    delete vault.files["Notes/A.md"];
    await indexer.removeFolder("Notes");

    expect(Object.keys(indexer.getPathChunkCounts())).toEqual(["NotesArchive/B.md"]);
  });

  it("reconcile is a no-op when nothing changed", async () => {
    const vault = makeVault({ "A.md": "# A" }, { "A.md": 1000 });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    await indexer.rebuild();
    const callsBefore = session.calls.length;
    const indexer2 = new VaultIndexer(vault, config);
    indexer2.attachSession(session);
    indexer2.restoreFromMeta(indexer.getPathChunkCounts(), indexer.getPathMtimes());
    const result = await indexer2.reconcile();
    expect(result).toEqual({ upserted: 0, removed: 0 });
    expect(session.calls.length).toBe(callsBefore);
  });

  it("restoreFromMeta re-enables watching with the persisted counts", async () => {
    const vault = makeVault({ "A.md": "# One\n## Two" });
    const session = new FakeSession();
    const indexer = new VaultIndexer(vault, config);
    indexer.attachSession(session);
    indexer.restoreFromMeta({ "A.md": 2, "Gone.md": 0 });
    expect(indexer.getStatus()).toEqual({ state: "ready", files: 1, chunks: 2 });
    await indexer.upsertPath("A.md");
    expect(session.docCount).toBe(2);
  });
});
