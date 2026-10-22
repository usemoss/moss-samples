import { NextResponse } from "next/server";
import { chunkBrainSource, sourceFromFile, sourceFromUrl, type BrainSource } from "@/lib/brain-ingest";
import { ingestBrainChunks } from "@/lib/jarvis-store";
import { setRuntimeConfig, type RuntimeConfig } from "@/lib/runtime-config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_BATCH_BYTES = 60 * 1024 * 1024;

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export async function POST(request: Request) {
  try {
    const form = await request.formData();
    const sessionId = String(form.get("sessionId") || "");
    if (!sessionId) return NextResponse.json({ error: "Missing Jarvis session ID." }, { status: 400 });

    const configText = String(form.get("config") || "");
    if (configText) setRuntimeConfig(JSON.parse(configText) as RuntimeConfig);

    const sources: BrainSource[] = [];
    const errors: string[] = [];
    const urls = form.getAll("url").map(String).map((url) => url.trim()).filter(Boolean).slice(0, 12);
    for (const url of urls) {
      try {
        sources.push(await sourceFromUrl(url));
      } catch (error) {
        errors.push(`${url}: ${errorMessage(error)}`);
      }
    }

    const files = form.getAll("file").filter((item): item is File => item instanceof File && item.size > 0);
    const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
    if (totalBytes > MAX_BATCH_BYTES) return NextResponse.json({ error: "That import is larger than the 60 MB batch limit." }, { status: 413 });
    for (const file of files.slice(0, 80)) {
      if (file.size > MAX_FILE_BYTES) {
        errors.push(`${file.name}: larger than the 25 MB per-file limit.`);
        continue;
      }
      try {
        sources.push(...await sourceFromFile(file));
      } catch (error) {
        errors.push(`${file.name}: ${errorMessage(error)}`);
      }
    }

    if (!sources.length) {
      return NextResponse.json({ error: errors[0] || "Choose files or enter a public link to ingest." }, { status: 400 });
    }
    const importedAt = new Date().toISOString();
    const chunks = sources.flatMap((source) => chunkBrainSource(source, importedAt));
    const result = await ingestBrainChunks(sessionId, chunks);
    return NextResponse.json({
      ...result,
      sources: sources.length,
      chunks: chunks.length,
      errors,
      imported: sources.map((source) => ({ source: source.source, title: source.title, kind: source.kind })),
    });
  } catch (error) {
    console.error("Jarvis brain ingest error", error);
    return NextResponse.json({ error: errorMessage(error) }, { status: 500 });
  }
}
