/**
 * Decides which vault paths are indexed. Pure — no Obsidian imports — so it
 * is unit-testable.
 *
 * Paths are vault-relative with `/` separators, as Obsidian reports them.
 */

/** Folders never indexed regardless of user settings. */
const HARD_SKIP_SEGMENTS = new Set([".obsidian", ".trash", ".git", "node_modules"]);

export function normalizeVaultPath(p: string): string {
  return p.replace(/\\/g, "/").replace(/^\.?\//, "").replace(/\/+$/, "");
}

/**
 * Parse the user's "excluded folders" setting: one entry per line, blank lines
 * and `#` comments ignored, trailing slashes dropped.
 */
export function parseExcludedFolders(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map(normalizeVaultPath)
    .filter(Boolean);
}

/**
 * Case-insensitive: vault filesystems (macOS, Windows) usually are, and a
 * user typing `templates` expects it to cover `Templates/`.
 */
export function isExcludedFromIndex(relativePath: string, excludedFolders: string[]): boolean {
  const normalized = normalizeVaultPath(relativePath);
  if (!normalized) {
    return true;
  }
  const lower = normalized.toLowerCase();
  const segments = lower.split("/");
  if (segments.some((s) => HARD_SKIP_SEGMENTS.has(s))) {
    return true;
  }
  for (const folder of excludedFolders) {
    const f = folder.toLowerCase();
    if (lower === f || lower.startsWith(`${f}/`)) {
      return true;
    }
  }
  return false;
}

export function isMarkdownPath(relativePath: string): boolean {
  return /\.md$/i.test(relativePath);
}
