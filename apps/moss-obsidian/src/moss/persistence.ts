import * as crypto from "crypto";
import * as fs from "fs";
import * as fsp from "fs/promises";
import * as path from "path";
import type { DocumentInfo } from "@moss-dev/moss";

export interface IndexMeta {
  vaultPath: string;
  sessionName: string;
  model: string;
  files: number;
  chunks: number;
  pathChunkCounts: Record<string, number>;
  /** Modification time (ms) of each note when it was indexed. */
  pathMtimes?: Record<string, number>;
  /** Chunk size the index was built with; a mismatch invalidates the cache. */
  maxCharsPerChunk?: number;
  savedAt: string;
  cloudPushedAt?: string;
}

/**
 * Stable session / cloud index name: `obsidian-<sha256(vaultId)[:12]>`.
 * `vaultId` is a random UUID generated once per vault and stored in the
 * plugin's settings (`data.json`), so two unrelated vaults that happen to
 * share a display name can never collide on one cloud index, while a vault
 * synced across devices (with its `.obsidian` folder) keeps one identity.
 */
export function vaultSessionName(vaultId: string): string {
  const hash = crypto.createHash("sha256").update(vaultId).digest("hex").slice(0, 12);
  return `obsidian-${hash}`;
}

export function generateVaultId(): string {
  return crypto.randomUUID();
}

export function pathChunkCountsFromDocs(docs: DocumentInfo[]): Record<string, number> {
  const counts = new Map<string, number>();
  for (const doc of docs) {
    const filePath = doc.metadata?.filePath;
    if (filePath) {
      counts.set(filePath, (counts.get(filePath) ?? 0) + 1);
    }
  }
  return Object.fromEntries(counts);
}

export class IndexCache {
  /** Serializes meta writes so overlapping persists can't clobber each other. */
  private writeChain: Promise<void> = Promise.resolve();

  constructor(private readonly cacheDir: string) {}

  get dir(): string {
    return this.cacheDir;
  }

  get metaPath(): string {
    return path.join(this.cacheDir, "meta.json");
  }

  exists(): boolean {
    return fs.existsSync(this.metaPath);
  }

  async ensureDir(): Promise<string> {
    await fsp.mkdir(this.cacheDir, { recursive: true });
    return this.cacheDir;
  }

  async readMeta(): Promise<IndexMeta | undefined> {
    try {
      const raw = await fsp.readFile(this.metaPath, "utf8");
      const parsed = JSON.parse(raw) as IndexMeta;
      if (
        !parsed ||
        typeof parsed.vaultPath !== "string" ||
        typeof parsed.sessionName !== "string" ||
        typeof parsed.model !== "string" ||
        parsed.model.length === 0 ||
        typeof parsed.pathChunkCounts !== "object" ||
        parsed.pathChunkCounts === null
      ) {
        return undefined;
      }
      return parsed;
    } catch {
      return undefined;
    }
  }

  writeMeta(meta: IndexMeta): Promise<void> {
    const run = this.writeChain.then(async () => {
      await this.ensureDir();
      const tmp = `${this.metaPath}.${process.pid}.${Date.now()}.${Math.floor(Math.random() * 1e6)}.tmp`;
      await fsp.writeFile(tmp, JSON.stringify(meta, null, 2), "utf8");
      await fsp.rename(tmp, this.metaPath);
    });
    this.writeChain = run.catch(() => undefined);
    return run;
  }

  async clear(): Promise<void> {
    try {
      await fsp.rm(this.cacheDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }
}
