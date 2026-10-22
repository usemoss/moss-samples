import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pool = JSON.parse(readFileSync(new URL("../data/draft-pool.json", import.meta.url), "utf8"));
const players = pool.flatMap((squad) => squad.players);

test("Scout archive has one unique searchable record per player campaign", () => {
  assert.equal(players.length, 10_973);
  assert.equal(new Set(players.map((player) => player.id)).size, players.length);
  for (const player of players) {
    assert.ok(player.name);
    assert.ok(player.nation);
    assert.ok(Number.isInteger(player.year));
    assert.ok(["GK", "DEF", "MID", "FWD"].includes(player.position));
    assert.ok(player.subPosition);
    assert.ok(Number.isFinite(player.rating));
    assert.ok(player.inputs.teamFinish);
  }
});

test("Scout archive can always provide a replacement for every broad position", () => {
  const positions = new Set(players.map((player) => player.position));
  assert.deepEqual([...positions].sort(), ["DEF", "FWD", "GK", "MID"]);
  for (const position of positions) {
    assert.ok(players.filter((player) => player.position === position).length > 100);
  }
});
