import { expect, test } from "@playwright/test";

import { openCalculator } from "./helpers.js";

const chip = (page, label) => page.locator("#chips button", { hasText: new RegExp(`^${label}$`) });

test("a unit chip appends to what was typed and keeps the keyboard up", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("7");
  await chip(page, "h").click();
  await expect(page.locator("#line")).toHaveValue("7h");
  await expect(page.locator("#line")).toBeFocused();
});

test("the in chip pads itself with spaces", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("now");
  await chip(page, "in").click();
  await expect(page.locator("#line")).toHaveValue("now in ");
});

test("the @ chip attaches a zone", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("12:13");
  await chip(page, "@").click();
  await expect(page.locator("#line")).toHaveValue("12:13 @ ");
});

test("the colon chip inserts a colon for clock times", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("12");
  await chip(page, ":").click();
  await expect(page.locator("#line")).toHaveValue("12:");
});

test("chips insert at the cursor, not the end", async ({ page }) => {
  await openCalculator(page);
  const line = page.locator("#line");
  await line.fill("1 + 2h");
  await line.evaluate((el) => el.setSelectionRange(1, 1));
  await chip(page, "h").click();
  await expect(line).toHaveValue("1h + 2h");
});

test("a chip row is reachable by scrolling, not by wrapping the page", async ({ page }) => {
  await openCalculator(page);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test("no suggestions are shown before anything is typed", async ({ page }) => {
  await openCalculator(page);
  await expect(page.locator("#suggestions")).toBeHidden();
});

test("typing a zone prefix offers zone names, and tapping one completes it", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("now in Toky");
  const suggestion = page.locator("#suggestions button", { hasText: /^Tokyo$/ });
  await expect(suggestion).toBeVisible();
  await suggestion.click();
  await expect(page.locator("#line")).toHaveValue("now in Tokyo");
  await expect(page.locator("#line")).toBeFocused();
});

test("suggestions go away once the word is complete and nothing else matches", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("zzz");
  await expect(page.locator("#suggestions")).toBeHidden();
});

test("Tab completes a unique candidate", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("tomo");
  await page.locator("#line").press("Tab");
  await expect(page.locator("#line")).toHaveValue("tomorrow");
  await expect(page.locator("#line")).toBeFocused();
});

test("Tab extends to the common prefix when several candidates remain", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("u");
  // unix, upcoming: nothing in common beyond "u", so Tab leaves the text alone.
  await page.locator("#line").press("Tab");
  await expect(page.locator("#line")).toHaveValue("u");
});

test("meta commands are suggested after a colon", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill(":t");
  await expect(page.locator("#suggestions button", { hasText: /^:tz$/ })).toBeVisible();
});

test("a result still runs after using chips and suggestions", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").fill("now");
  await chip(page, "in").click();
  await page.locator("#line").pressSequentially("Toky");
  await page.locator("#suggestions button", { hasText: /^Tokyo$/ }).click();
  await page.locator("#line").press("Enter");
  await expect(page.locator("#scrollback .entry").last().locator(".output")).toHaveText(
    "2026-05-24T01:15:13+09:00  Asia/Tokyo",
  );
});
