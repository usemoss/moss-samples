import readline from "node:readline";
import { MossClient } from "@moss-dev/moss";

let client = null;
let session = null;

function normalizeDocs(result) {
  if (!result) return [];
  if (Array.isArray(result.docs)) return result.docs;
  if (Array.isArray(result.documents)) return result.documents;
  if (Array.isArray(result)) return result;
  return [];
}

async function handle(message) {
  if (message.action === "init") {
    client = new MossClient(message.projectId, message.projectKey);
    session = await client.session(message.sessionName || "study-session");
    return {
      backend: "moss-js",
      docCount: session.docCount ?? 0,
      sessionName: session.name ?? message.sessionName,
    };
  }

  if (!session) {
    throw new Error("Moss session has not been initialized.");
  }

  if (message.action === "query") {
    const result = await session.query(message.query || "", { topK: message.topK || 3 });
    return {
      docs: normalizeDocs(result).map((doc) => ({
        id: doc.id,
        score: doc.score,
        text: doc.text || "",
      })),
    };
  }

  if (message.action === "add_docs") {
    const result = await session.addDocs(message.docs || []);
    return result || { added: 0, updated: 0 };
  }

  if (message.action === "shutdown") {
    process.exit(0);
  }

  throw new Error(`Unknown action: ${message.action}`);
}

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

rl.on("line", async (line) => {
  let message;
  try {
    message = JSON.parse(line);
    const data = await handle(message);
    process.stdout.write(JSON.stringify({ id: message.id, ok: true, data }) + "\n");
  } catch (error) {
    process.stdout.write(
      JSON.stringify({
        id: message?.id ?? null,
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      }) + "\n",
    );
  }
});
