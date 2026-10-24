import type { QueryResultDocumentInfo } from "@moss-dev/moss";
import type { LocalMossSession } from "../moss/client";
import { getSearchOptions } from "../moss/config";

export interface SearchHit {
  id: string;
  score: number;
  text: string;
  filePath: string;
  startLine: number;
  endLine: number;
  language?: string;
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

export function mapHit(doc: QueryResultDocumentInfo): SearchHit {
  const metadata = (doc.metadata ?? {}) as Record<string, unknown>;
  return {
    id: doc.id,
    score: doc.score ?? 0,
    text: doc.text ?? "",
    filePath: asString(metadata.filePath, doc.id.split("#")[0] ?? doc.id),
    startLine: asNumber(metadata.startLine, 1),
    endLine: asNumber(metadata.endLine, 1),
    language: asString(metadata.language) || undefined,
  };
}

export class SemanticSearch {
  constructor(
    private getSession: () => LocalMossSession | undefined,
    private canSearch: () => boolean,
  ) {}

  async query(text: string): Promise<SearchHit[]> {
    const trimmed = text.trim();
    if (!trimmed) {
      return [];
    }
    if (!this.canSearch()) {
      return [];
    }
    const session = this.getSession();
    if (!session) {
      return [];
    }
    const { topK, alpha } = getSearchOptions();
    const result = await session.query(trimmed, { topK, alpha });
    return (result.docs ?? []).map(mapHit);
  }
}

export function debounce<T extends (...args: any[]) => void>(
  fn: T,
  waitMs: number,
): (...args: Parameters<T>) => void {
  let timer: NodeJS.Timeout | undefined;
  return (...args: Parameters<T>) => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => fn(...args), waitMs);
  };
}
