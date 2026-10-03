import { expect, test } from "@playwright/test";

import { FROZEN, goOffline, submit } from "./helpers.js";

// The only spec that wants a service worker.
test.use({ serviceWorkers: "allow" });

async function installed(page) {
  await page.clock.setFixedTime(FROZEN);
  await page.goto("/index.html");
  await page.locator("#line:enabled").waitFor();
  // `ready` resolves once a worker is active, which is after it precached.
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => undefined));
  // The first load was not under the worker's control; reload so it is.
  await page.reload();
  await page.locator("#line:enabled").waitFor();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
}

test("the calculator starts with no network once it has been visited", async ({ page, context }) => {
  await installed(page);
  await goOffline(context);
  await page.reload();
  await page.locator("#line:enabled").waitFor();
  await submit(page, "now + 7h");
  await expect(page.locator("#scrollback .entry").last().locator(".output")).toHaveText(
    "2026-05-23T19:15:13-04:00  America/New_York",
  );
});

test("a ?q= link works offline too", async ({ page, context }) => {
  await installed(page);
  await goOffline(context);
  await page.goto("/index.html?q=8h%20*%203");
  await page.locator("#line:enabled").waitFor();
  await expect(page.locator("#line")).toHaveValue("8h * 3");
});

test("the site address without a file name works offline", async ({ page, context }) => {
  await installed(page);
  await goOffline(context);
  await page.goto("/");
  await page.locator("#line:enabled").waitFor();
});

test("only the current version's cache is kept", async ({ page }) => {
  await installed(page);
  const names = await page.evaluate(() => caches.keys());
  expect(names.filter((name) => name.startsWith("dtcalc-"))).toHaveLength(1);
});

test("the page is installable: manifest, icons and theme colour", async ({ page, request }) => {
  await page.goto("/index.html");
  const href = await page.locator('link[rel="manifest"]').getAttribute("href");
  expect(href).toBeTruthy();
  const manifest = await (await request.get(`/${href}`)).json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.start_url).toBe("./");
  expect(manifest.scope).toBe("./");
  const sizes = manifest.icons.map((icon) => icon.sizes);
  expect(sizes).toContain("192x192");
  expect(sizes).toContain("512x512");
  for (const icon of manifest.icons) {
    const response = await request.get(`/${icon.src}`);
    expect(response.ok()).toBe(true);
    expect(response.headers()["content-type"]).toBe("image/png");
  }
  await expect(page.locator('meta[name="theme-color"]').first()).toHaveAttribute("content", /#/);
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveCount(1);
});

test("the offline cut really cuts: an uncached file fails", async ({ page, context }) => {
  await installed(page);
  await goOffline(context);
  const failed = await page.evaluate(() => fetch("not-in-the-precache.txt").then(() => false, () => true));
  expect(failed).toBe(true);
});
