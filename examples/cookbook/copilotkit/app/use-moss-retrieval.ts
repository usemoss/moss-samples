import { useCopilotAction } from "@copilotkit/react-core";

export interface MossRetrievalOptions {
  /**
   * Name of the Moss index to query.
   * If not specified, the backend will default to MOSS_INDEX_NAME env variable.
   */
  indexName?: string;
  /**
   * Custom description to guide the LLM when it should call this action.
   */
  description?: string;
  /**
   * Number of documents to retrieve. Defaults to 3.
   */
  topK?: number;
  /**
   * Callback fired when a search starts (useful for UI feedback).
   */
  onSearchStart?: (query: string) => void;
  /**
   * Callback fired when search finishes (returns results).
   */
  onSearchComplete?: (results: any) => void;
}

/**
 * useMossRetrieval hook
 *
 * Registers a client-side action in CopilotKit that allows the CopilotKit agent
 * to query the Moss semantic search index for relevant context.
 */
export function useMossRetrieval(options: MossRetrievalOptions = {}) {
  const {
    indexName,
    description,
    topK = 3,
    onSearchStart,
    onSearchComplete,
  } = options;

  useCopilotAction({
    name: "searchKnowledgeBase",
    description:
      description ||
      "Searches the internal knowledge base for documents matching the query. " +
      "Use this to answer questions that require company-specific knowledge, " +
      "policies, guides, or other stored documents.",
    parameters: [
      {
        name: "query",
        type: "string",
        description: "The search query to match against documents in the knowledge base.",
        required: true,
      },
    ],
    handler: async ({ query }: { query: string }) => {
      // --- THE MOSS <-> COPILOTKIT HANDOFF ---
      // 1. When the user asks a question, the CopilotKit chat agent analyzes the registered actions.
      // 2. If it needs internal knowledge to answer, it triggers this "searchKnowledgeBase" action.
      // 3. The handler executes in the browser (client-side), ensuring the user interface stays responsive.
      // 4. To keep our sensitive Moss API keys secure, the client calls our Next.js API route (`/api/moss/query`).
      // 5. The API route queries Moss Cloud and returns matching documents with confidence scores.
      // 6. The handler receives the results and returns them to CopilotKit.
      // 7. CopilotKit feeds these retrieved documents into the LLM context, allowing it to generate a grounded, accurate response.

      if (onSearchStart) {
        onSearchStart(query);
      }

      try {
        const url = new URL("/api/moss/query", window.location.origin);
        url.searchParams.append("query", query);
        if (indexName) {
          url.searchParams.append("indexName", indexName);
        }
        url.searchParams.append("topK", topK.toString());

        const response = await fetch(url.toString());
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Failed to query Moss: ${errorText}`);
        }

        const data = await response.json();

        if (onSearchComplete) {
          onSearchComplete(data);
        }

        // Return results to the CopilotKit agent
        return {
          success: true,
          query,
          documents: data.docs || [],
        };
      } catch (error: any) {
        console.error("useMossRetrieval failed:", error);
        return {
          success: false,
          error: error.message || "Unknown error during Moss retrieval",
          documents: [],
        };
      }
    },
  });
}
