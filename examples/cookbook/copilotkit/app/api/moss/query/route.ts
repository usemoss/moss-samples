import { NextResponse } from "next/server";
import { MossClient } from "@moss-dev/moss";

// Retrieve environment variables
const projectId = process.env.MOSS_PROJECT_ID;
const projectKey = process.env.MOSS_PROJECT_KEY;

// Mock database for testing without API keys out-of-the-box
const MOCK_DOCUMENTS = [
  {
    id: "refund-policy",
    text: "Refund Policy: Customers can return any unused item in its original packaging within 30 days of purchase for a full refund. Return shipping costs are covered by the customer, and original shipping fees are non-refundable. Refunds are processed within 5-7 business days.",
    metadata: { category: "policy" }
  },
  {
    id: "shipping-options",
    text: "Shipping Options: We offer Standard Shipping (3-5 business days) for $5.99 (free on orders over $50) and Express Shipping (1-2 business days) for $14.99. We currently only ship within North America.",
    metadata: { category: "shipping" }
  },
  {
    id: "office-hours-location",
    text: "Office Info: Our corporate headquarters is located at 123 Innovation Way, Suite 400, San Francisco, CA 94107. We are open Monday through Friday, 9:00 AM to 6:00 PM PST. The office is closed on major US holidays.",
    metadata: { category: "info" }
  },
  {
    id: "support-contact",
    text: "Contact Support: Customer support is available 24/7. You can email us at support@usemoss.dev, call us toll-free at 1-800-555-0199, or open a live chat on our website during normal business hours.",
    metadata: { category: "contact" }
  },
  {
    id: "what-is-moss",
    text: "Moss is a real-time semantic search runtime for AI agents targeting sub-10ms query latency. It runs on-device using bundled embedding models, requiring no external API calls for local queries. The cloud layer handles project management and index distribution.",
    metadata: { category: "moss-info" }
  }
];

let mossClient: MossClient | null = null;
const isMockMode = !projectId || !projectKey || projectId === "your_moss_project_id" || projectKey === "your_moss_project_key";

if (!isMockMode) {
  try {
    mossClient = new MossClient(projectId!, projectKey!);
    console.log("MossClient successfully initialized on server.");
  } catch (error) {
    console.error("Failed to initialize MossClient:", error);
  }
} else {
  console.warn("Moss credentials not configured or set to placeholder values. Running in MOCK mode.");
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const query = (searchParams.get("query") ?? "").trim();
    const indexName = searchParams.get("indexName") || process.env.MOSS_INDEX_NAME;
    const topKRaw = searchParams.get("topK");
    const parsedTopK = Number.parseInt(topKRaw ?? "3", 10);
    const topK = Number.isFinite(parsedTopK)
      ? Math.min(Math.max(parsedTopK, 1), 20)
      : 3;

    if (!query) {
      return NextResponse.json({ error: "Missing query parameter" }, { status: 400 });
    }

    // MOCK MODE FALLBACK
    if (isMockMode || !mossClient) {
      console.log(`[MOCK MODE] Searching (topK=${topK})`);
      
      // Perform a simple case-insensitive keyword match score simulation
      const queryWords = query.toLowerCase().split(/\s+/);
      const results = MOCK_DOCUMENTS.map(doc => {
        let matches = 0;
        const textLower = doc.text.toLowerCase();
        
        queryWords.forEach(word => {
          if (word.length > 2 && textLower.includes(word)) {
            matches++;
          }
        });
        
        // Calculate a simulated score
        const score = matches > 0 ? 0.3 + (matches * 0.15) : 0.05;
        
        return {
          id: doc.id,
          text: doc.text,
          score: Math.min(score, 0.99),
          metadata: doc.metadata
        };
      })
      .filter(doc => doc.score > 0.1) // Only return matches above threshold
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);

      return NextResponse.json({
        docs: results,
        mode: "mock",
        warning: isMockMode
          ? "Running in mock mode. Add MOSS_PROJECT_ID and MOSS_PROJECT_KEY to your environment variables to query real indexes."
          : "Moss credentials were provided, but MossClient failed to initialize. Check server logs and native bindings."
      });
    }

    // REAL MOSS QUERY
    if (!indexName || indexName === "your_moss_index_name") {
      return NextResponse.json({
        error: "Moss index name is not configured. Please set MOSS_INDEX_NAME in your environment."
      }, { status: 400 });
    }

    console.log(`[REAL MODE] Querying Moss index "${indexName}" (topK=${topK})`);
    const results = await mossClient.query(indexName, query, { topK });

    return NextResponse.json({
      docs: results.docs.map(doc => ({
        id: doc.id,
        text: doc.text,
        score: doc.score,
        metadata: doc.metadata,
      })),
      timeTakenInMs: results.timeTakenInMs,
      mode: "real"
    });

  } catch (error: any) {
    console.error("API route query error:", error);
    return NextResponse.json({
      error: error.message || "Internal server error occurred while querying knowledge base."
    }, { status: 500 });
  }
}
