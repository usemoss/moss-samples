import { NextResponse } from "next/server";
import { getStats } from "../../../lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json(getStats());
}
