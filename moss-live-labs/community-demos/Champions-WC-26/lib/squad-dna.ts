import draftPool from "../data/draft-pool.json";
import sources from "../data/data-sources.json";
import type { DraftPick, DraftPlayer, HistoricSquad, SquadDnaResult, SquadProfile } from "./types";

export const SQUAD_DNA_INDEX_NAME = `champions-wc26-squad-dna-${sources.generatedAt.slice(0, 10).replaceAll("-", "")}-${sources.draftPool.squads}`;

function average(values: number[], fallback = 65) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : fallback;
}

function balanceLabel(attack: number, defense: number): SquadProfile["balance"] {
  if (attack - defense >= 2.5) return "attack-led";
  if (defense - attack >= 2.5) return "defense-led";
  return "balanced";
}

function bestByPosition(players: DraftPlayer[], position: DraftPlayer["position"], count: number) {
  return players.filter((player) => player.position === position).sort((a, b) => b.rating - a.rating).slice(0, count);
}

function profilePlayers(players: DraftPlayer[]) {
  const attackPlayers = players.filter((player) => player.position === "MID" || player.position === "FWD");
  const defensePlayers = players.filter((player) => player.position === "DEF" || player.position === "GK");
  const attack = Math.round(average(attackPlayers.map((player) => player.rating)));
  const defense = Math.round(average(defensePlayers.map((player) => player.rating)));
  const goalkeeper = Math.max(...players.filter((player) => player.position === "GK").map((player) => player.rating), 65);
  return {
    rating: Math.round(average(players.map((player) => player.rating))),
    attack,
    defense,
    goalkeeper,
    experience: Number(average(players.map((player) => player.inputs.appearances), 0).toFixed(1)),
    goals: players.reduce((sum, player) => sum + player.inputs.goals, 0),
    balance: balanceLabel(attack, defense),
  };
}

export function profileHistoricSquad(squad: HistoricSquad): SquadProfile {
  const selected = [
    ...bestByPosition(squad.players, "GK", 1),
    ...bestByPosition(squad.players, "DEF", 4),
    ...bestByPosition(squad.players, "MID", 3),
    ...bestByPosition(squad.players, "FWD", 3),
  ];
  const fallback = squad.players.filter((player) => !selected.some((item) => item.id === player.id)).sort((a, b) => b.rating - a.rating);
  while (selected.length < 11 && fallback.length) selected.push(fallback.shift()!);
  return {
    id: squad.id,
    nation: squad.nation,
    nationCode: squad.nationCode,
    year: squad.year,
    finish: squad.finish,
    ...profilePlayers(selected),
  };
}

export const SQUAD_PROFILES = (draftPool as HistoricSquad[]).map(profileHistoricSquad);

export const SQUAD_DNA_DOCUMENTS = SQUAD_PROFILES.map((profile) => ({
  id: profile.id,
  text: [
    `${profile.nation} at the ${profile.year} men's World Cup, finishing ${profile.finish}.`,
    `A ${profile.balance} team with a best-XI rating of ${profile.rating}, attack ${profile.attack}, defense ${profile.defense}, and goalkeeper ${profile.goalkeeper}.`,
    `The selected XI averaged ${profile.experience} tournament appearances and scored ${profile.goals} goals.`,
  ].join(" "),
  metadata: {
    nation: profile.nation,
    nationCode: profile.nationCode,
    year: String(profile.year),
    finish: profile.finish,
    balance: profile.balance,
    rating: String(profile.rating),
  },
  payload: JSON.stringify(profile),
}));

export function profileCustomXi(xi: DraftPick[]): SquadDnaResult["custom"] {
  const players = xi.map((pick) => pick.player);
  const profile = profilePlayers(players);
  const years = players.map((player) => player.year);
  const nationCounts = new Map<string, number>();
  for (const player of players) nationCounts.set(player.nation, (nationCounts.get(player.nation) ?? 0) + 1);
  return {
    ...profile,
    nations: nationCounts.size,
    nationMix: [...nationCounts.entries()].map(([nation, count]) => ({ nation, count })).sort((a, b) => b.count - a.count || a.nation.localeCompare(b.nation)),
    averageYear: Math.round(average(years, 0)),
    eraSpan: Math.max(...years) - Math.min(...years),
  };
}

