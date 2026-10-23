import { MossClient, type DocumentInfo } from "@moss-dev/moss";
import { randomUUID } from "node:crypto";
import { config } from "dotenv";

config();

type MetadataFilter = Record<string, unknown>;

interface MetadataFilterExample {
  operator: string;
  description: string;
  query: string;
  filter: MetadataFilter;
}

const documents: DocumentInfo[] = [
  {
    id: "shoe-nyc-001",
    text: "Breathable road running shoes for daily city training.",
    metadata: {
      category: "shoes",
      brand: "swiftfit",
      city: "new-york",
      location: "40.7580,-73.9855",
    },
  },
  {
    id: "shoe-denver-002",
    text: "Trail running shoes built for rocky mountain paths.",
    metadata: {
      category: "shoes",
      brand: "peakstride",
      city: "denver",
      location: "39.7392,-104.9903",
    },
  },
  {
    id: "bag-nyc-003",
    text: "Lightweight commuter backpack with a laptop sleeve.",
    metadata: {
      category: "bags",
      brand: "urbanpack",
      city: "new-york",
      location: "40.7505,-73.9934",
    },
  },
  {
    id: "bag-seattle-004",
    text: "Compact travel duffel with a separate shoe compartment.",
    metadata: {
      category: "bags",
      brand: "swiftfit",
      city: "seattle",
      location: "47.6205,-122.3493",
    },
  },
];

function requireEnv(name: string): string {
  const value = process.env[name]?.trim();

  if (!value) {
    throw new Error(
      `Missing ${name}. Add it to .env before running this example.`,
    );
  }

  return value;
}

export async function runMetadataFilterExample(
  example: MetadataFilterExample,
): Promise<void> {
  const projectId = requireEnv("MOSS_PROJECT_ID");
  const projectKey = requireEnv("MOSS_PROJECT_KEY");
  const indexName = `metadata-filter-${example.operator.slice(1)}-${randomUUID()}`;
  const client = new MossClient(projectId, projectKey);
  let cleanupNeeded = false;
  let operationError: unknown;
  let operationFailed = false;

  try {
    console.log(`Moss metadata filter example: ${example.operator}`);
    console.log(example.description);

    console.log(`\nCreating temporary index: ${indexName}`);
    cleanupNeeded = true;
    await client.createIndex(indexName, documents, { modelId: "moss-minilm" });

    console.log("Loading index locally for filtered query...");
    await client.loadIndex(indexName);

    console.log(`\nQuery: ${example.query}`);
    console.log(`Filter: ${JSON.stringify(example.filter)}`);

    const results = await client.query(indexName, example.query, {
      topK: 5,
      alpha: 0.5,
      filter: example.filter,
    });

    const timing =
      results.timeTakenInMs === undefined
        ? ""
        : ` in ${results.timeTakenInMs}ms`;
    console.log(`\nFound ${results.docs.length} result(s)${timing}:`);
    results.docs.forEach((doc, index) => {
      const preview =
        doc.text.length > 80 ? `${doc.text.slice(0, 80)}...` : doc.text;
      console.log(
        `${index + 1}. [${doc.id}] score=${doc.score.toFixed(3)} ${preview}`,
      );
      console.log(`   metadata=${JSON.stringify(doc.metadata ?? {})}`);
    });
  } catch (error) {
    operationError = error;
    operationFailed = true;
  }

  if (cleanupNeeded) {
    console.log(`\nDeleting temporary index: ${indexName}`);
    try {
      const deleted = await client.deleteIndex(indexName);
      if (!deleted) {
        throw new Error(`Moss did not delete temporary index: ${indexName}`);
      }
    } catch (cleanupError) {
      if (operationFailed) {
        console.warn(
          `Failed to delete temporary index: ${indexName}`,
          cleanupError,
        );
      } else {
        throw cleanupError;
      }
    }
  }

  if (operationFailed) {
    throw operationError;
  }
}
