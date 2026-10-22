import { NextRequest, NextResponse } from "next/server";
import { ERA_SUMMARIES, getEraTournament } from "../../../lib/era-data";

export const dynamic = "force-dynamic";

export function GET(request: NextRequest) {
  const yearParam = request.nextUrl.searchParams.get("year");
  if (!yearParam) return NextResponse.json({ eras: ERA_SUMMARIES });
  const usedYears = new Set((request.nextUrl.searchParams.get("used") ?? "")
    .split(",")
    .map((value) => Number.parseInt(value, 10))
    .filter(Number.isInteger));
  const year = yearParam === "random"
    ? (() => {
      const available = ERA_SUMMARIES.filter((item) => !usedYears.has(item.year));
      return available[Math.floor(Math.random() * available.length)]?.year;
    })()
    : Number.parseInt(yearParam, 10);
  if (!year) return NextResponse.json({ error: "Every tournament year has already been used." }, { status: 409 });
  const tournament = getEraTournament(year);
  if (!tournament) return NextResponse.json({ error: "Choose a valid World Cup year from 1930 to 2022." }, { status: 404 });
  return NextResponse.json(tournament, { headers: { "cache-control": "no-store" } });
}
