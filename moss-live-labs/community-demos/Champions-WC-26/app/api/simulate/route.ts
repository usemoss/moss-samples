import { NextResponse } from "next/server";
import { saveRun } from "../../../lib/db";
import { simulateTournament } from "../../../lib/simulation";
import type { ClassicRatingMode, DraftPick, FormationName, GameMode, SquadDnaResult } from "../../../lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json() as {
      xi: DraftPick[];
      formation: FormationName;
      replacedTeam: string;
      seed?: number;
      gameMode?: GameMode;
      classicRatingMode?: ClassicRatingMode;
      eraYear?: number | null;
      eraYears?: number[];
      squadDna?: SquadDnaResult | null;
    };
    const result = simulateTournament({
      ...body,
      seed: body.seed ?? Math.floor(Math.random() * 2_147_483_647),
    });
    return NextResponse.json(saveRun(result));
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Simulation failed." },
      { status: 400 },
    );
  }
}
