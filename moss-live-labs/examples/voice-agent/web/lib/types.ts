export type RetrievalDoc = {
  /** Moss may omit an id or emit JSON null for documents without one. */
  id?: string | null;
  text: string;
  score: number;
};

export type RetrievalPayload = {
  query: string;
  docs: RetrievalDoc[];
  took_ms: number;
  /** Region used for the Moss filter on this turn (required). */
  region: string;
};
