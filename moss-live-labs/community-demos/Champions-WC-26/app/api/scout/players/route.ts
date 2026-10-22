import { NextRequest, NextResponse } from "next/server";
import { browseScoutPlayers } from "../../../../lib/scout-data";
import type { Position } from "../../../../lib/types";

export const dynamic = "force-dynamic";

const positions = new Set<Position>(["GK", "DEF", "MID", "FWD"]);
const sorts = new Set(["rating-desc", "year-desc", "year-asc", "name-asc"] as const);

export function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const perPage = Math.min(48, Math.max(12, Number.parseInt(params.get("perPage") ?? "24", 10) || 24));
  const rawPosition = params.get("position");
  const position = rawPosition && positions.has(rawPosition as Position) ? rawPosition as Position : undefined;
  const rawYear = Number.parseInt(params.get("year") ?? "", 10);
  const rawSort = params.get("sort");
  const sort = rawSort && sorts.has(rawSort as "rating-desc" | "year-desc" | "year-asc" | "name-asc")
    ? rawSort as "rating-desc" | "year-desc" | "year-asc" | "name-asc"
    : "rating-desc";

  const result = browseScoutPlayers({
    page,
    perPage,
    query: params.get("query") ?? undefined,
    position,
    nation: params.get("nation") ?? undefined,
    year: Number.isFinite(rawYear) ? rawYear : undefined,
    sort,
  });

  return NextResponse.json(result, { headers: { "cache-control": "no-store" } });
}
