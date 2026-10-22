import draftPool from "../data/draft-pool.json";
import sources from "../data/data-sources.json";
import type { DraftPlayer, HistoricSquad, Position, ScoutBrowseResponse } from "./types";

export const SCOUT_INDEX_NAME = `champions-wc26-players-${sources.generatedAt.slice(0, 10).replaceAll("-", "")}-${sources.draftPool.players}`;

export const SCOUT_PLAYERS = (draftPool as HistoricSquad[]).flatMap((squad) => squad.players);

const playerById = new Map(SCOUT_PLAYERS.map((player) => [player.id, player]));
const nations = [...new Set(SCOUT_PLAYERS.map((player) => player.nation))].sort((a, b) => a.localeCompare(b));
const years = [...new Set(SCOUT_PLAYERS.map((player) => player.year))].sort((a, b) => b - a);

function normalize(value: string) {
  return value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}

export function getScoutPlayer(id: string) {
  return playerById.get(id) ?? null;
}

export function toScoutDocument(player: DraftPlayer) {
  const { appearances, starts, estimatedMinutes, goals, teamFinish, statsCoverage } = player.inputs;
  return {
    id: player.id,
    text: [
      `${player.name} represented ${player.nation} at the ${player.year} men's World Cup.`,
      `Position: ${player.position}, role: ${player.subPosition}, Champions rating: ${player.rating}.`,
      `Tournament record: ${appearances} appearances, ${starts} starts, approximately ${estimatedMinutes} minutes, and ${goals} goals.`,
      `${player.nation} finished as ${teamFinish}.`,
      `Campaign data coverage: ${statsCoverage}.`,
    ].join(" "),
    metadata: {
      playerId: player.playerId,
      playerName: player.name,
      nation: player.nation,
      nationCode: player.nationCode,
      year: String(player.year),
      position: player.position,
      subPosition: player.subPosition,
      rating: String(player.rating),
      appearances: String(appearances),
      goals: String(goals),
      teamFinish,
    },
    payload: JSON.stringify(player),
  };
}

export const SCOUT_DOCUMENTS = SCOUT_PLAYERS.map(toScoutDocument);

export function explainScoutMatch(player: DraftPlayer) {
  const { appearances, goals, teamFinish } = player.inputs;
  const appearanceCopy = appearances === 1 ? "1 appearance" : `${appearances} appearances`;
  const goalCopy = goals === 1 ? "1 goal" : `${goals} goals`;
  return `Moss matched ${player.name}'s ${player.year} campaign: a ${player.subPosition} for ${player.nation} with ${appearanceCopy}, ${goalCopy}, and a ${teamFinish} team finish.`;
}

type BrowseOptions = {
  page: number;
  perPage: number;
  query?: string;
  position?: Position;
  nation?: string;
  year?: number;
  sort?: "rating-desc" | "year-desc" | "year-asc" | "name-asc";
};

export function browseScoutPlayers(options: BrowseOptions): ScoutBrowseResponse {
  const query = normalize(options.query ?? "");
  let filtered = SCOUT_PLAYERS.filter((player) => {
    if (options.position && player.position !== options.position) return false;
    if (options.nation && player.nation !== options.nation) return false;
    if (options.year && player.year !== options.year) return false;
    if (!query) return true;
    return normalize(`${player.name} ${player.nation} ${player.nationCode} ${player.year} ${player.position} ${player.subPosition}`).includes(query);
  });

  const sort = options.sort ?? "rating-desc";
  filtered = [...filtered].sort((a, b) => {
    if (sort === "name-asc") return a.name.localeCompare(b.name) || b.year - a.year;
    if (sort === "year-asc") return a.year - b.year || b.rating - a.rating;
    if (sort === "year-desc") return b.year - a.year || b.rating - a.rating;
    return b.rating - a.rating || b.year - a.year || a.name.localeCompare(b.name);
  });

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / options.perPage));
  const page = Math.min(Math.max(1, options.page), totalPages);
  const start = (page - 1) * options.perPage;

  return {
    players: filtered.slice(start, start + options.perPage),
    page,
    perPage: options.perPage,
    total,
    totalPages,
    facets: { nations, years },
  };
}
