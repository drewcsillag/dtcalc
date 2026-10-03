// 2026-05-23T12:15:13 in America/New_York, the moment the golden files freeze.
export const FROZEN = new Date("2026-05-23T16:15:13Z");

/** Open the calculator with the clock fixed, and wait until the engine is ready. */
export async function openCalculator(page, query = "") {
  // setFixedTime fixes Date only; timers keep running, which Pyodide's loader needs.
  await page.clock.setFixedTime(FROZEN);
  await page.goto(`/index.html${query}`);
  await page.locator("#line:enabled").waitFor();
}

export async function submit(page, text) {
  await page.locator("#line").fill(text);
  await page.locator("#line").press("Enter");
}

/** Cut this context off from the server; anything not already cached now fails. */
export async function goOffline(context) {
  await context.addCookies([{ name: "offline", value: "1", url: "http://127.0.0.1:4173" }]);
}
