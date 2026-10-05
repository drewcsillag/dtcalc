// The page: a terminal-like scrollback over the Pyodide engine.

import { applyCompletion, insertChip, tabCompletion } from "./completion.js";
import { loadEngine } from "./engine.js";
import { loadSaved, pageStorage, save } from "./storage.js";

const scrollback = document.getElementById("scrollback");
const status = document.getElementById("status");
const form = document.getElementById("form");
const line = document.getElementById("line");
const chips = document.getElementById("chips");
const suggestions = document.getElementById("suggestions");

const MAX_SUGGESTIONS = 8;

const QUIT_NOTE = "Nothing to quit: this runs in your browser, so just close this tab.";

async function fetchBytes(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`could not load ${url} (${response.status})`);
  return new Uint8Array(await response.arrayBuffer());
}

function browserZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

async function start() {
  const { loadPyodide } = await import("./pyodide/pyodide.mjs");
  const manifest = await (await fetch("wheels.json")).json();
  const engine = await loadEngine({
    loadPyodide,
    indexURL: new URL("pyodide/", location.href).href,
    wheelURLs: manifest.map((name) => new URL(`wheels/${name}`, location.href).href),
    fetchBytes,
  });

  let session;
  try {
    session = engine.newSession(browserZone());
  } catch {
    // A zone name the bundled tz database does not know; UTC always exists.
    session = engine.newSession("UTC");
  }
  return session;
}

/** Put back saved variables and settings; unusable state is simply not restored. */
function restore(session, saved) {
  if (saved.state === null) return;
  try {
    session.importState(saved.state);
  } catch {
    // Import is all-or-nothing, so the fresh session is untouched.
  }
}

function addEntry(input, outcome, lines) {
  const entry = document.createElement("div");
  entry.className = "entry";

  const echoed = document.createElement("div");
  echoed.className = "input";
  echoed.textContent = input;
  // Tapping it copies it back into the input; see wireRecall.
  echoed.setAttribute("role", "button");
  echoed.tabIndex = 0;

  const output = document.createElement("pre");
  output.className = outcome === "error" ? "output error" : "output";
  if (lines.length > 1) output.classList.add("block");
  output.textContent = lines.join("\n");

  entry.append(echoed, output);
  scrollback.append(entry);
  scrollback.scrollTop = scrollback.scrollHeight;
}

function wireEditing(session) {
  const candidates = () => session.complete(line.value, line.selectionStart ?? line.value.length);

  function refreshSuggestions() {
    const shown = candidates().slice(0, MAX_SUGGESTIONS);
    suggestions.replaceChildren(
      ...shown.map((name) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = name;
        button.dataset.complete = name;
        return button;
      }),
    );
    suggestions.hidden = shown.length === 0;
  }

  function setLine({ line: text, cursor }) {
    line.value = text;
    line.setSelectionRange(cursor, cursor);
    refreshSuggestions();
  }

  // Taps must not move focus off the input, or the phone keyboard closes
  // between every chip.
  for (const strip of [chips, suggestions]) {
    strip.addEventListener("pointerdown", (event) => event.preventDefault());
  }

  chips.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-insert]");
    if (!button) return;
    const start = line.selectionStart ?? line.value.length;
    const end = line.selectionEnd ?? start;
    setLine(insertChip(line.value, start, end, button.dataset.insert));
    line.focus();
  });

  suggestions.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-complete]");
    if (!button) return;
    const cursor = line.selectionStart ?? line.value.length;
    setLine(applyCompletion(line.value, cursor, button.dataset.complete));
    line.focus();
  });

  line.addEventListener("input", refreshSuggestions);
  line.addEventListener("click", refreshSuggestions);
  line.addEventListener("keyup", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") refreshSuggestions();
  });

  line.addEventListener("keydown", (event) => {
    if (event.key !== "Tab" || event.shiftKey) return;
    const cursor = line.selectionStart ?? line.value.length;
    const result = tabCompletion(line.value, cursor, candidates());
    // With nothing to complete, Tab keeps its normal job of moving focus on.
    if (!result) return;
    event.preventDefault();
    setLine(result);
  });

  return refreshSuggestions;
}

function wire(session, refreshSuggestions, saved, storage) {
  const history = [...saved.history];
  let position = history.length;
  let draft = "";

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = line.value;
    line.value = "";

    const [outcome, lines] = session.run(text);
    if (outcome !== "nothing") {
      addEntry(text, outcome, outcome === "quit" ? [QUIT_NOTE] : lines);
      if (history.at(-1) !== text) history.push(text);
      save(storage, { history, state: session.exportState() });
    }
    position = history.length;
    draft = "";
    refreshSuggestions();
  });

  // Arrow keys and the on-screen buttons share these, so they cannot drift.
  function older() {
    if (position === 0) return;
    if (position === history.length) draft = line.value;
    position -= 1;
    show(history[position]);
  }

  function newer() {
    if (position === history.length) return;
    position += 1;
    show(position === history.length ? draft : history[position]);
  }

  function show(text) {
    line.value = text;
    line.setSelectionRange(text.length, text.length);
    refreshSuggestions();
  }

  line.addEventListener("keydown", (event) => {
    if (event.key === "ArrowUp" && position > 0) older();
    else if (event.key === "ArrowDown" && position < history.length) newer();
    else return;
    event.preventDefault();
  });

  chips.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-history]");
    if (!button) return;
    if (button.dataset.history === "up") older();
    else newer();
    line.focus();
  });

  return show;
}

/** Tapping an earlier expression in the scrollback puts it back in the input. */
function wireRecall(show) {
  const recall = (target) => {
    const echoed = target.closest(".input");
    if (!echoed) return;
    // Finishing a drag-select also clicks; that should leave the input alone.
    if (window.getSelection()?.toString()) return;
    show(echoed.textContent);
    line.focus();
  };
  scrollback.addEventListener("click", (event) => recall(event.target));
  scrollback.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      recall(event.target);
    }
  });
}

function registerOfflineSupport() {
  // Best effort: without a worker the calculator just needs the network.
  navigator.serviceWorker?.register("sw.js").catch(() => {});
}

try {
  const session = await start();
  const storage = pageStorage();
  const saved = loadSaved(storage);
  restore(session, saved);
  wireRecall(wire(session, wireEditing(session), saved, storage));

  const prefill = new URLSearchParams(location.search).get("q");
  if (prefill !== null) line.value = prefill;

  status.hidden = true;
  line.disabled = false;
  line.focus();
  registerOfflineSupport();
} catch (error) {
  status.textContent = `Could not start the calculator: ${error.message}`;
}
