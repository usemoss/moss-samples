import draftPool from "../data/draft-pool.json";
import type { DraftPlayer, HistoricSquad } from "./types";

type CareerSummary = {
  campaigns: number;
  appearances: number;
  goals: number;
  bestCampaignRating: number;
};

// Editorial career-prime benchmarks for historically elite players. These are
// independent game ratings, not official FIFA or EA Sports ratings.
const CURATED_PRIME_RATINGS: Record<string, number> = {
  "pele": 96,
  "diego maradona": 95,
  "franz beckenbauer": 95,
  "johan cruyff": 95,
  "ferenc puskas": 95,
  "ronaldo": 95,
  "lionel messi": 94,
  "cristiano ronaldo": 94,
  "zinedine zidane": 94,
  "garrincha": 94,
  "eusebio": 94,
  "michel platini": 94,
  "zico": 94,
  "ronaldinho": 94,
  "romario": 94,
  "marco van basten": 94,
  "gerd muller": 94,
  "paolo maldini": 94,
  "lev yashin": 94,
  "xavi": 93,
  "andres iniesta": 93,
  "lothar matthaus": 93,
  "roberto baggio": 93,
  "thierry henry": 93,
  "ruud gullit": 93,
  "bobby charlton": 93,
  "bobby moore": 93,
  "franco baresi": 93,
  "neymar": 92,
  "kylian mbappe": 92,
  "luis suarez": 92,
  "robert lewandowski": 92,
  "karim benzema": 92,
  "luka modric": 92,
  "kaka": 92,
  "rivaldo": 92,
  "luis figo": 92,
  "socrates": 92,
  "rivelino": 92,
  "didi": 92,
  "jairzinho": 92,
  "sandor kocsis": 92,
  "giuseppe meazza": 92,
  "stanley matthews": 92,
  "cafu": 92,
  "roberto carlos": 92,
  "sergio ramos": 92,
  "fabio cannavaro": 92,
  "carlos alberto": 92,
  "daniel passarella": 92,
  "gaetano scirea": 92,
  "gianluigi buffon": 93,
  "manuel neuer": 92,
  "iker casillas": 92,
  "dino zoff": 92,
  "oliver kahn": 92,
  "kevin de bruyne": 92,
  "mohamed salah": 91,
  "antoine griezmann": 91,
  "wayne rooney": 91,
  "dennis bergkamp": 92,
  "gabriel batistuta": 91,
  "miroslav klose": 90,
  "jurgen klinsmann": 91,
  "david villa": 91,
  "raul": 91,
  "samuel eto'o": 92,
  "george weah": 93,
  "hugo sanchez": 91,
  "andriy shevchenko": 92,
  "didier drogba": 91,
  "arjen robben": 92,
  "franck ribery": 91,
  "ryan giggs": 91,
  "paul scholes": 91,
  "steven gerrard": 91,
  "frank lampard": 90,
  "andrea pirlo": 91,
  "clarence seedorf": 91,
  "frank rijkaard": 91,
  "johan neeskens": 91,
  "toni kroos": 91,
  "bastian schweinsteiger": 90,
  "casemiro": 90,
  "ngolo kante": 91,
  "yaya toure": 91,
  "david beckham": 91,
  "gheorghe hagi": 91,
  "pavel nedved": 91,
  "michael laudrup": 92,
  "juan roman riquelme": 90,
  "luiz suarez miramontes": 91,
  "philipp lahm": 91,
  "carles puyol": 91,
  "lilian thuram": 91,
  "alessandro nesta": 92,
  "ronald koeman": 91,
  "marcel desailly": 91,
  "jaap stam": 90,
  "virgil van dijk": 91,
  "gerard pique": 90,
  "gordon banks": 91,
  "peter schmeichel": 91,
  "sepp maier": 91,
  "edwin van der sar": 90,
};

function normalizeName(value: string) {
  return value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().replace(/[.'’]/g, "").replace(/\s+/g, " ").trim();
}

const players = (draftPool as HistoricSquad[]).flatMap((squad) => squad.players);
const summaries = new Map<string, CareerSummary>();
for (const player of players) {
  const current = summaries.get(player.playerId) ?? { campaigns: 0, appearances: 0, goals: 0, bestCampaignRating: 45 };
  current.campaigns += 1;
  current.appearances += player.inputs.appearances;
  current.goals += player.inputs.goals;
  current.bestCampaignRating = Math.max(current.bestCampaignRating, player.rating);
  summaries.set(player.playerId, current);
}

export function getCareerPrimeRating(player: DraftPlayer) {
  const curated = CURATED_PRIME_RATINGS[normalizeName(player.name)];
  const summary = summaries.get(player.playerId) ?? {
    campaigns: 1,
    appearances: player.inputs.appearances,
    goals: player.inputs.goals,
    bestCampaignRating: player.rating,
  };
  if (curated) return { rating: curated, source: "curated" as const, ...summary };

  // Non-curated players stay below the elite benchmark band. This keeps one
  // exceptional World Cup from turning a strong career into a 93-rated one.
  const translatedPeak = 66 + (summary.bestCampaignRating - 50) * 0.5;
  const longevity = Math.min(2.5, Math.max(0, summary.campaigns - 1) * 0.9);
  const experience = Math.min(1.5, summary.appearances / 16);
  const scoring = Math.min(1.5, summary.goals / 10);
  const rating = Math.round(Math.max(72, Math.min(89, translatedPeak + longevity + experience + scoring)));
  return { rating, source: "model" as const, ...summary };
}

export function withCareerPrimeRating(player: DraftPlayer): DraftPlayer {
  const prime = getCareerPrimeRating(player);
  return {
    ...player,
    rating: prime.rating,
    campaignRating: player.campaignRating ?? player.rating,
    primeRating: prime.rating,
    ratingMode: "prime",
    primeRatingSource: prime.source,
  };
}

export function withCareerPrimeSquad(squad: HistoricSquad): HistoricSquad {
  return { ...squad, players: squad.players.map(withCareerPrimeRating) };
}

export const PRIME_RATING_SUMMARY = {
  uniquePlayers: summaries.size,
  curatedPlayers: new Set(players.filter((player) => CURATED_PRIME_RATINGS[normalizeName(player.name)]).map((player) => player.playerId)).size,
};
