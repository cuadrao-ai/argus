import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

async function openTransacciones(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.goto("/dev/business-preview?view=transactions");
  await expect(page.getByTestId("business-period-control")).toBeVisible();
}

async function pickRange(page: Page, from: string, to: string) {
  const calendar = page.getByTestId("range-calendar");
  await calendar.locator(`[data-day="${from}"]`).click();
  await calendar.locator(`[data-day="${to}"]`).click();
}

const day = (offset: number) => {
  const date = new Date();
  date.setDate(date.getDate() - offset);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
};

test.describe("Personalizado opens our own range calendar", () => {
  test.describe("on a desktop", () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test("a popover under the period control, no browser date inputs, and an applied range names itself", async ({ page }) => {
      await openTransacciones(page);
      await page.getByTestId("business-period-control").locator('[data-segment="custom"]').click();
      const popover = page.getByTestId("period-popover");
      await expect(popover).toBeVisible();
      await expect(page.getByTestId("period-sheet")).toHaveCount(0);
      await expect(page.locator('input[type="date"]')).toHaveCount(0);
      await expect(popover.getByTestId("range-calendar")).toBeVisible();
      await pickRange(page, day(5), day(2));
      await expect(page.getByTestId("period-apply")).toBeEnabled();
      await page.getByTestId("period-apply").click();
      await expect(popover).toHaveCount(0);
      await expect(page.getByTestId("business-period-control").locator('[data-segment="custom"]')).toContainText("–");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });

    test("closing without applying keeps the period in use", async ({ page }) => {
      await openTransacciones(page);
      const control = page.getByTestId("business-period-control");
      await control.locator('[data-segment="custom"]').click();
      await expect(page.getByTestId("period-popover")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("period-popover")).toHaveCount(0);
      await expect(control.locator('[data-segment="this_month"]')).toHaveAttribute("aria-checked", "true");
    });
  });

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("a sheet from the bottom with the same calendar, and no browser date inputs", async ({ page }) => {
      await openTransacciones(page);
      await page.getByRole("combobox", { name: "Período" }).selectOption("custom");
      const sheet = page.getByTestId("period-sheet");
      await expect(sheet).toBeVisible();
      await expect(page.getByTestId("period-popover")).toHaveCount(0);
      await expect(page.locator('input[type="date"]')).toHaveCount(0);
      await expect(sheet.getByTestId("range-calendar")).toBeVisible();
      await pickRange(page, day(5), day(2));
      await page.getByTestId("period-apply").click();
      await expect(sheet).toHaveCount(0);
      await expect(page.getByRole("combobox", { name: "Período" }).locator("option:checked")).toContainText("–");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  });
});
