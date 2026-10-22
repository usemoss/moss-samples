import { NextResponse } from "next/server";
import { getRun } from "../../../../lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const run = getRun(id);
  return run
    ? NextResponse.json(run)
    : NextResponse.json({ error: "Run not found." }, { status: 404 });
}
