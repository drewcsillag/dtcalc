import assert from "node:assert/strict";
import test from "node:test";

import { createNodeEngine } from "./support.js";

const engine = await createNodeEngine({ zone: "America/New_York", nowMs: 0 });

test("a session with no frozen time uses the real clock", () => {
  const session = engine.newSession("UTC", null);
  const [outcome, lines] = session.run("unix(now)");
  assert.equal(outcome, "ok");
  assert.ok(Math.abs(Number(lines[0]) - Date.now() / 1000) < 60);
});

test("setNow freezes and releases the clock", () => {
  const session = engine.newSession("UTC", null);
  session.setNow(Date.UTC(2026, 4, 23, 16, 15, 13));
  assert.equal(session.run("now")[1][0], "2026-05-23T16:15:13+00:00  UTC");
  session.setNow(null);
  assert.notEqual(session.run("now")[1][0], "2026-05-23T16:15:13+00:00  UTC");
});

test("complete returns candidates as a plain array", () => {
  const session = engine.newSession("UTC", 0);
  assert.ok(Array.isArray(session.complete("now in Toky")));
  assert.ok(session.complete("now in Toky").some((name) => name.includes("Tokyo")));
});

test("state round-trips and a bad blob throws", () => {
  const session = engine.newSession("UTC", 0);
  session.run("x = 90m");
  const other = engine.newSession("America/New_York", 0);
  other.importState(session.exportState());
  assert.equal(other.run("x")[1][0], "1h30m");
  assert.throws(() => other.importState("not json"), /saved state/);
  assert.equal(other.run("x")[1][0], "1h30m");
});

test("an unknown zone is rejected", () => {
  assert.throws(() => engine.newSession("Not/AZone", 0));
});

test("zoneNames lists the zones", () => {
  assert.ok(engine.zoneNames().includes("America/New_York"));
});

test("runLine reports an ambiguity and takes the answers to it", async () => {
  const session = await engine.fresh();
  const first = session.runLine("2:11 - 1:29");
  assert.equal(first.outcome, "error");
  assert.deepEqual(first.ambiguity.options.map((option) => option.choice), ["clock", "duration"]);

  const settled = session.runLine("2:11 - 1:29", [[...first.ambiguity.key, "duration"]]);
  assert.deepEqual(settled, { outcome: "ok", lines: ["42m"], ambiguity: null });
});

test("runLine on an ordinary line has no ambiguity", async () => {
  const session = await engine.fresh();
  assert.deepEqual(session.runLine("1h + 1h"), { outcome: "ok", lines: ["2h"], ambiguity: null });
});
