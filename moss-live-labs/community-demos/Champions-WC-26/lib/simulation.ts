import field from "../data/wc2026-field.json";
import { FORMATION_MODIFIERS } from "./formations";
import type {
  DraftPick,
  ClassicRatingMode,
  FieldTeam,
  FormationName,
  GameMode,
  MatchStage,
  SimMatch,
  TableRow,
  TournamentResult,
  SquadDnaResult,
} from "./types";

type TeamModel = FieldTeam & {
  name: string;
  attack: number;
  defense: number;
  goalkeeper: number;
  mental: number;
  isCustom: boolean;
};

type SimulationInput = {
  xi: DraftPick[];
  formation: FormationName;
  replacedTeam: string;
  seed: number;
  gameMode?: GameMode;
  classicRatingMode?: ClassicRatingMode;
  eraYear?: number | null;
  eraYears?: number[];
  squadDna?: SquadDnaResult | null;
};

const CUSTOM_NAME = "Champions XI";
const GROUP_LETTERS = "ABCDEFGHIJKL".split("");

function mulberry32(seed: number) {
  return function random() {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function poisson(lambda: number, random: () => number) {
  const limit = Math.exp(-lambda);
  let product = 1;
  let count = 0;
  do {
    count += 1;
    product *= random();
  } while (product > limit && count < 12);
  return count - 1;
}

function average(values: number[], fallback = 70) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : fallback;
}

export function mapPlayerAverageToTeamStrength(rating: number) {
  return Math.round(Math.max(58, Math.min(96, 58 + ((rating - 55) / 37) * 38)));
}

function makeCustomTeam(xi: DraftPick[], formation: FormationName, group: string): TeamModel {
  const players = xi.map((pick) => pick.player);
  const modifier = FORMATION_MODIFIERS[formation];
  const attackPlayers = players.filter((player) => player.position === "FWD" || player.position === "MID");
  const defensePlayers = players.filter((player) => player.position === "DEF" || player.position === "GK");
  const playerAverage = average(players.map((player) => player.rating));
  const goalkeeper = mapPlayerAverageToTeamStrength(players.find((player) => player.position === "GK")?.rating ?? 65);
  const strengthRating = mapPlayerAverageToTeamStrength(playerAverage);
  return {
    team: CUSTOM_NAME,
    name: CUSTOM_NAME,
    group,
    fifaRanking: 0,
    fifaPoints: 0,
    strengthRating,
    attack: mapPlayerAverageToTeamStrength(average(attackPlayers.map((player) => player.rating))) + modifier.attack,
    defense: mapPlayerAverageToTeamStrength(average(defensePlayers.map((player) => player.rating))) + modifier.defense,
    goalkeeper,
    mental: mapPlayerAverageToTeamStrength(playerAverage) + (formation === "4-4-2" ? 1 : 0),
    isCustom: true,
  };
}

function makeRealTeam(team: FieldTeam): TeamModel {
  const shape = ((team.fifaRanking * 7) % 5) - 2;
  return {
    ...team,
    name: team.team,
    attack: team.strengthRating + shape,
    defense: team.strengthRating - shape / 2,
    goalkeeper: team.strengthRating + ((team.fifaRanking * 3) % 5) - 2,
    mental: team.strengthRating + Math.max(0, 3 - team.fifaRanking / 25),
    isCustom: false,
  };
}

function expectedGoals(attacker: TeamModel, defender: TeamModel) {
  return Math.max(0.18, Math.min(4.15, 1.22 * Math.exp((attacker.attack - defender.defense) / 21)));
}

function penaltyShootout(a: TeamModel, b: TeamModel, random: () => number) {
  const aEdge = (a.goalkeeper + a.mental - b.goalkeeper - b.mental) / 150;
  const aChance = Math.max(0.39, Math.min(0.61, 0.5 + aEdge));
  const aWins = random() < aChance;
  const baseLoser = 2 + Math.floor(random() * 3);
  const winnerScore = Math.min(6, baseLoser + 1);
  return aWins ? { a: winnerScore, b: baseLoser } : { a: baseLoser, b: winnerScore };
}

function simulateMatch(
  home: TeamModel,
  away: TeamModel,
  stage: MatchStage,
  random: () => number,
  id: string,
): SimMatch {
  const knockout = stage !== "Group stage";
  let homeGoals = poisson(expectedGoals(home, away), random);
  let awayGoals = poisson(expectedGoals(away, home), random);
  let afterExtraTime = false;
  let penalties: SimMatch["penalties"] = null;

  if (knockout && homeGoals === awayGoals) {
    afterExtraTime = true;
    homeGoals += poisson(expectedGoals(home, away) * 0.25, random);
    awayGoals += poisson(expectedGoals(away, home) * 0.25, random);
    if (homeGoals === awayGoals) {
      const shootout = penaltyShootout(home, away, random);
      penalties = { home: shootout.a, away: shootout.b };
    }
  }

  const winner = homeGoals > awayGoals
    ? home.name
    : awayGoals > homeGoals
      ? away.name
      : penalties
        ? penalties.home > penalties.away ? home.name : away.name
        : null;
  const customTeamPlayed = home.isCustom || away.isCustom;
  const customScore = home.isCustom ? homeGoals : awayGoals;
  const opponentScore = home.isCustom ? awayGoals : homeGoals;
  const customWonPens = penalties && ((home.isCustom && penalties.home > penalties.away) || (away.isCustom && penalties.away > penalties.home));
  const customOutcome = !customTeamPlayed
    ? null
    : customScore > opponentScore || customWonPens
      ? "W"
      : customScore < opponentScore || penalties
        ? "L"
        : "D";

  return {
    id,
    stage,
    home: home.name,
    away: away.name,
    homeGoals,
    awayGoals,
    afterExtraTime,
    penalties,
    winner,
    customTeamPlayed,
    customOutcome,
    customOpponent: customTeamPlayed ? (home.isCustom ? away.name : home.name) : null,
  };
}

function blankRow(team: string, fairPlay: number): TableRow {
  return { team, played: 0, won: 0, drawn: 0, lost: 0, gf: 0, ga: 0, gd: 0, points: 0, fairPlay };
}

function applyMatch(row: TableRow, goalsFor: number, goalsAgainst: number) {
  row.played += 1;
  row.gf += goalsFor;
  row.ga += goalsAgainst;
  row.gd = row.gf - row.ga;
  if (goalsFor > goalsAgainst) {
    row.won += 1;
    row.points += 3;
  } else if (goalsFor < goalsAgainst) {
    row.lost += 1;
  } else {
    row.drawn += 1;
    row.points += 1;
  }
}

function sortTable(rows: TableRow[], groupMatches: SimMatch[]) {
  const h2hPoints = (a: string, b: string) => {
    const match = groupMatches.find((item) =>
      (item.home === a && item.away === b) || (item.home === b && item.away === a),
    );
    if (!match || match.homeGoals === match.awayGoals) return 1;
    const winner = match.homeGoals > match.awayGoals ? match.home : match.away;
    return winner === a ? 3 : 0;
  };
  return [...rows].sort((a, b) =>
    b.points - a.points
    || (a.points === b.points ? h2hPoints(b.team, a.team) - h2hPoints(a.team, b.team) : 0)
    || b.gd - a.gd
    || b.gf - a.gf
    || a.fairPlay - b.fairPlay
    || a.team.localeCompare(b.team),
  );
}

function pickOpponent(pool: TeamModel[], team: TeamModel) {
  const differentGroup = pool.findIndex((candidate) => candidate.group !== team.group);
  const index = differentGroup >= 0 ? differentGroup : 0;
  return pool.splice(index, 1)[0];
}

function shuffle<T>(items: T[], random: () => number) {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function winnerModel(match: SimMatch, lookup: Map<string, TeamModel>) {
  if (!match.winner) throw new Error(`Knockout match ${match.id} has no winner`);
  const winner = lookup.get(match.winner);
  if (!winner) throw new Error(`Missing model for ${match.winner}`);
  return winner;
}

export function simulateTournament(input: SimulationInput): TournamentResult {
  if (input.xi.length !== 11) throw new Error("A complete XI is required.");
  const draftedEraYears = input.xi.map((pick) => pick.player.year);
  if (input.gameMode === "era" && new Set(draftedEraYears).size !== 11) {
    throw new Error("World Cup Era requires one player from each of eleven different tournament-year spins.");
  }
  const replaced = (field as FieldTeam[]).find((team) => team.team === input.replacedTeam);
  if (!replaced) throw new Error("Choose a valid World Cup 2026 team slot.");
  const random = mulberry32(input.seed || 1);

  const models = (field as FieldTeam[]).map(makeRealTeam).filter((team) => team.name !== input.replacedTeam);
  const custom = makeCustomTeam(input.xi, input.formation, replaced.group);
  models.push(custom);
  const lookup = new Map(models.map((team) => [team.name, team]));
  const allMatches: SimMatch[] = [];
  const allGroupTables: Record<string, TableRow[]> = {};
  const advancing: Record<string, { winner: TeamModel; runner: TeamModel; third: TeamModel }> = {};

  for (const group of GROUP_LETTERS) {
    const teams = models.filter((team) => team.group === group);
    const rows = new Map(teams.map((team) => [team.name, blankRow(team.name, Math.floor(random() * 8))]));
    const groupMatches: SimMatch[] = [];
    let matchNumber = 0;
    for (let i = 0; i < teams.length; i += 1) {
      for (let j = i + 1; j < teams.length; j += 1) {
        const match = simulateMatch(teams[i], teams[j], "Group stage", random, `G${group}-${++matchNumber}`);
        groupMatches.push(match);
        allMatches.push(match);
        applyMatch(rows.get(match.home)!, match.homeGoals, match.awayGoals);
        applyMatch(rows.get(match.away)!, match.awayGoals, match.homeGoals);
      }
    }
    const table = sortTable([...rows.values()], groupMatches);
    allGroupTables[group] = table;
    advancing[group] = {
      winner: lookup.get(table[0].team)!,
      runner: lookup.get(table[1].team)!,
      third: lookup.get(table[2].team)!,
    };
  }

  const thirds = GROUP_LETTERS.map((group) => ({ team: advancing[group].third, row: allGroupTables[group][2] }))
    .sort((a, b) => b.row.points - a.row.points || b.row.gd - a.row.gd || b.row.gf - a.row.gf || a.row.fairPlay - b.row.fairPlay)
    .slice(0, 8);
  const thirdNames = new Set(thirds.map((entry) => entry.team.name));
  for (const group of GROUP_LETTERS) {
    allGroupTables[group] = allGroupTables[group].map((row, index) => ({
      ...row,
      qualified: index < 2 || thirdNames.has(row.team),
    }));
  }

  const winners = shuffle(GROUP_LETTERS.map((group) => advancing[group].winner), random);
  const runners = shuffle(GROUP_LETTERS.map((group) => advancing[group].runner), random);
  const thirdTeams = shuffle(thirds.map((entry) => entry.team), random);
  const r32Pairs: [TeamModel, TeamModel][] = [];
  for (const winner of winners.slice(0, 8)) r32Pairs.push([winner, pickOpponent(thirdTeams, winner)]);
  for (const winner of winners.slice(8)) r32Pairs.push([winner, pickOpponent(runners, winner)]);
  while (runners.length) {
    const home = runners.shift()!;
    r32Pairs.push([home, pickOpponent(runners, home)]);
  }

  const stages: MatchStage[] = ["Round of 32", "Round of 16", "Quarterfinal", "Semifinal", "Final"];
  let roundTeams: [TeamModel, TeamModel][] = r32Pairs;
  for (const stage of stages) {
    const roundMatches = roundTeams.map(([home, away], index) =>
      simulateMatch(home, away, stage, random, `${stage.replaceAll(" ", "-")}-${index + 1}`),
    );
    allMatches.push(...roundMatches);
    if (stage !== "Final") {
      const nextTeams = roundMatches.map((match) => winnerModel(match, lookup));
      roundTeams = [];
      for (let i = 0; i < nextTeams.length; i += 2) roundTeams.push([nextTeams[i], nextTeams[i + 1]]);
    }
  }

  const path = allMatches.filter((match) => match.customTeamPlayed);
  const goalsFor = path.reduce((sum, match) => sum + (match.home === CUSTOM_NAME ? match.homeGoals : match.awayGoals), 0);
  const goalsAgainst = path.reduce((sum, match) => sum + (match.home === CUSTOM_NAME ? match.awayGoals : match.homeGoals), 0);
  const wins = path.filter((match) => match.customOutcome === "W").length;
  const draws = path.filter((match) => match.customOutcome === "D").length;
  const losses = path.filter((match) => match.customOutcome === "L").length;
  const finalMatch = allMatches.find((match) => match.stage === "Final")!;
  const champion = finalMatch.winner === CUSTOM_NAME;
  const lastPathMatch = path[path.length - 1];
  const reached = champion ? "World champions" : lastPathMatch?.stage ?? "Group stage";
  const perfect = champion
    && path.length === 8
    && path.every((match) => match.customOutcome === "W" && !match.penalties);

  return {
    seed: input.seed,
    createdAt: new Date().toISOString(),
    teamName: CUSTOM_NAME,
    replacedTeam: input.replacedTeam,
    group: replaced.group,
    gameMode: input.gameMode ?? "classic",
    classicRatingMode: input.gameMode === "classic" ? (input.classicRatingMode ?? "campaign") : "campaign",
    eraYear: input.eraYear ?? null,
    eraYears: input.gameMode === "era" ? draftedEraYears : (input.eraYears ?? []),
    formation: input.formation,
    xi: input.xi,
    squadRating: custom.strengthRating,
    playerAverageRating: Math.round(average(input.xi.map((pick) => pick.player.rating))),
    squadDna: input.squadDna ?? null,
    groupTable: allGroupTables[replaced.group],
    allGroupTables,
    path,
    allMatches,
    record: { wins, draws, losses },
    goalsFor,
    goalsAgainst,
    reached,
    champion,
    perfect,
  };
}
