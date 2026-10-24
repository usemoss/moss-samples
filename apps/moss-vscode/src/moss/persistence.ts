import type { DocumentInfo } from "@moss-dev/moss";
import * as fs from "node:fs";
import * as fsp from "node:fs/promises";
import * as path from "node:path";
import * as vscode from "vscode";
import { workspaceSessionName } from "./config";

export interface IndexMeta {
  workspaceRoot: string;
  sessionName: string;
  files: number;
  chunks: number;
  pathChunkCounts: Record<string, number>;
  savedAt: string;
  cloudPushedAt?: string;
}

export function pathChunkCountsFromDocs(docs: DocumentInfo[]): Record<string, number> {
  const counts = new Map<string, number>();
  for (const doc of docs) {
    const metadata = doc.metadata as Record<string, string> | undefined;
    const filePath = metadata?.filePath;
    if (filePath) {
      counts.set(filePath, (counts.get(filePath) ?? 0) + 1);
    }
  }
  return Object.fromEntries(counts);
}

export function workspaceRootPath(): string {
  return (
    vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ??
    vscode.workspace.name ??
    "default-workspace"
  );
}

export function workspaceHash(): string {
  const name = workspaceSessionName();
  return name.startsWith("vscode-") ? name.slice("vscode-".length) : name;
}

export function indexCacheDir(context: vscode.ExtensionContext): string {
  return path.join(context.globalStorageUri.fsPath, "indexes", workspaceHash());
}

export function indexMetaPath(context: vscode.ExtensionContext): string {
  return path.join(indexCacheDir(context), "meta.json");
}

export function indexCacheExists(context: vscode.ExtensionContext): boolean {
  return fs.existsSync(indexMetaPath(context));
}

export async function ensureIndexCacheDir(
  context: vscode.ExtensionContext,
): Promise<string> {
  const dir = indexCacheDir(context);
  await fsp.mkdir(dir, { recursive: true });
  return dir;
}

export async function readIndexMeta(
  context: vscode.ExtensionContext,
): Promise<IndexMeta | undefined> {
  const metaPath = indexMetaPath(context);
  try {
    const raw = await fsp.readFile(metaPath, "utf8");
    const parsed = JSON.parse(raw) as IndexMeta;
    if (
      !parsed ||
      typeof parsed.workspaceRoot !== "string" ||
      typeof parsed.sessionName !== "string" ||
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

export async function writeIndexMeta(
  context: vscode.ExtensionContext,
  meta: IndexMeta,
): Promise<void> {
  const dir = await ensureIndexCacheDir(context);
  const metaPath = path.join(dir, "meta.json");
  await fsp.writeFile(metaPath, JSON.stringify(meta, null, 2), "utf8");
}

export async function clearIndexCache(
  context: vscode.ExtensionContext,
): Promise<void> {
  const dir = indexCacheDir(context);
  // Deliberately not swallowed. This is the only durable step stopping the next
  // activation from restoring metadata for documents a rebuild already deleted,
  // so a caller has to be able to tell that it failed.
  await fsp.rm(dir, { recursive: true, force: true });
}
