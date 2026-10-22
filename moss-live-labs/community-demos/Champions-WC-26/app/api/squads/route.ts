import { NextRequest, NextResponse } from "next/server";
import pool from "../../../data/draft-pool.json";
import { withCareerPrimeSquad } from "../../../lib/prime-ratings";
import type { HistoricSquad } from "../../../lib/types";

export const dynamic = "force-dynamic";

export function GET(request: NextRequest) {
  const used = new Set((request.nextUrl.searchParams.get("used") ?? "").split(",").filter(Boolean));
  const available = pool.filter((squad) => !used.has(squad.id));
  if (!available.length) return NextResponse.json({ error: "No unused squads remain." }, { status: 409 });
  const rawSquad = available[Math.floor(Math.random() * available.length)] as HistoricSquad;
  const squad = request.nextUrl.searchParams.get("ratingMode") === "prime" ? withCareerPrimeSquad(rawSquad) : rawSquad;
  return NextResponse.json(squad, { headers: { "cache-control": "no-store" } });
}
