import { expect, test, type Locator, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const BUSINESS_BUILD = process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED === "true";
const fact = (page: Page, key: string) => page.locator(`[data-fact="${key}"]`);

async function openFiscalRecord(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.fiscal}`);
  await expect(page.getByTestId("business-record-review")).toBeVisible();
  const tabs = page.getByTestId("receipt-review-tabs");
  if (await tabs.isVisible()) await tabs.getByText("Formulario", { exact: true }).click();
}

async function box(locator: Locator) {
  const found = await locator.boundingBox();
  expect(found).not.toBeNull();
  return found!;
}

const centerX = (found: { x: number; width: number }) => found.x + found.width / 2;

async function pencilColumn(page: Page) {
  const centers = await page.locator("[data-fact]:not(:has([data-row-open])) svg.lucide-pencil").evaluateAll((icons) => icons.map((icon) => {
    const { left, width } = icon.getBoundingClientRect();
    return left + width / 2;
  }));
  expect(centers.length).toBeGreaterThan(1);
  expect(Math.max(...centers) - Math.min(...centers)).toBeLessThan(0.5);
  return centers[0];
}

async function openRow(page: Page, key: string, label: string) {
  await fact(page, key).getByRole("button", { name: `Editar detalles · ${label}`, exact: true }).click();
  const save = page.getByRole("button", { name: `Guardar · ${label}`, exact: true });
  const cancel = page.getByRole("button", { name: `Cancelar · ${label}`, exact: true });
  await expect(fact(page, key).locator("[data-row-open] input").first()).toBeFocused();
  return { save, cancel, field: fact(page, key).locator("[data-row-open] > :first-child") };
}

const ROWS = [
  { key: "rnc", label: "RNC" },
  { key: "fiscal_number", label: "NCF / e-CF" },
  { key: "amount", label: "Monto" },
];

test.describe("an open fact row", () => {
  test.skip(!BUSINESS_BUILD, "Business build only");

  for (const width of [1280, 1024, 390]) {
    test(`keeps check and cross on the field's line with the cross in the pencil column at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await openFiscalRecord(page);
      for (const { key, label } of ROWS) {
        const closedHeight = (await box(fact(page, key))).height;
        const { save, cancel, field } = await openRow(page, key, label);
        const column = await pencilColumn(page);
        const fieldBox = await box(field);
        const saveBox = await box(save);
        const cancelBox = await box(cancel);
        expect(Math.abs(centerX(await box(cancel.locator("svg"))) - column)).toBeLessThan(0.5);
        expect(saveBox.y).toBeCloseTo(fieldBox.y, 0);
        expect(cancelBox.y).toBeCloseTo(fieldBox.y, 0);
        expect(saveBox.x).toBeGreaterThan(fieldBox.x + fieldBox.width);
        for (const action of [saveBox, cancelBox]) {
          expect(action.width).toBeGreaterThanOrEqual(44);
          expect(action.height).toBeGreaterThanOrEqual(44);
        }
        if (key === "fiscal_number" && width >= 720) expect((await box(fact(page, key))).height).toBe(closedHeight);
        await page.keyboard.press("Escape");
        await expect(fact(page, key).locator("[data-row-open]")).toHaveCount(0);
        await expect(fact(page, key).getByRole("button", { name: `Editar detalles · ${label}`, exact: true })).toBeFocused();
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
  }

  test("wraps the actions below a field that cannot fit, still ending in the pencil column", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 900 });
    await openFiscalRecord(page);
    const { save, cancel, field } = await openRow(page, "fiscal_number", "NCF / e-CF");
    const column = await pencilColumn(page);
    const fieldBox = await box(field);
    expect((await box(save)).y).toBeGreaterThanOrEqual(fieldBox.y + fieldBox.height);
    expect(Math.abs(centerX(await box(cancel.locator("svg"))) - column)).toBeLessThan(0.5);
  });

  test("Enter saves the typed NCF and closes the row", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await openFiscalRecord(page);
    await openRow(page, "fiscal_number", "NCF / e-CF");
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.type("B0100000123");
    await page.keyboard.press("Enter");
    await expect(fact(page, "fiscal_number").locator("[data-row-open]")).toHaveCount(0);
    await expect(fact(page, "fiscal_number")).toContainText("B0100000123");
  });
});
