// The dtcalc engine in the browser: CPython under Pyodide running dtcalc.web.
//
// This module knows nothing about the DOM or about where files live. The
// caller supplies `loadPyodide`, the URL Pyodide's files are served from, and
// a way to fetch bytes, so the same code drives the page and the Node tests.

/**
 * Load Pyodide and install the pure-Python wheels into it.
 *
 * Wheels are unpacked straight into site-packages rather than installed with
 * micropip: micropip would try to reach a package index, and this build must
 * work from its own files alone, offline.
 *
 * @param {object} options
 * @param {Function} options.loadPyodide  Pyodide's loader.
 * @param {string} options.indexURL  Where pyodide.asm.wasm and the stdlib live.
 * @param {string[]} options.wheelURLs  Wheels to unpack, in order.
 * @param {(url: string) => Promise<Uint8Array>} options.fetchBytes
 */
export async function loadEngine({ loadPyodide, indexURL, wheelURLs, fetchBytes }) {
  const pyodide = await loadPyodide({ indexURL });

  for (const url of wheelURLs) {
    const name = url.split("/").pop();
    pyodide.FS.writeFile(`/tmp/${name}`, await fetchBytes(url));
    pyodide.globals.set("_wheel_path", `/tmp/${name}`);
    pyodide.runPython(`
import site, zipfile
zipfile.ZipFile(_wheel_path).extractall(site.getsitepackages()[0])
`);
  }
  pyodide.runPython("import importlib; importlib.invalidate_caches()");

  const WebSession = pyodide.pyimport("dtcalc.web").WebSession;

  /** Start a new session; `nowMs` freezes the clock, `null` uses the real one. */
  function newSession(zone, nowMs = null) {
    const session = WebSession.callKwargs(zone, { now_ms: millis(nowMs) });
    return wrap(session);
  }

  function zoneNames() {
    const names = WebSession.zone_names();
    const result = names.toJs();
    names.destroy();
    return result;
  }

  return { newSession, zoneNames, pythonVersion: pyodide.runPython("import sys; sys.version.split()[0]") };
}

/**
 * A clock reading as Pyodide wants it. JS `null` arrives in Python as a
 * `JsNull` object, not `None`; only `undefined` maps to `None`.
 */
function millis(nowMs) {
  return nowMs === null || nowMs === undefined ? undefined : Math.trunc(nowMs);
}

/** Wrap a Python WebSession so callers only ever see plain JS values. */
function wrap(session) {
  const plain = (proxy) => {
    const value = proxy.toJs();
    proxy.destroy();
    return value;
  };
  return {
    /** @returns {[string, string[]]} outcome name and output lines */
    run: (line) => plain(session.run(line)),
    /**
     * Run a line that may be ambiguous. `choices` are the answers given so
     * far, as `[start, end, "clock" | "duration"]`; `ambiguity` in the reply is
     * null, or the next question: `{key: [start, end], options: [{choice,
     * label, spelling, preview}]}`.
     * @returns {{outcome: string, lines: string[], ambiguity: object | null}}
     */
    runLine: (line, choices = []) => JSON.parse(session.run_line(line, JSON.stringify(choices))),
    complete: (line, cursor = line.length) => plain(session.complete(line, cursor)),
    setNow: (nowMs) => session.set_now(millis(nowMs)),
    exportState: () => session.export_state(),
    /** Throws if the saved state is unusable; the session is then unchanged. */
    importState: (blob) => session.import_state(blob),
  };
}
