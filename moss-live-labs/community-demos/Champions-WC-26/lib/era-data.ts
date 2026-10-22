import draftPool from "../data/draft-pool.json";
import type { EraSummary, EraTournament, HistoricSquad } from "./types";

const squads = draftPool as HistoricSquad[];
const years = [...new Set(squads.map((squad) => squad.year))].sort((a, b) => a - b);

export const ERA_SUMMARIES: EraSummary[] = years.map((year) => {
  const historicSquads = squads.filter((squad) => squad.year === year);
  return {
    year,
    squads: historicSquads.length,
    players: historicSquads.reduce((total, squad) => total + squad.players.length, 0),
    nations: historicSquads.map((squad) => squad.nation).sort((a, b) => a.localeCompare(b)),
  };
});

export function getEraTournament(year: number): EraTournament | null {
  const summary = ERA_SUMMARIES.find((item) => item.year === year);
  if (!summary) return null;
  return {
    ...summary,
    historicSquads: squads.filter((squad) => squad.year === year),
  };
}
