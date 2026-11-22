import { expect, test, type Locator, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const fact = (page: Page, key: string) => page.locator(`[data-fact="${key}"]`);

async function openFiscalRecord(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.fiscal}`);
  await expect(page.getByTestId("business-record-review")).toBeVisible();
  await expect(page.getByTestId("receipt-review-fields")).toBeVisible();
}

async function box(locator: Locator) {
  const found = await locator.boundingBox();
  expect(found).not.toBeNull();
  return found!;
}

const centerY = (found: { y: number; height: number }) => found.y + found.height / 2;
const right = (found: { x: number; width: number }) => found.x + found.width;

const pencil = (page: Page, key: string, label: string) => fact(page, key).getByRole("button", { name: `Editar detalles · ${label}`, exact: true });

async function openRow(page: Page, key: string, label: string) {
  await pencil(page, key, label).click();
  const save = page.getByRole("button", { name: `Guardar · ${label}`, exact: true });
  const cancel = page.getByRole("button", { name: `Cancelar · ${label}`, exact: true });
  const input = fact(page, key).locator("[data-row-open] input").first();
  await expect(input).toBeFocused();
  return { save, cancel, input, field: fact(page, key).locator("[data-row-open]") };
}

/** A row's height and where its label sits inside it, so a page scroll does not count as a move. */
async function rowBoxes(page: Page, key: string) {
  const row = await box(fact(page, key));
  const label = await box(fact(page, key).locator("> :first-child"));
  return { row, label: { ...label, y: label.y - row.y } };
}

const ROWS = [
  { key: "rnc", label: "RNC" },
  { key: "fiscal_number", label: "NCF" },
  { key: "amount", label: "Total" },
];

test.describe("an open fact row", () => {
  for (const width of [1280, 1024, 768, 390]) {
    test(`keeps its field in the value column and both actions in the action slot at ${width}px`, async ({ page }) => {
      await openFiscalRecord(page, width);
      for (const { key, label } of ROWS) {
        const row = fact(page, key);
        await row.scrollIntoViewIfNeeded();
        const value = await box(row.locator("[data-row-value]"));
        const valueInRow = value.y - (await box(row)).y;
        const closedPencil = await box(pencil(page, key, label));
        const { save, cancel, input, field } = await openRow(page, key, label);
        const fieldBox = await box(field);
        const saveBox = await box(save);
        const cancelBox = await box(cancel);

        expect(fieldBox.x, `${key}: the field starts where the value did`).toBeCloseTo(value.x, 0);
        expect(fieldBox.width, `${key}: the field fills the value column`).toBeCloseTo(value.width, 0);
        expect(saveBox.x, `${key}: Guardar sits right of the field`).toBeGreaterThanOrEqual(right(fieldBox));
        expect(cancelBox.x, `${key}: Cancelar follows Guardar`).toBeGreaterThanOrEqual(right(saveBox));
        expect(right(cancelBox), `${key}: Cancelar ends where the pencil did`).toBeCloseTo(right(closedPencil), 0);
        for (const action of [saveBox, cancelBox]) expect(centerY(action), `${key}: the actions sit on the field's line`).toBeCloseTo(centerY(fieldBox), 0);
        if (key === "amount") await expect(input, "an amount stays right-aligned while editing").toHaveCSS("text-align", "right");

        await page.keyboard.press("Escape");
        await expect(row.locator("[data-row-open]")).toHaveCount(0);
        await expect(row.locator("[data-row-value]"), `${key}: Escape returns focus to the row`).toBeFocused();
        // Opening may scroll the page; the value comes back to the same place in its row.
        const back = await box(row.locator("[data-row-value]"));
        expect({ x: back.x, width: back.width, height: back.height, y: back.y - (await box(row)).y }).toEqual({ x: value.x, width: value.width, height: value.height, y: valueInRow });
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
  }

  test("opening a row moves neither its label nor its height", async ({ page }) => {
    for (const width of [1280, 390]) {
      await openFiscalRecord(page, width);
      for (const { key, label } of ROWS) {
        const closed = await rowBoxes(page, key);
        await openRow(page, key, label);
        const open = await rowBoxes(page, key);
        expect.soft(open.row.height, `${key} row height at ${width}px`).toBe(closed.row.height);
        expect.soft(open.label, `${key} label at ${width}px`).toEqual(closed.label);
        await page.keyboard.press("Escape");
        await expect(fact(page, key).locator("[data-row-open]")).toHaveCount(0);
      }
    }
  });

  test("Guardar and Cancelar keep a 44px target where the record is read by touch, and the board's 32px in the desktop tray", async ({ page }) => {
    for (const [width, target] of [[1280, 32], [768, 44], [390, 44]] as const) {
      await openFiscalRecord(page, width);
      const { save, cancel } = await openRow(page, "fiscal_number", "NCF");
      for (const [name, action] of [["Guardar", save], ["Cancelar", cancel]] as const) {
        const found = await box(action);
        expect.soft(found.width, `${name} width at ${width}px`).toBeGreaterThanOrEqual(target);
        expect.soft(found.height, `${name} height at ${width}px`).toBeGreaterThanOrEqual(target);
      }
    }
  });

  test("each value reads whole, not cut off", async ({ page }) => {
    for (const width of [1280, 768, 390]) {
      await openFiscalRecord(page, width);
      for (const key of ["rnc", "fiscal_number", "occurred_on", "amount"]) {
        const value = fact(page, key).locator("[data-row-value]");
        const cut = await value.evaluate((node) => ({ text: node.textContent, shown: node.clientWidth, needed: node.scrollWidth }));
        expect.soft(cut.needed, `${key} "${cut.text}" needs ${cut.needed}px and has ${cut.shown}px at ${width}px`).toBeLessThanOrEqual(cut.shown);
      }
    }
  });

  test("an amount reads right-aligned before it opens", async ({ page }) => {
    await openFiscalRecord(page, 1280);
    for (const key of ["net_amount", "itbis", "amount"]) await expect(fact(page, key).locator("[data-row-value]")).toHaveCSS("text-align", "right");
  });

  test("Enter saves the typed NCF and closes the row", async ({ page }) => {
    await openFiscalRecord(page, 1280);
    await openRow(page, "fiscal_number", "NCF");
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.type("B0100000123");
    await page.keyboard.press("Enter");
    await expect(fact(page, "fiscal_number").locator("[data-row-open]")).toHaveCount(0);
    await expect(fact(page, "fiscal_number")).toContainText("B0100000123");
  });
});
