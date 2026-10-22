import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pool = JSON.parse(readFileSync(new URL("../data/draft-pool.json", import.meta.url), "utf8"));
const years = [...new Set(pool.map((squad) => squad.year))].sort((a, b) => a - b);
const primeModel = readFileSync(new URL("../lib/prime-ratings.ts", import.meta.url), "utf8");

test("World Cup Era mode can open all 22 tournaments and their complete rosters", () => {
  assert.equal(years.length, 22);
  assert.equal(pool.length, 489);
  assert.equal(pool.flatMap((squad) => squad.players).length, 10_973);
  for (const year of years) {
    const squads = pool.filter((squad) => squad.year === year);
    assert.ok(squads.length >= 13, `${year} should include all participating squads`);
    assert.ok(squads.every((squad) => squad.players.every((player) => player.year === year)));
  }
});

test("every historical squad can contribute a valid best-XI Squad DNA profile", () => {
  for (const squad of pool) {
    assert.ok(squad.id);
    assert.ok(squad.nation);
    assert.ok(squad.finish);
    assert.ok(squad.players.some((player) => player.position === "GK"));
    assert.ok(squad.players.length >= 11);
    assert.ok(squad.players.every((player) => Number.isFinite(player.rating)));
  }
});

test("Prime Form uses stable player identity and keeps model ratings below curated elites", () => {
  const messiCampaigns = pool.flatMap((squad) => squad.players).filter((player) => player.name === "Lionel Messi");
  assert.equal(messiCampaigns.length, 5);
  assert.equal(new Set(messiCampaigns.map((player) => player.playerId)).size, 1);
  assert.match(primeModel, /"lionel messi": 94/);
  assert.match(primeModel, /"cristiano ronaldo": 94/);
  assert.match(primeModel, /Math\.min\(89,/);
});
