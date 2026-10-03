// Text editing for the completion UI, kept free of the DOM so it can be tested
// directly. The Python completer decides *what* to offer; this decides what
// the line becomes when a candidate or a chip is chosen.

// The same word the REPL completes: identifier characters plus the slash and
// colon that zone names and commands use. Python's `completions` and this
// pattern must agree, or a tapped candidate would replace the wrong span.
const WORD = /[A-Za-z0-9_/:]+$/;

/** The word that ends at `cursor`, or "" if the cursor is not after one. */
export function currentWord(line, cursor) {
  const match = WORD.exec(line.slice(0, cursor));
  return match ? match[0] : "";
}

/** Replace the word before `cursor` with `candidate`. */
export function applyCompletion(line, cursor, candidate) {
  const start = cursor - currentWord(line, cursor).length;
  return {
    line: line.slice(0, start) + candidate + line.slice(cursor),
    cursor: start + candidate.length,
  };
}

/** The longest case-insensitive common prefix, spelled as the first candidate spells it. */
export function commonPrefix(candidates) {
  if (candidates.length === 0) return "";
  let length = candidates[0].length;
  for (const other of candidates.slice(1)) {
    let i = 0;
    while (
      i < length &&
      i < other.length &&
      candidates[0][i].toLowerCase() === other[i].toLowerCase()
    ) {
      i += 1;
    }
    length = i;
  }
  return candidates[0].slice(0, length);
}

/**
 * What Tab should do, or `null` to leave the line alone.
 *
 * One candidate is completed outright. Several are completed only as far as
 * they agree *and* only if that extends what was typed: zone candidates also
 * match on their last segment, so their common prefix can be unrelated to the
 * word, and replacing the word with it would lose what the user typed.
 */
export function tabCompletion(line, cursor, candidates) {
  const word = currentWord(line, cursor);
  if (candidates.length === 0) return null;
  if (candidates.length === 1) {
    return candidates[0] === word ? null : applyCompletion(line, cursor, candidates[0]);
  }
  const shared = commonPrefix(candidates);
  const extends_ = shared.length > word.length && shared.toLowerCase().startsWith(word.toLowerCase());
  return extends_ ? applyCompletion(line, cursor, shared) : null;
}

/**
 * Insert chip `text` over the selection `[start, end)`.
 *
 * A chip written with surrounding spaces (" in ") drops whichever of them the
 * line already has, so tapping it after a space does not double it.
 */
export function insertChip(line, start, end, text) {
  const before = line.slice(0, start);
  const after = line.slice(end);
  let inserted = text;
  if (inserted.startsWith(" ") && (before === "" || before.endsWith(" "))) {
    inserted = inserted.slice(1);
  }
  if (inserted.endsWith(" ") && after.startsWith(" ")) {
    inserted = inserted.slice(0, -1);
  }
  return { line: before + inserted + after, cursor: before.length + inserted.length };
}
