import { expect, test } from "@playwright/test";

import { openCalculator, submit } from "./helpers.js";

const line = (page) => page.locator("#line");
const up = (page) => page.locator('#chips button[data-history="up"]');
const down = (page) => page.locator('#chips button[data-history="down"]');

test("the history buttons are the first chips and are labelled", async ({ page }) => {
  await openCalculator(page);
  await expect(page.locator("#chips button").first()).toHaveAttribute("data-history", "up");
  await expect(page.locator("#chips button").nth(1)).toHaveAttribute("data-history", "down");
  await expect(up(page)).toHaveAccessibleName("Previous expression");
  await expect(down(page)).toHaveAccessibleName("Next expression");
});

test("the up and down buttons walk through history like the arrow keys", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h");
  await submit(page, "2h");
  await up(page).click();
  await expect(line(page)).toHaveValue("2h");
  await up(page).click();
  await expect(line(page)).toHaveValue("1h");
  await up(page).click();
  await expect(line(page)).toHaveValue("1h");
  await down(page).click();
  await expect(line(page)).toHaveValue("2h");
  await down(page).click();
  await expect(line(page)).toHaveValue("");
});

test("going back down restores what was being typed", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h");
  await line(page).fill("now +");
  await up(page).click();
  await expect(line(page)).toHaveValue("1h");
  await down(page).click();
  await expect(line(page)).toHaveValue("now +");
});

test("the history buttons keep the keyboard up", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h");
  await up(page).click();
  await expect(line(page)).toBeFocused();
});

test("with no history the buttons do nothing", async ({ page }) => {
  await openCalculator(page);
  await line(page).fill("abc");
  await up(page).click();
  await expect(line(page)).toHaveValue("abc");
  await down(page).click();
  await expect(line(page)).toHaveValue("abc");
});

test("history from an earlier visit can be reached with the buttons", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h + 2h");
  await page.reload();
  await line(page).waitFor({ state: "visible" });
  await page.locator("#line:enabled").waitFor();
  await up(page).click();
  await expect(line(page)).toHaveValue("1h + 2h");
});

test("tapping an earlier expression copies it into the input", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h + 2h");
  await submit(page, "3h");
  await page.locator("#scrollback .entry .input").first().click();
  await expect(line(page)).toHaveValue("1h + 2h");
  await expect(line(page)).toBeFocused();
  // Recalling does not run it.
  await expect(page.locator("#scrollback .entry")).toHaveCount(2);
});

test("a recalled expression can be edited and run", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h + 2h");
  await page.locator("#scrollback .entry .input").first().click();
  await line(page).press("End");
  await line(page).pressSequentially(" + 1h");
  await line(page).press("Enter");
  await expect(page.locator("#scrollback .entry").last().locator(".output")).toHaveText("4h");
});

test("recalled expressions are reachable from the keyboard", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "5m");
  const recall = page.locator("#scrollback .entry .input").first();
  await expect(recall).toHaveAttribute("role", "button");
  await recall.focus();
  await recall.press("Enter");
  await expect(line(page)).toHaveValue("5m");
});

test("dragging to select an expression's text does not recall it", async ({ page }) => {
  await openCalculator(page);
  await submit(page, "1h");
  await line(page).fill("keep me");
  const echoed = page.locator("#scrollback .entry .input").first();
  await echoed.selectText();
  // A drag-select ends in a click with the selection still in place.
  await echoed.evaluate((element) => element.click());
  await expect(line(page)).toHaveValue("keep me");
});
