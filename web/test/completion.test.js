import assert from "node:assert/strict";
import test from "node:test";

import { applyCompletion, commonPrefix, currentWord, insertChip, tabCompletion } from "../src/completion.js";

test("currentWord is the word ending at the cursor, as the REPL sees it", () => {
  assert.equal(currentWord("now in Toky", 11), "Toky");
  assert.equal(currentWord("now in Toky", 6), "in");
  assert.equal(currentWord("now + ", 6), "");
  assert.equal(currentWord(":tz Asia/Tok", 12), "Asia/Tok");
  assert.equal(currentWord("12:13", 5), "12:13");
});

test("applyCompletion replaces the word and puts the cursor after it", () => {
  assert.deepEqual(applyCompletion("now in Toky", 11, "Tokyo"), { line: "now in Tokyo", cursor: 12 });
});

test("applyCompletion keeps the text after the cursor", () => {
  assert.deepEqual(applyCompletion("to + 1h", 2, "today"), { line: "today + 1h", cursor: 5 });
});

test("commonPrefix is case-insensitive and keeps the first candidate's case", () => {
  assert.equal(commonPrefix(["today", "tomorrow"]), "to");
  assert.equal(commonPrefix(["Sydney", "sydney2"]), "Sydney");
  assert.equal(commonPrefix(["only"]), "only");
  assert.equal(commonPrefix([]), "");
});

test("tabCompletion completes a unique candidate", () => {
  assert.deepEqual(tabCompletion("tomo", 4, ["tomorrow"]), { line: "tomorrow", cursor: 8 });
});

test("tabCompletion extends to the common prefix of several candidates", () => {
  assert.deepEqual(tabCompletion("t", 1, ["today", "tomorrow"]), { line: "to", cursor: 2 });
});

test("tabCompletion does nothing when the common prefix adds nothing", () => {
  assert.equal(tabCompletion("to", 2, ["today", "tomorrow"]), null);
});

test("tabCompletion does nothing when the candidates do not extend what was typed", () => {
  // Zone candidates also match on their last segment, so they need not start with it.
  assert.equal(tabCompletion("New_", 4, ["America/New_York", "America/North_Dakota/New_Salem"]), null);
});

test("tabCompletion does nothing without candidates", () => {
  assert.equal(tabCompletion("zz", 2, []), null);
});

test("insertChip inserts at the cursor and moves past the text", () => {
  assert.deepEqual(insertChip("7", 1, 1, "h"), { line: "7h", cursor: 2 });
  assert.deepEqual(insertChip("ab", 1, 1, "X"), { line: "aXb", cursor: 2 });
});

test("insertChip replaces a selection", () => {
  assert.deepEqual(insertChip("abc", 0, 3, "now"), { line: "now", cursor: 3 });
});

test("insertChip pads an operator with spaces", () => {
  assert.deepEqual(insertChip("now", 3, 3, " in "), { line: "now in ", cursor: 7 });
  assert.deepEqual(insertChip("12:13", 5, 5, " @ "), { line: "12:13 @ ", cursor: 8 });
});

test("insertChip does not double a space that is already there", () => {
  assert.deepEqual(insertChip("now ", 4, 4, " in "), { line: "now in ", cursor: 7 });
  assert.deepEqual(insertChip("", 0, 0, " + "), { line: "+ ", cursor: 2 });
});
