import { expect, test } from "@playwright/test";

import { openCalculator, submit } from "./helpers.js";

test("starts ready, with the input focused", async ({ page }) => {
  await openCalculator(page);
  await expect(page.locator("#status")).toBeHidden();
  await expect(page.locator("#line")).toBeFocused();
});

test("shows the input and its result in the scrollback", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "now + 7h");
  const entry = page.locator("#scrollback .entry").last();
  await expect(entry.locator(".input")).toHaveText("now + 7h");
  await expect(entry.locator(".output")).toHaveText("2026-05-23T19:15:13-04:00  America/New_York");
  await expect(page.locator("#line")).toHaveValue("");
});

test("an error keeps its caret block and is marked as an error", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "now +");
  const output = page.locator("#scrollback .entry").last().locator(".output");
  await expect(output).toHaveClass(/error/);
  await expect(output).toContainText("error: ");
  await expect(output).toContainText("^");
});

test("variables persist between lines", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "standup = upcoming monday @ 9:30");
  await submit(page, "standup - now");
  await expect(page.locator("#scrollback .entry").last().locator(".output")).toHaveText(
    "45h14m47s",
  );
});

test("the working zone defaults to the browser's zone", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "now");
  await expect(page.locator("#scrollback .entry").last().locator(".output")).toHaveText(
    "2026-05-23T12:15:13-04:00  America/New_York",
  );
});

test("meta commands work", async ({ page }) => {
  await openCalculator(page);
  await submit(page, ":tz Tokyo");
  await expect(page.locator("#scrollback .entry").last().locator(".output")).toHaveText(
    "working zone is now Asia/Tokyo",
  );
});

test("a blank line adds nothing to the scrollback", async ({ page }) => {
  await openCalculator(page);
  await page.locator("#line").press("Enter");
  await expect(page.locator("#scrollback .entry")).toHaveCount(0);
});

test("quit explains itself instead of closing anything", async ({ page }) => {
  await openCalculator(page);
  await submit(page, ":q");
  await expect(page.locator("#scrollback .entry").last().locator(".output")).toContainText(
    "close this tab",
  );
});

test("arrow keys walk through history", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h");
  await submit(page, "2h");
  const line = page.locator("#line");
  await line.press("ArrowUp");
  await expect(line).toHaveValue("2h");
  await line.press("ArrowUp");
  await expect(line).toHaveValue("1h");
  await line.press("ArrowUp");
  await expect(line).toHaveValue("1h");
  await line.press("ArrowDown");
  await expect(line).toHaveValue("2h");
  await line.press("ArrowDown");
  await expect(line).toHaveValue("");
});

test("a repeated line is not duplicated in history", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h");
  await submit(page, "1h");
  const line = page.locator("#line");
  await line.press("ArrowUp");
  await line.press("ArrowUp");
  await expect(line).toHaveValue("1h");
});

test("?q= prefills the input without running it", async ({ page }) => {
  await openCalculator(page, "?q=now%20%2B%201d");
  await expect(page.locator("#line")).toHaveValue("now + 1d");
  await expect(page.locator("#scrollback .entry")).toHaveCount(0);
});

test("the input is set up for typing expressions on a phone", async ({ page }) => {
  await openCalculator(page);
  const line = page.locator("#line");
  await expect(line).toHaveAttribute("autocapitalize", "off");
  await expect(line).toHaveAttribute("autocorrect", "off");
  await expect(line).toHaveAttribute("spellcheck", "false");
  await expect(line).toHaveAttribute("enterkeyhint", "go");
  const size = await line.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  // Below 16px iOS Safari zooms the page when the input is focused.
  expect(size).toBeGreaterThanOrEqual(16);
});

test("long output never makes the page scroll sideways", async ({ page }) => {
  await openCalculator(page);
  await submit(page, ":help");
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
