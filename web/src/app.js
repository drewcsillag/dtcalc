// The page: a terminal-like scrollback over the Pyodide engine.

import { loadEngine } from "./engine.js";

const scrollback = document.getElementById("scrollback");
const status = document.getElementById("status");
const form = document.getElementById("form");
const line = document.getElementById("line");

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

function addEntry(input, outcome, lines) {
  const entry = document.createElement("div");
  entry.className = "entry";

  const echoed = document.createElement("div");
  echoed.className = "input";
  echoed.textContent = input;

  const output = document.createElement("pre");
  output.className = outcome === "error" ? "output error" : "output";
  output.textContent = lines.join("\n");

  entry.append(echoed, output);
  scrollback.append(entry);
  scrollback.scrollTop = scrollback.scrollHeight;
}

function wire(session) {
  const history = [];
  let position = 0;
  let draft = "";

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = line.value;
    line.value = "";

    const [outcome, lines] = session.run(text);
    if (outcome !== "nothing") {
      addEntry(text, outcome, outcome === "quit" ? [QUIT_NOTE] : lines);
      if (history.at(-1) !== text) history.push(text);
    }
    position = history.length;
    draft = "";
  });

  line.addEventListener("keydown", (event) => {
    if (event.key === "ArrowUp" && position > 0) {
      if (position === history.length) draft = line.value;
      position -= 1;
      line.value = history[position];
    } else if (event.key === "ArrowDown" && position < history.length) {
      position += 1;
      line.value = position === history.length ? draft : history[position];
    } else {
      return;
    }
    event.preventDefault();
  });
}

try {
  const session = await start();
  wire(session);

  const prefill = new URLSearchParams(location.search).get("q");
  if (prefill !== null) line.value = prefill;

  status.hidden = true;
  line.disabled = false;
  line.focus();
} catch (error) {
  status.textContent = `Could not start the calculator: ${error.message}`;
}
