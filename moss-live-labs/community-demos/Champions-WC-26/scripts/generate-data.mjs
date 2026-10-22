import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const ROOT = process.cwd();
const DATA_DIR = join(ROOT, "data");
const SOURCE = "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv";
const RANKING_URL = "https://inside.fifa.com/api/ranking-overview?locale=en&dateId=id15136";
const DRAW_CHECK_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup";

const GROUPS = {
  A: ["Mexico", "South Africa", "Korea Republic", "Czechia"],
  B: ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
  C: ["Brazil", "Morocco", "Scotland", "Haiti"],
  D: ["USA", "Paraguay", "Australia", "Türkiye"],
  E: ["Germany", "Côte d'Ivoire", "Ecuador", "Curaçao"],
  F: ["Netherlands", "Japan", "Sweden", "Tunisia"],
  G: ["Belgium", "Egypt", "IR Iran", "New Zealand"],
  H: ["Spain", "Cabo Verde", "Saudi Arabia", "Uruguay"],
  I: ["France", "Senegal", "Norway", "Iraq"],
  J: ["Argentina", "Algeria", "Austria", "Jordan"],
  K: ["Portugal", "Congo DR", "Uzbekistan", "Colombia"],
  L: ["England", "Croatia", "Ghana", "Panama"],
};

const DRAW_ALIASES = {
  "Korea Republic": "South Korea",
  Czechia: "Czech Republic",
  USA: "United States",
  Türkiye: "Turkey",
  "Côte d'Ivoire": "Ivory Coast",
  "Cabo Verde": "Cape Verde",
  "IR Iran": "Iran",
  "Congo DR": "DR Congo",
};

const RANKING_ALIASES = {
  "Korea Republic": "Korea Republic",
  Czechia: "Czechia",
  USA: "USA",
  Türkiye: "Türkiye",
  "Côte d'Ivoire": "Côte d'Ivoire",
  "Cabo Verde": "Cabo Verde",
  "IR Iran": "IR Iran",
  "Congo DR": "Congo DR",
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  const headers = rows.shift();
  return rows.filter((r) => r.length === headers.length).map((r) =>
    Object.fromEntries(headers.map((header, index) => [header, r[index]])),
  );
}

async function fetchText(url) {
  const response = await fetch(url, { headers: { "user-agent": "Champions-WC26-data-generator/1.0" } });
  if (!response.ok) throw new Error(`Failed ${response.status}: ${url}`);
  return response.text();
}

