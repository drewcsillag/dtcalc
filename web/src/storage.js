// What the page remembers between visits: history and the session state blob.
//
// localStorage can be missing, full or blocked (private windows, strict
// settings), and its contents can be stale or hand-edited, so nothing here is
// allowed to throw: the calculator must work the same without it.

export const KEY = "dtcalc:v1";
export const MAX_HISTORY = 200;

const EMPTY = Object.freeze({ history: [], state: null });

/** @returns {{history: string[], state: string | null}} */
export function loadSaved(storage) {
  let data;
  try {
    data = JSON.parse(storage?.getItem(KEY) ?? "null");
  } catch {
    return { ...EMPTY, history: [] };
  }
  if (data === null || typeof data !== "object" || data.v !== 1) return { ...EMPTY, history: [] };
  return {
    history: Array.isArray(data.history)
      ? data.history.filter((item) => typeof item === "string").slice(-MAX_HISTORY)
      : [],
    state: typeof data.state === "string" ? data.state : null,
  };
}

/** Best effort: a failed write just means nothing is remembered. */
export function save(storage, { history, state }) {
  try {
    storage?.setItem(KEY, JSON.stringify({ v: 1, history: history.slice(-MAX_HISTORY), state }));
  } catch {
    // Quota or blocked storage; carry on.
  }
}

/** The page's storage, or undefined if the browser refuses even to hand it over. */
export function pageStorage() {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}
