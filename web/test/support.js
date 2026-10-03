// Loads the *built* engine (web/dist) in Node, so the tests exercise the same
// files the browser is served rather than a development copy.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { loadEngine } from "../src/engine.js";

const DIST = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../dist");

export async function createNodeEngine({ zone, nowMs }) {
  if (!fs.existsSync(path.join(DIST, "wheels.json"))) {
    throw new Error("web/dist is missing; run `make web-build` first");
  }
  const { loadPyodide } = await import(pathToFileURL(path.join(DIST, "pyodide/pyodide.mjs")));
  const wheels = JSON.parse(fs.readFileSync(path.join(DIST, "wheels.json"), "utf8"));
  const engine = await loadEngine({
    loadPyodide,
    indexURL: path.join(DIST, "pyodide") + "/",
    wheelURLs: wheels.map((name) => path.join(DIST, "wheels", name)),
    fetchBytes: async (file) => new Uint8Array(fs.readFileSync(file)),
  });
  return { ...engine, fresh: async () => engine.newSession(zone, nowMs) };
}
