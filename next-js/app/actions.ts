'use server'

import { MossClient } from "@inferedge/moss";

/**
 * Server Action to perform semantic search using Moss SDK.
 * This runs securely on the server, keeping your API keys protected.
 */
export async function searchMoss(query: string) {
  const projectId = process.env.MOSS_PROJECT_ID;
  const projectKey = process.env.MOSS_PROJECT_KEY;
  const indexName = process.env.MOSS_INDEX_NAME;

  if (!projectId || !projectKey || !indexName) {
    throw new Error("Missing Moss credentials in environment variables.");
  }

  const client = new MossClient(projectId, projectKey);

  try {
    // 1. Ensure index is loaded
    await client.loadIndex(indexName);

    // 2. Perform semantic search
    const results = await client.query(indexName, query, { topK: 5 });

    // 3. Return results to the client
    return {
      success: true,
      docs: results.docs.map(doc => ({
        id: doc.id,
        text: doc.text,
        score: doc.score,
        metadata: doc.metadata
      })),
      timeTaken: results.timeTakenInMs
    };
  } catch (error) {
    console.error("Moss Search Error:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "An unknown error occurred"
    };
  }
}
