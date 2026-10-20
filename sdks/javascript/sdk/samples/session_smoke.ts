/**
 * Smoke test for `client.session(...)`.
 *
 * Uses `modelId="custom"` so document `addDocs` / `query` / `deleteDocs`
 * stay in-process — no cloud round trip. The only network call is the
 * credential validation that `SessionIndex` performs at construction
 * (so real creds in `MOSS_TEST_PROJECT_ID` / `MOSS_TEST_PROJECT_KEY` are required).
 *
 * Run:
 *   npx tsx samples/session_smoke.ts
 */

import { config } from "dotenv";

import { MossClient, type DocumentInfo, type SessionIndex } from "../src";

// SessionIndex's constructor validates credentials against the cloud,
// so even an in-process smoke test needs real creds from .env.
config();

async function main(): Promise<void> {
  const projectId = process.env.MOSS_TEST_PROJECT_ID;
  const projectKey = process.env.MOSS_TEST_PROJECT_KEY;
  if (!projectId || !projectKey) {
    throw new Error(
      "MOSS_TEST_PROJECT_ID / MOSS_TEST_PROJECT_KEY not set. Check .env",
    );
  }

  const client = new MossClient(projectId, projectKey);
  let session: SessionIndex | undefined;

  try {
    session = await client.session("smoke-session", "custom");
    console.log(`Created session: name=${session.name}, modelId=${session.modelId}`);

    const docs: DocumentInfo[] = [
      {
        id: "a",
        text: "Machine learning models",
        metadata: { topic: "ml" },
        embedding: [1, 0, 0],
      },
      {
        id: "b",
        text: "Cloud infrastructure",
        metadata: { topic: "infra" },
        embedding: [0, 1, 0],
      },
      {
        id: "c",
        text: "Neural networks",
        metadata: { topic: "ml" },
        embedding: [0.9, 0.1, 0],
      },
    ];

    const addResult = await session.addDocs(docs);
    console.log(
      `addDocs: added=${addResult.added}, updated=${addResult.updated}, docCount=${session.docCount}`,
    );
    if (addResult.added !== 3 || session.docCount !== 3) {
      throw new Error("expected 3 docs added");
    }

    // Custom-embedding query: "show me ML stuff" with embedding ~ [1, 0, 0]
    const result = await session.query("ML stuff", {
      topK: 2,
      embedding: [1, 0, 0],
    });
    console.log(
      `query: query="${result.query}", count=${result.docs.length}, top=[${result.docs
        .map((d) => `${d.id}:${d.score.toFixed(3)}`)
        .join(", ")}]`,
    );
    if (result.docs.length !== 2) {
      throw new Error(`expected 2 results, got ${result.docs.length}`);
    }
    if (result.docs[0].id !== "a") {
      throw new Error(`expected top doc to be 'a', got '${result.docs[0].id}'`);
    }

    const deleted = await session.deleteDocs(["b"]);
    console.log(`deleteDocs: removed=${deleted}, docCount=${session.docCount}`);
    if (deleted !== 1 || session.docCount !== 2) {
      throw new Error("expected b to be removed");
    }

    // Custom-embedding session should reject queryText
    try {
      await session.query("anything"); // no embedding supplied
      throw new Error("expected query() without embedding to throw on custom");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (!message.includes("custom embeddings")) {
        throw new Error(`unexpected error message: ${message}`);
      }
      console.log(`custom-without-embedding correctly rejected: ${message}`);
    }

    console.log("✓ session smoke test passed");
  } finally {
    await session?.close();
    await client.close();
  }
}

main().catch((err) => {
  console.error("✗ smoke test failed:", err);
  process.exit(1);
});
