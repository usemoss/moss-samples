import { NextResponse } from "next/server";
import { configValue } from "@/lib/runtime-config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const { text } = (await request.json()) as { text?: string };
    const apiKey = configValue("elevenLabsApiKey", "ELEVENLABS_API_KEY");
    const voiceId = configValue("elevenLabsVoiceId", "ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb");
    const modelId = configValue("elevenLabsModelId", "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2");

    if (!apiKey) return NextResponse.json({ error: "ElevenLabs is not configured." }, { status: 503 });
    if (!text?.trim()) return NextResponse.json({ error: "Missing text." }, { status: 400 });

    const response = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(voiceId)}?output_format=mp3_44100_128`,
      {
        method: "POST",
        headers: {
          accept: "audio/mpeg",
          "content-type": "application/json",
          "xi-api-key": apiKey,
        },
        body: JSON.stringify({
          text: text.slice(0, 2400),
          model_id: modelId,
          voice_settings: { stability: 0.48, similarity_boost: 0.78, style: 0.16, use_speaker_boost: true },
        }),
      },
    );

    if (!response.ok) {
      console.error("ElevenLabs request failed", response.status, await response.text());
      return NextResponse.json({ error: `ElevenLabs returned ${response.status}.` }, { status: 502 });
    }

    return new Response(await response.arrayBuffer(), {
      headers: { "content-type": "audio/mpeg", "cache-control": "no-store" },
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
