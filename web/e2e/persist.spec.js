import { expect, test } from "@playwright/test";

import { openCalculator, submit } from "./helpers.js";

const lastOutput = (page) => page.locator("#scrollback .entry").last().locator(".output");

test("variables survive a reload", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "standup = 9:30 + 1d");
  await page.reload();
  await page.locator("#line:enabled").waitFor();
  await submit(page, "standup - standup");
  await expect(lastOutput(page)).toHaveText("0s");
});

test("settings survive a reload", async ({ page }) => {
  await openCalculator(page);
  await submit(page, ":tz Tokyo");
  await page.reload();
  await page.locator("#line:enabled").waitFor();
  await submit(page, ":tz");
  await expect(lastOutput(page)).toHaveText("working zone is Asia/Tokyo");
});

test("history survives a reload", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h + 2h");
  await page.reload();
  await page.locator("#line:enabled").waitFor();
  await page.locator("#line").press("ArrowUp");
  await expect(page.locator("#line")).toHaveValue("1h + 2h");
});

test("a fresh page has no leftovers from nowhere", async ({ page }) => {
  await openCalculator(page);
  await submit(page, ":vars");
  await expect(lastOutput(page)).not.toContainText("standup");
});

test("garbled saved data is ignored and the calculator still works", async ({ page }) => {
  await openCalculator(page);
  await page.evaluate(() => localStorage.setItem("dtcalc:v1", "{garbage"));
  await page.reload();
  await page.locator("#line:enabled").waitFor();
  await submit(page, "1h + 2h");
  await expect(lastOutput(page)).toHaveText("3h");
});

test("saved variables that no longer load are dropped, history is kept", async ({ page }) => {
  await openCalculator(page);
  await page.evaluate(() =>
    localStorage.setItem(
      "dtcalc:v1",
      JSON.stringify({ v: 1, history: ["1h"], state: '{"v": 99}' }),
    ),
  );
  await page.reload();
  await page.locator("#line:enabled").waitFor();
  await page.locator("#line").press("ArrowUp");
  await expect(page.locator("#line")).toHaveValue("1h");
  await submit(page, "2h + 1h");
  await expect(lastOutput(page)).toHaveText("3h");
});

test("works when storage is blocked", async ({ page }) => {
  await page.addInitScript(() => {
    const blocked = () => {
      throw new DOMException("blocked", "SecurityError");
    };
    Storage.prototype.getItem = blocked;
    Storage.prototype.setItem = blocked;
    Storage.prototype.removeItem = blocked;
  });
  await openCalculator(page);
  await submit(page, "x = 1h");
  await submit(page, "x + 2h");
  await expect(lastOutput(page)).toHaveText("3h");
});
