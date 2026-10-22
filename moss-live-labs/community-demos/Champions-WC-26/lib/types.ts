export type Position = "GK" | "DEF" | "MID" | "FWD";
export type FormationName = "4-3-3" | "4-4-2" | "3-5-2";
export type GameMode = "classic" | "era";
export type ClassicRatingMode = "campaign" | "prime";

export type RatingInputs = {
  appearances: number;
  starts: number;
  estimatedMinutes: number;
  goals: number;
  assists: null;
  teamFinish: string;
  teamSuccessModifier: number;
  statsCoverage: string;
};

export type DraftPlayer = {
  id: string;
  playerId: string;
  name: string;
  nation: string;
  nationCode: string;
  year: number;
  position: Position;
  subPosition: string;
  rating: number;
  campaignRating?: number;
  primeRating?: number;
  ratingMode?: ClassicRatingMode;
  primeRatingSource?: "curated" | "model";
  inputs: RatingInputs;
};

export type HistoricSquad = {
  id: string;
  nation: string;
  nationCode: string;
  year: number;
  finish: string;
  players: DraftPlayer[];
};

export type EraSummary = {
  year: number;
  squads: number;
  players: number;
  nations: string[];
};

export type EraTournament = EraSummary & {
  historicSquads: HistoricSquad[];
};

export type FormationSlot = {
  id: string;
  label: string;
  position: Position;
  x: number;
  y: number;
};

export type DraftPick = {
  player: DraftPlayer;
  slotId: string;
  squadId: string;
};

export type MossReplacement = {
  outgoing: DraftPlayer;
  incoming: DraftPlayer;
  slotId: string;
  completedAt: string;
};

export type SquadProfile = {
  id: string;
  nation: string;
  nationCode: string;
  year: number;
  finish: string;
  rating: number;
  attack: number;
  defense: number;
  goalkeeper: number;
  experience: number;
  goals: number;
  balance: "attack-led" | "balanced" | "defense-led";
};

export type SquadDnaResult = {
  match: SquadProfile;
  similarity: number;
  mossScore: number;
  explanation: string;
  custom: {
    rating: number;
    attack: number;
    defense: number;
    goalkeeper: number;
    experience: number;
    goals: number;
    balance: "attack-led" | "balanced" | "defense-led";
    nations: number;
    nationMix: Array<{ nation: string; count: number }>;
    averageYear: number;
    eraSpan: number;
  };
};

export type ScoutSearchHit = {
  player: DraftPlayer;
  score: number;
  explanation: string;
};

export type ScoutBrowseResponse = {
  players: DraftPlayer[];
  page: number;
  perPage: number;
  total: number;
  totalPages: number;
  facets: {
    nations: string[];
    years: number[];
  };
};

export type FieldTeam = {
  team: string;
  group: string;
  fifaRanking: number;
  fifaPoints: number;
  strengthRating: number;
};

export type MatchStage = "Group stage" | "Round of 32" | "Round of 16" | "Quarterfinal" | "Semifinal" | "Final";

export type SimMatch = {
  id: string;
  stage: MatchStage;
  home: string;
  away: string;
  homeGoals: number;
  awayGoals: number;
  afterExtraTime: boolean;
  penalties: null | { home: number; away: number };
  winner: string | null;
  customTeamPlayed: boolean;
  customOutcome: "W" | "D" | "L" | null;
  customOpponent: string | null;
};

export type TableRow = {
  team: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  gd: number;
  points: number;
  fairPlay: number;
  qualified?: boolean;
};

export type TournamentResult = {
  id?: string;
  seed: number;
  createdAt: string;
  teamName: string;
  replacedTeam: string;
  group: string;
  gameMode?: GameMode;
  classicRatingMode?: ClassicRatingMode;
  eraYear?: number | null;
  eraYears?: number[];
  formation: FormationName;
  xi: DraftPick[];
  squadRating: number;
  playerAverageRating?: number;
  squadDna?: SquadDnaResult | null;
  groupTable: TableRow[];
  allGroupTables: Record<string, TableRow[]>;
  path: SimMatch[];
  allMatches: SimMatch[];
  record: { wins: number; draws: number; losses: number };
  goalsFor: number;
  goalsAgainst: number;
  reached: string;
  champion: boolean;
  perfect: boolean;
};
