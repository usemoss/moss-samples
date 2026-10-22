export type Doc = {
  id?: string;
  text: string;
  score: number;
};

export type RetrievalPayload = {
  query: string;
  catalog: Doc[]; // pre-loaded cloud index
  session: Doc[]; // live session (this call)
  catalog_ms: number;
  session_ms: number;
};
