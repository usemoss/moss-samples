import type { QueryResultDocumentInfo } from "@moss-dev/moss";

export interface SearchHit {
  id: string;
  score: number;
  /** Chunk body without the breadcrumb prefix line. */
  text: string;
  filePath: string;
  title: string;
  headingPath: string;
  heading: string;
  startLine: number;
  endLine: number;
}

function asNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

/** Map a raw Moss result document to a navigable hit. */
export function mapHit(doc: QueryResultDocumentInfo): SearchHit {
  const metadata = (doc.metadata ?? {}) as Record<string, unknown>;
  const filePath = asString(metadata.filePath, doc.id.split("#")[0] || doc.id);
  const headingPath = asString(metadata.headingPath);
  const rawText = doc.text ?? "";
  // The chunker prefixes the breadcrumb as the first line; strip it for display.
  const text =
    headingPath && rawText.startsWith(`${headingPath}\n`)
      ? rawText.slice(headingPath.length + 1)
      : rawText;
  return {
    id: doc.id,
    score: doc.score ?? 0,
    text,
    filePath,
    title: asString(metadata.title, filePath.replace(/\.md$/i, "")),
    headingPath,
    heading: asString(metadata.heading),
    startLine: asNumber(metadata.startLine, 1),
    endLine: asNumber(metadata.endLine, 1),
  };
}

/**
 * Collapse multiple chunks from the same note into its best-scoring one when
 * `perNote` is true. Rank order of first appearance is preserved; if a later
 * chunk of an already-seen note scores higher (unsorted input), it replaces
 * that note's entry in place.
 */
export function dedupeByNote(hits: SearchHit[], perNote: boolean): SearchHit[] {
  if (!perNote) {
    return hits;
  }
  const bestByNote = new Map<string, number>();
  const out: SearchHit[] = [];
  for (const hit of hits) {
    const index = bestByNote.get(hit.filePath);
    if (index === undefined) {
      bestByNote.set(hit.filePath, out.length);
      out.push(hit);
    } else if (hit.score > out[index].score) {
      out[index] = hit;
    }
  }
  return out;
}

/** Short single-line preview for the suggestion list. */
export function previewText(text: string, maxLen = 160): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  if (collapsed.length <= maxLen) {
    return collapsed;
  }
  return `${collapsed.slice(0, maxLen - 1).trimEnd()}…`;
}
