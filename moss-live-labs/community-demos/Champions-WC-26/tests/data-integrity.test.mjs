import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const readJson = async (path) => JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));

test("historic pool covers every men's World Cup", async () => {
  const pool = await readJson("../data/draft-pool.json");
  const years = [...new Set(pool.map((squad) => squad.year))];
  assert.equal(years.length, 22);
  assert.equal(Math.min(...years), 1930);
  assert.equal(Math.max(...years), 2022);
  assert.ok(pool.length >= 480);
  assert.ok(pool.every((squad) => squad.players.length >= 11));
});

test("2026 field has 48 teams in 12 groups of four", async () => {
  const field = await readJson("../data/wc2026-field.json");
  assert.equal(field.length, 48);
  for (const group of "ABCDEFGHIJKL") {
    assert.equal(field.filter((team) => team.group === group).length, 4);
  }
  assert.ok(field.every((team) => team.fifaRanking > 0 && team.strengthRating >= 58 && team.strengthRating <= 94));
});
