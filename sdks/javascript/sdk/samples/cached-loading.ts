/**
 * Moss SDK - Cached Index Loading Sample
 *
 * Demonstrates using the `cachePath` option to persist downloaded indexes to disk.
 * On the first run, the index is fetched from the cloud and saved locally.
 * On subsequent runs, the index loads instantly from the local cache.
 *
 * You can also combine caching with auto-refresh for long-running processes:
 *   await client.loadIndex(indexName, {
 *     cachePath: CACHE_DIR,
 *     autoRefresh: true,
 *     pollingIntervalInSeconds: 60,
 *   });
 *
 * Required Environment Variables:
 * - MOSS_TEST_PROJECT_ID: Your Moss project ID
 * - MOSS_TEST_PROJECT_KEY: Your Moss project key
 *
 * @example
 * ```bash
 * npx tsx cached-loading.ts
 * ```
 */

import { MossClient } from "../src";
import { performance } from "node:perf_hooks";
import { config } from "dotenv";

config();

const CACHE_DIR = "./.moss-cache";

async function cachedLoadSample(): Promise<void> {
  console.log("Moss SDK - Cached Index Loading Sample");
  console.log("=".repeat(45));

  const projectId = process.env.MOSS_TEST_PROJECT_ID;
  const projectKey = process.env.MOSS_TEST_PROJECT_KEY;
  const indexName = process.env.MOSS_INDEX_NAME;
  if (!projectId || !projectKey || !indexName) {
    console.error(
      "Error: Please set MOSS_TEST_PROJECT_ID, MOSS_TEST_PROJECT_KEY, and MOSS_INDEX_NAME in .env"
    );
    return;
  }

  const client = new MossClient(projectId, projectKey);

  try {
    console.log(`\nLoading index '${indexName}' (cache dir: ${CACHE_DIR})...`);
    const start = performance.now();
    await client.loadIndex(indexName, { cachePath: CACHE_DIR });
    const loadMs = (performance.now() - start).toFixed(0);
    console.log(`Index loaded in ${loadMs}ms`);

    // Run a few queries to verify the loaded index works
    const queries = [
      "how to return damaged item",
      "return shipping label process",
      "refund processing time and policy",
    ];

    console.log("\nRunning sample queries...");
    for (const query of queries) {
      const results = await client.query(indexName, query, { topK: 3 });
      console.log(
        `\n  "${query}" -> ${results.docs.length} results (${results.timeTakenInMs}ms)`
      );
      results.docs.forEach((doc, i) => {
        const preview =
          doc.text.length > 80 ? doc.text.substring(0, 80) + "..." : doc.text;
        console.log(`    ${i + 1}. [${doc.id}] score=${doc.score.toFixed(3)}`);
        console.log(`       ${preview}`);
      });
    }

    console.log("\nDone! Run again to see the faster cached load time.");
  } finally {
    await client.close();
  }
}

// Export for use in tests or other modules
export { cachedLoadSample };

// Run the sample
cachedLoadSample().catch(console.error);
