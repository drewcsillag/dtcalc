import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_HISTORY, KEY, loadSaved, save } from "../src/storage.js";

function fakeStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => void data.set(key, String(value)),
    removeItem: (key) => void data.delete(key),
  };
}

const throwing = {
  getItem() {
    throw new Error("blocked");
  },
  setItem() {
    throw new Error("blocked");
  },
  removeItem() {
    throw new Error("blocked");
  },
};

test("nothing saved gives empty history and no state", () => {
  assert.deepEqual(loadSaved(fakeStorage()), { history: [], state: null });
});

test("what was saved is loaded back", () => {
  const storage = fakeStorage();
  save(storage, { history: ["a", "b"], state: '{"v":1}' });
  assert.deepEqual(loadSaved(storage), { history: ["a", "b"], state: '{"v":1}' });
});

test("history is capped to the most recent entries", () => {
  const storage = fakeStorage();
  const history = Array.from({ length: MAX_HISTORY + 5 }, (_, i) => `line ${i}`);
  save(storage, { history, state: null });
  const loaded = loadSaved(storage).history;
  assert.equal(loaded.length, MAX_HISTORY);
  assert.equal(loaded.at(-1), `line ${MAX_HISTORY + 4}`);
});

for (const [name, raw] of [
  ["not json", "{oops"],
  ["an array", "[]"],
  ["null", "null"],
  ["wrong version", '{"v":2,"history":["a"],"state":null}'],
]) {
  test(`unusable saved data (${name}) is ignored`, () => {
    assert.deepEqual(loadSaved(fakeStorage({ [KEY]: raw })), { history: [], state: null });
  });
}

test("bad field types are dropped individually", () => {
  const raw = JSON.stringify({ v: 1, history: ["ok", 5, null, "fine"], state: 7 });
  assert.deepEqual(loadSaved(fakeStorage({ [KEY]: raw })), { history: ["ok", "fine"], state: null });
});

test("blocked storage never throws", () => {
  assert.deepEqual(loadSaved(throwing), { history: [], state: null });
  assert.doesNotThrow(() => save(throwing, { history: ["a"], state: null }));
});

test("missing storage never throws", () => {
  assert.deepEqual(loadSaved(undefined), { history: [], state: null });
  assert.doesNotThrow(() => save(undefined, { history: [], state: null }));
});
