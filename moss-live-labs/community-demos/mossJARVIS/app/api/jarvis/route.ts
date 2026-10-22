import { NextResponse } from "next/server";
import {
  addWorkingTurn,
  brainStats,
  buildBrainGraph,
  createJarvisSession,
  deleteBrainMemory,
  openTasks,
  persistTurn,
  queryBoth,
  relatedBrainMemories,
  rememberInBrain,
  searchBrain,
  type JarvisTask,
  type RetrievedMemory,
} from "@/lib/jarvis-store";
import { configStatus, configValue, setRuntimeConfig, type RuntimeConfig } from "@/lib/runtime-config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type LlmTurn = {
  response: string;
  facts: string[];
  tasks: JarvisTask[];
};

function cleanJson(text: string) {
  const cleaned = text.trim().replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  return start >= 0 && end > start ? cleaned.slice(start, end + 1) : cleaned;
}

async function callOpenRouter(messages: Array<{ role: "system" | "user"; content: string }>) {
  const apiKey = configValue("openRouterApiKey", "OPENROUTER_API_KEY");
  const model = configValue("openRouterModel", "OPENROUTER_MODEL", "openai/gpt-4.1-mini");
  if (!apiKey) throw new Error("OpenRouter is offline. Add OPENROUTER_API_KEY to .env.local.");

  const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${apiKey}`,
      "HTTP-Referer": configValue("appUrl", "APP_URL", "http://localhost:3000"),
      "X-Title": "Jarvis Second Brain",
    },
    body: JSON.stringify({
      model,
      max_tokens: 650,
      messages,
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    console.error("OpenRouter request failed", response.status, detail);
    let message = detail;
    try {
      const parsed = JSON.parse(detail) as { error?: { message?: string } };
      message = parsed.error?.message || detail;
    } catch {
      // Keep the provider's plain-text error when it is not JSON.
    }
    throw new Error(`OpenRouter ${response.status}: ${message.slice(0, 240)}`);
  }
  const data = await response.json();
  const content = data?.choices?.[0]?.message?.content;
  if (typeof content !== "string") throw new Error("OpenRouter returned an invalid response.");
  return content;
}

function memoryText(memories: RetrievedMemory[]) {
  return memories.map((item) => `[${item.source}:${item.id}] ${item.text}`).join("\n") || "None";
}

async function answerTurn(
  text: string,
  working: RetrievedMemory[],
  longTerm: RetrievedMemory[],
): Promise<LlmTurn> {
  const today = new Date().toISOString();
  const raw = await callOpenRouter([
    {
      role: "system",
      content: `You are Jarvis, a precise, calm personal AI assistant with a subtle British manner. Be useful and concise when spoken aloud. Never mention retrieval internals unless asked.

Today is ${today}. Extract durable user facts and requested reminders/tasks. Resolve relative due dates to an ISO date/time when reasonably possible. Return JSON only:
{"response":"spoken answer","facts":["durable fact"],"tasks":[{"title":"task","due":"ISO date or empty","recurrence":"none or rule","priority":"low|normal|high"}]}
Do not create tasks unless the user actually requests one. Do not store transient questions as facts.`,
    },
    {
      role: "user",
      content: `Current request:\n${text}\n\nWorking memory:\n${memoryText(working)}\n\nLong-term second brain:\n${memoryText(longTerm)}`,
    },
  ]);

  try {
    const parsed = JSON.parse(cleanJson(raw)) as Partial<LlmTurn>;
    if (parsed.response && typeof parsed.response === "string") {
      return {
        response: parsed.response,
        facts: Array.isArray(parsed.facts) ? parsed.facts.filter((item): item is string => typeof item === "string") : [],
        tasks: Array.isArray(parsed.tasks)
          ? parsed.tasks.filter((item): item is JarvisTask => Boolean(item && typeof item.title === "string"))
          : [],
      };
    }
  } catch {
    // Models without JSON mode may answer in prose. Text chat should still work.
  }
  return {
    response: raw.trim(),
    facts: [],
    tasks: [],
  };
}

async function makeBriefing(tasks: Awaited<ReturnType<typeof openTasks>>) {
  if (tasks.length === 0) {
    return "Good morning. Your task matrix is clear. There are no open commitments in the second brain.";
  }
  const raw = await callOpenRouter([
    {
      role: "system",
      content:
        "You are Jarvis. Produce a crisp British-voiced morning briefing in under 90 words. Prioritise overdue, due-today, and high-priority items. Return JSON only: {\"briefing\":\"...\"}.",
    },
    { role: "user", content: `Current time: ${new Date().toISOString()}\nOpen tasks:\n${JSON.stringify(tasks)}` },
  ]);
  try {
    const parsed = JSON.parse(cleanJson(raw)) as { briefing?: string };
    if (parsed.briefing) return parsed.briefing;
  } catch {
    // Plain-text output is valid for models without JSON mode.
  }
  return raw.trim() || "Your briefing is ready, but the model returned no text.";
}

async function listOpenRouterModels() {
  const apiKey = configValue("openRouterApiKey", "OPENROUTER_API_KEY");
  if (!apiKey) return [];
  const response = await fetch("https://openrouter.ai/api/v1/models?output_modalities=text", {
    headers: { authorization: `Bearer ${apiKey}` },
    cache: "no-store",
  });
  if (!response.ok) return [];
  const data = (await response.json()) as {
    data?: Array<{ id?: string; name?: string; architecture?: { output_modalities?: string[] } }>;
  };
  return (data.data || [])
    .filter((model) => typeof model.id === "string" && model.architecture?.output_modalities?.includes("text"))
    .map((model) => ({ id: model.id as string, name: model.name || (model.id as string) }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function errorResponse(error: unknown, status = 500) {
  const message = error instanceof Error ? error.message : String(error);
  return NextResponse.json({ error: message }, { status });
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const action = typeof body.action === "string" ? body.action : "";

    if (body.config && typeof body.config === "object") {
      setRuntimeConfig(body.config as RuntimeConfig);
    }

    if (action === "status") {
      return NextResponse.json({ config: configStatus() });
    }

    if (action === "models") {
      return NextResponse.json({ models: await listOpenRouterModels() });
    }

    if (action === "init") {
      return NextResponse.json({ ...(await createJarvisSession()), config: configStatus() });
    }

    if (action === "chat") {
      const text = typeof body.text === "string" ? body.text.trim() : "";
      if (!text) return errorResponse(new Error("I didn't catch that."), 400);
      const result = await answerTurn(text, [], []);
      return NextResponse.json({
        ...result,
        memoryMs: 0,
        recalled: 0,
        persisted: { stored: 0, synced: false },
        memoryOnline: false,
        localMossReady: false,
        memoryError: "No memory session was available for this turn.",
      });
    }

    const sessionId = typeof body.sessionId === "string" ? body.sessionId : "";
    if (!sessionId) return errorResponse(new Error("Missing Jarvis session ID."), 400);

    if (action === "briefing") {
      const tasks = await openTasks(sessionId);
      return NextResponse.json({ briefing: await makeBriefing(tasks), tasks });
    }

    if (action === "brain-list" || action === "brain-search") {
      const text = typeof body.text === "string" ? body.text.trim() : "";
      const limit = typeof body.limit === "number" ? body.limit : 40;
      const recent = body.recent === true;
      const type = typeof body.type === "string" ? body.type : "all";
      const source = typeof body.source === "string" ? body.source : undefined;
      return NextResponse.json(await searchBrain(sessionId, text, { limit, recent, type, source }));
    }

    if (action === "brain-related") {
      const memoryId = typeof body.memoryId === "string" ? body.memoryId : "";
      if (!memoryId) return errorResponse(new Error("Missing memory ID."), 400);
      return NextResponse.json(await relatedBrainMemories(sessionId, memoryId));
    }

    if (action === "brain-remember") {
      const text = typeof body.text === "string" ? body.text.trim() : "";
      if (!text) return errorResponse(new Error("Enter something worth remembering."), 400);
      const title = typeof body.title === "string" ? body.title : undefined;
      const tags = Array.isArray(body.tags) ? body.tags.filter((tag): tag is string => typeof tag === "string") : [];
      return NextResponse.json(await rememberInBrain(sessionId, text, { title, tags }));
    }

    if (action === "brain-stats") {
      return NextResponse.json(await brainStats(sessionId));
    }

    if (action === "brain-graph") {
      return NextResponse.json(await buildBrainGraph(sessionId));
    }

    if (action === "brain-delete") {
      const memoryId = typeof body.memoryId === "string" ? body.memoryId : "";
      if (!memoryId) return errorResponse(new Error("Missing memory ID."), 400);
      return NextResponse.json(await deleteBrainMemory(sessionId, memoryId));
    }

    if (action === "memory-search") {
      const text = typeof body.text === "string" ? body.text.trim() : "";
      if (!text) return errorResponse(new Error("Missing memory search text."), 400);
      const memory = await queryBoth(sessionId, text, 5);
      return NextResponse.json(memory);
    }

    if (action === "turn") {
      const text = typeof body.text === "string" ? body.text.trim() : "";
      if (!text) return errorResponse(new Error("I didn't catch that."), 400);

      await addWorkingTurn(sessionId, "user", text);
      const memory = await queryBoth(sessionId, text, 5);
      const result = await answerTurn(text, memory.working, memory.longTerm);
      await addWorkingTurn(sessionId, "assistant", result.response);
      const persisted = await persistTurn(sessionId, text, result.response, result.facts, result.tasks);

      return NextResponse.json({
        ...result,
        memoryMs: memory.elapsedMs,
        recalled: memory.working.length + memory.longTerm.length,
        persisted,
        memoryDocs: persisted.stored,
        memoryOnline: persisted.synced,
        localMossReady: persisted.localMossReady,
        memoryError: persisted.error || memory.memoryError,
      });
    }

    return errorResponse(new Error("Unknown Jarvis action."), 400);
  } catch (error) {
    console.error("Jarvis API error", error);
    return errorResponse(error);
  }
}
