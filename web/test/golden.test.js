// Replays tests/golden/*.in through the Pyodide build and compares with the
// .out files the Python suite already pins, so the browser engine is held to
// the same executable spec as the CLI.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { createNodeEngine } from "./support.js";

const GOLDEN = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../tests/golden");
const PROMPT = "dtcalc> ";

// 2026-05-23T12:15:13 in America/New_York, the same frozen moment as the CLI tests.
const NOW_MS = Date.UTC(2026, 4, 23, 16, 15, 13);

function transcript(engine, source) {
  const out = [];
  const lines = source.split("\n");
  if (lines.at(-1) === "") lines.pop();
  for (const line of lines) {
    out.push(`${PROMPT}${line}`);
    const [outcome, text] = engine.run(line);
    if (outcome === "quit") break;
    out.push(...text);
  }
  return out.length ? out.join("\n") + "\n" : "";
}

const engine = await createNodeEngine({ zone: "America/New_York", nowMs: NOW_MS });
const cases = fs
  .readdirSync(GOLDEN)
  .filter((name) => name.endsWith(".in"))
  .map((name) => name.slice(0, -3))
  .sort();

test("there are golden cases", () => assert.ok(cases.length > 0));

for (const name of cases) {
  test(`golden: ${name}`, async () => {
    // Each transcript starts from a fresh session, as the CLI does.
    const fresh = await engine.fresh();
    const source = fs.readFileSync(path.join(GOLDEN, `${name}.in`), "utf8");
    const expected = fs.readFileSync(path.join(GOLDEN, `${name}.out`), "utf8");
    assert.equal(transcript(fresh, source), expected);
  });
}
