export type RetrievalDoc = {
  id?: string;
  text: string;
  score: number;
};

export type RetrievalPayload = {
  query: string;
  docs: RetrievalDoc[];
  took_ms: number;
  region?: string;
};