function fullName(given, family) {
  const parts = [given === "not applicable" ? "" : given, family].filter(Boolean);
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

function hashNumber(value) {
  let hash = 2166136261;
  for (const char of value) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
}

function broadPosition(code) {
  return ({ GK: "GK", DF: "DEF", MF: "MID", FW: "FWD" })[code] ?? "MID";
}

function inferredSubPosition(code, playerId) {
  const choices = {
    GK: ["GK"],
    DF: ["CB", "FB", "CB", "WB"],
    MF: ["CM", "DM", "CAM", "W"],
    FW: ["ST", "CF", "W", "ST"],
  }[code] ?? ["CM"];
  return choices[hashNumber(playerId) % choices.length];
}

function successModifier(performance) {
  const value = performance.toLowerCase();
  if (value === "winner") return 14;
  if (value.includes("final")) return 11;
  if (value.includes("semi")) return 9;
  if (value.includes("quarter")) return 7;
  if (value.includes("round of 16")) return 5;
  if (value.includes("second group")) return 4;
  return 2;
}

function ratePlayer({ position, appearances, starts, estimatedMinutes, goals, modifier }) {
  const goalWeight = { GK: 5, DEF: 3.2, MID: 2.1, FWD: 1.45 }[position];
  const raw = 48
    + Math.min(14, appearances * 1.8)
    + Math.min(6, starts * 0.8)
    + Math.min(7, estimatedMinutes / 90)
    + Math.min(14, goals * goalWeight)
    + modifier;
  return Math.max(45, Math.min(97, Math.round(raw)));
}

async function generateDraftPool() {
  const names = ["squads", "player_appearances", "goals", "qualified_teams"];
  const [squadsText, appearancesText, goalsText, qualifiedText] = await Promise.all(
    names.map((name) => fetchText(`${SOURCE}/${name}.csv`)),
  );
  const squads = parseCsv(squadsText).filter((row) => row.tournament_name.includes("Men's"));
  const appearances = parseCsv(appearancesText).filter((row) => row.tournament_name.includes("Men's"));
  const goals = parseCsv(goalsText).filter((row) => row.tournament_name.includes("Men's") && row.own_goal !== "1");
  const qualified = parseCsv(qualifiedText).filter((row) => row.tournament_name.includes("Men's"));

  const statKey = (row) => `${row.tournament_id}|${row.team_id}|${row.player_id}`;
  const appearanceStats = new Map();
  for (const row of appearances) {
    const key = statKey(row);
    const stat = appearanceStats.get(key) ?? { appearances: 0, starts: 0, substitutes: 0 };
    stat.appearances += 1;
    stat.starts += Number(row.starter || 0);
    stat.substitutes += Number(row.substitute || 0);
    appearanceStats.set(key, stat);
  }

  const goalStats = new Map();
  for (const row of goals) {
    const key = statKey({ ...row, team_id: row.player_team_id });
    goalStats.set(key, (goalStats.get(key) ?? 0) + 1);
  }

  const finishes = new Map(qualified.map((row) => [`${row.tournament_id}|${row.team_id}`, row.performance]));
  const bySquad = new Map();
  for (const row of squads) {
    const year = Number(row.tournament_id.slice(3));
    const key = statKey(row);
    const stats = appearanceStats.get(key) ?? { appearances: 0, starts: 0, substitutes: 0 };
    const estimatedMinutes = stats.starts * 90 + stats.substitutes * 30;
    const goalsCount = goalStats.get(key) ?? 0;
    const finish = finishes.get(`${row.tournament_id}|${row.team_id}`) ?? "group stage";
    const modifier = successModifier(finish);
    const position = broadPosition(row.position_code);
    const player = {
      id: `${row.player_id}-${year}-${row.team_code}`,
      playerId: row.player_id,
      name: fullName(row.given_name, row.family_name),
      nation: row.team_name,
      nationCode: row.team_code,
      year,
      position,
      subPosition: inferredSubPosition(row.position_code, row.player_id),
      rating: ratePlayer({
        position,
        appearances: stats.appearances,
        starts: stats.starts,
        estimatedMinutes,
        goals: goalsCount,
        modifier,
      }),
      inputs: {
        appearances: stats.appearances,
        starts: stats.starts,
        estimatedMinutes,
        goals: goalsCount,
        assists: null,
        teamFinish: finish,
        teamSuccessModifier: modifier,
        statsCoverage: year >= 1970 ? "appearance-level" : "squad-and-goals-only",
      },
    };
    const squadKey = `${row.team_code}-${year}`;
    const squad = bySquad.get(squadKey) ?? {
      id: squadKey,
      nation: row.team_name,
      nationCode: row.team_code,
      year,
      finish,
      players: [],
    };
    squad.players.push(player);
    bySquad.set(squadKey, squad);
  }

  const pool = [...bySquad.values()]
    .filter((squad) => squad.players.some((player) => player.position === "GK") && squad.players.length >= 11)
    .map((squad) => ({ ...squad, players: squad.players.sort((a, b) => b.rating - a.rating || a.name.localeCompare(b.name)) }))
    .sort((a, b) => a.year - b.year || a.nation.localeCompare(b.nation));

  await writeFile(join(DATA_DIR, "draft-pool.json"), JSON.stringify(pool));
  return {
    squads: pool.length,
    players: pool.reduce((sum, squad) => sum + squad.players.length, 0),
    nations: new Set(pool.map((squad) => squad.nation)).size,
    tournaments: new Set(pool.map((squad) => squad.year)).size,
  };
}

async function generateField() {
  const [rankingRaw, drawHtml] = await Promise.all([fetchText(RANKING_URL), fetchText(DRAW_CHECK_URL)]);
  const rankingJson = JSON.parse(rankingRaw);
  const rankingByName = new Map(
    rankingJson.rankings.map((entry) => [entry.rankingItem.name, entry.rankingItem]),
  );

  for (const team of Object.values(GROUPS).flat()) {
    const drawName = DRAW_ALIASES[team] ?? team;
    if (!drawHtml.includes(drawName.replaceAll("&", "&amp;")) && !drawHtml.includes(drawName)) {
      throw new Error(`Live draw cross-check failed for ${team}`);
    }
  }

  const entries = [];
  for (const [group, teams] of Object.entries(GROUPS)) {
    for (const team of teams) {
      const rankingName = RANKING_ALIASES[team] ?? team;
      const ranking = rankingByName.get(rankingName);
      if (!ranking) throw new Error(`No FIFA ranking found for ${team} (${rankingName})`);
      const points = Number(ranking.totalPoints);
      const strengthRating = Math.round(58 + ((points - 1100) / (1880 - 1100)) * 36);
      entries.push({
        team,
        group,
        fifaRanking: Number(ranking.rank),
        fifaPoints: points,
        strengthRating: Math.max(58, Math.min(94, strengthRating)),
      });
    }
  }
  await writeFile(join(DATA_DIR, "wc2026-field.json"), JSON.stringify(entries, null, 2));
  return { teams: entries.length, rankingDate: "2026-06-11" };
}

await mkdir(DATA_DIR, { recursive: true });
const [draftPool, field] = await Promise.all([generateDraftPool(), generateField()]);
await writeFile(
  join(DATA_DIR, "data-sources.json"),
  JSON.stringify({
    generatedAt: new Date().toISOString(),
    draftPool: {
      source: "The Fjelstul World Cup Database v1.2.0 (CC-BY-SA 4.0)",
      repository: "https://github.com/jfjelstul/worldcup",
      ...draftPool,
    },
    wc2026: {
      drawSource: DRAW_CHECK_URL,
      officialDrawCrossCheck: "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/final-draw-results",
      rankingSource: RANKING_URL,
      ...field,
    },
  }, null, 2),
);
console.log(`Generated ${draftPool.squads} historic squads / ${draftPool.players} player-tournament records.`);
console.log(`Generated ${field.teams} World Cup 2026 teams from the ${field.rankingDate} FIFA ranking.`);
