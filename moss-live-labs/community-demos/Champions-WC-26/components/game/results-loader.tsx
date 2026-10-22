"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { TournamentResult } from "../../lib/types";
import { useGameStore } from "../../store/game-store";
import { ResultView } from "./result-view";

export function ResultsLoader({ id }: { id: string }) {
  const cached = useGameStore((state) => state.result);
  const reset = useGameStore((state) => state.reset);
  const [result, setResult] = useState<TournamentResult | null>(cached?.id === id ? cached : null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (result) return;
    fetch(`/api/runs/${id}`)
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then(setResult)
      .catch(() => setMissing(true));
  }, [id, result]);

  if (missing) return <main className="center-state"><h1>Run not found.</h1><p>This result may belong to a different local database.</p><Link className="button button-primary" href="/game">Start a new run</Link></main>;
  if (!result) return <main className="center-state"><span className="loader-ring" /><p>Loading your tournament run…</p></main>;
  return <ResultView result={result} onReset={reset} />;
}