function numericSimilarity(custom: SquadDnaResult["custom"], match: SquadProfile) {
  const nationPresence = (custom.nationMix.find((item) => item.nation === match.nation)?.count ?? 0) / 11;
  const distance =
    Math.min(1, Math.abs(custom.rating - match.rating) / 20) * 0.2
    + Math.min(1, Math.abs(custom.attack - match.attack) / 20) * 0.16
    + Math.min(1, Math.abs(custom.defense - match.defense) / 20) * 0.16
    + Math.min(1, Math.abs(custom.goalkeeper - match.goalkeeper) / 20) * 0.12
    + Math.min(1, Math.abs(custom.experience - match.experience) / 7) * 0.08
    + Math.min(1, Math.abs(custom.goals - match.goals) / 18) * 0.05
    + Math.min(1, Math.abs(custom.averageYear - match.year) / 50) * 0.12
    + (1 - nationPresence) * 0.07
    + (custom.balance === match.balance ? 0 : 0.04);
  return Math.max(0, 1 - distance);
}

export function buildSquadDnaQuery(custom: SquadDnaResult["custom"]) {
  return [
    `Find a historical World Cup squad resembling a ${custom.balance} all-time XI.`,
    `Team rating ${custom.rating}, attack ${custom.attack}, defense ${custom.defense}, goalkeeper ${custom.goalkeeper}.`,
    `Average tournament experience ${custom.experience} appearances and ${custom.goals} campaign goals.`,
    `The XI spans ${custom.nations} nations and an average era around ${custom.averageYear}.`,
  ].join(" ");
}

export function rankSquadDna(
  custom: SquadDnaResult["custom"],
  candidates: Array<{ profile: SquadProfile; mossScore: number }>,
): SquadDnaResult {
  const ranked = candidates.map((candidate) => ({
    ...candidate,
    numericScore: numericSimilarity(custom, candidate.profile),
    combined: numericSimilarity(custom, candidate.profile) * 0.72 + candidate.mossScore * 0.28,
  })).sort((a, b) => b.combined - a.combined);
  const best = ranked[0];
  if (!best) throw new Error("Moss did not return a historical squad match.");
  const similarities = [
    { label: `a ${custom.balance} shape`, delta: custom.balance === best.profile.balance ? 0 : 10 },
    { label: `team ratings of ${custom.rating} and ${best.profile.rating}`, delta: Math.abs(custom.rating - best.profile.rating) },
    { label: `defensive levels of ${custom.defense} and ${best.profile.defense}`, delta: Math.abs(custom.defense - best.profile.defense) },
    { label: `goalkeeper ratings of ${custom.goalkeeper} and ${best.profile.goalkeeper}`, delta: Math.abs(custom.goalkeeper - best.profile.goalkeeper) },
    { label: `an era centered near ${custom.averageYear}`, delta: Math.abs(custom.averageYear - best.profile.year) / 2 },
    { label: `${best.profile.nation} influence in a ${custom.nations}-nation XI`, delta: custom.nationMix.some((item) => item.nation === best.profile.nation) ? 0.5 : 12 },
  ].sort((a, b) => a.delta - b.delta).slice(0, 2).map((item) => item.label);
  return {
    match: best.profile,
    similarity: Math.round(Math.max(0, Math.min(1, best.combined)) * 100),
    mossScore: best.mossScore,
    explanation: `Your XI most closely resembles ${best.profile.nation} ${best.profile.year}: both share ${similarities.join(" and ")}. That side finished ${best.profile.finish}.`,
    custom,
  };
}
