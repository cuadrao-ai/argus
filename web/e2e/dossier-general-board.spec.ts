import { expect, test, type Locator, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const fields = (page: Page) => page.getByTestId("receipt-review-fields");
const fact = (page: Page, key: string) => fields(page).locator(`[data-fact="${key}"]`);
const card = (page: Page, name: string) => page.getByTestId(`receipt-facts-${name}`);

async function openFiscalRecord(page: Page, theme: "light" | "dark" = "light", width = 1440) {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: theme });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
  await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.fiscal}`);
  await expect(fields(page)).toBeVisible();
}

async function box(locator: Locator) {
  const found = await locator.boundingBox();
  expect(found).not.toBeNull();
  return found!;
}
const right = (found: { x: number; width: number }) => found.x + found.width;
const bottom = (found: { y: number; height: number }) => found.y + found.height;

test.describe("the General tab against the locked board", () => {
  test("Más sits at the footer's left edge and the accept action at its right, in both panel sizes", async ({ page }) => {
    await openFiscalRecord(page);
    for (const size of ["regular", "narrow"]) {
      if (size === "narrow") await page.getByTestId("dossier-size").click();
      await expect(page.getByTestId("business-record-review")).toHaveAttribute("data-size", size);
      const footer = await box(page.getByTestId("receipt-review-footer"));
      const more = await box(page.getByTestId("receipt-more").getByRole("button", { name: "Más", exact: true }));
      const accept = await box(page.locator("[data-review-primary]"));
      expect(more.x - footer.x, `${size}: Más starts the footer`).toBeLessThanOrEqual(1);
      expect(right(footer) - right(accept), `${size}: the accept action ends the footer`).toBeLessThanOrEqual(1);
      expect(right(more), `${size}: Más stays left of the accept action`).toBeLessThan(accept.x);
    }
  });

  test("the Más menu opens over the form from the trigger's left edge", async ({ page }) => {
    await openFiscalRecord(page);
    const trigger = page.getByTestId("receipt-more").getByRole("button", { name: "Más", exact: true });
    await trigger.click();
    const menu = await box(page.getByRole("menu", { name: "Más" }));
    const button = await box(trigger);
    expect(menu.x).toBeCloseTo(button.x, 0);
    expect(bottom(menu)).toBeLessThanOrEqual(button.y);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`an open row's field is the value's own box, so nothing moves (${theme})`, async ({ page }) => {
      await openFiscalRecord(page, theme);
      for (const key of ["counterparty", "rnc", "occurred_on", "amount"]) {
        const row = fact(page, key);
        const value = await box(row.locator("[data-row-value]"));
        const cardBefore = await box(card(page, key === "amount" ? "montos" : "comprobante"));
        await row.locator("[data-row-value]").click();
        const control = row.locator("[data-row-open] :is(label > input, select, div:has(> input))").first();
        const field = await box(control);
        expect.soft({ x: field.x, y: field.y, width: field.width, height: field.height }, `${key}: the field takes the value's box`).toEqual({ x: value.x, y: value.y, width: value.width, height: value.height });
        expect.soft(await box(card(page, key === "amount" ? "montos" : "comprobante")), `${key}: the card keeps its size`).toEqual(cardBefore);
        await expect.soft(row.locator("[data-row-open] input").first(), `${key}: the field keeps the value's type size`).toHaveCSS("font-size", key === "amount" ? "16px" : "14.5px");
        await expect.soft(control, `${key}: the app's own green marks the open field`).toHaveCSS("border-top-color", theme === "dark" ? "rgb(143, 203, 176)" : "rgb(47, 90, 73)");
        await page.keyboard.press("Escape");
        await expect(row.locator("[data-row-open]")).toHaveCount(0);
      }
    });

    test(`Tipo de gasto and Forma de pago open a list over the form, and a pick saves in place (${theme})`, async ({ page }) => {
      await openFiscalRecord(page, theme);
      const report = card(page, "choices");
      const before = { report: await box(report), montos: await box(card(page, "montos")) };
      for (const key of ["category", "payment_method"]) {
        const row = fact(page, key);
        await expect(row.locator("select")).toHaveCount(0);
        const trigger = row.getByRole("button", { expanded: false });
        const triggerBox = await box(trigger);
        const chevron = await box(row.locator("svg.lucide-chevron-down"));
        expect.soft(right(triggerBox) - right(chevron), `${key}: the chevron sits in the action slot`).toBeLessThanOrEqual(12);
        await trigger.click();
        const list = row.getByRole("listbox");
        await expect(list).toBeVisible();
        const listBox = await box(list);
        const panel = await box(fields(page));
        expect.soft(listBox.y, `${key}: the list stays inside the tab`).toBeGreaterThanOrEqual(panel.y);
        expect.soft(bottom(listBox), `${key}: the list stays inside the tab`).toBeLessThanOrEqual(bottom(panel));
        expect.soft(listBox.x, `${key}: the list starts at the value column`).toBeCloseTo(triggerBox.x, 0);
        expect.soft(right(listBox), `${key}: the list ends with the action slot`).toBeCloseTo(right(triggerBox), 0);
        await expect.soft(list, `${key}: the list is the app's own popover surface`).toHaveCSS("background-color", theme === "dark" ? "rgb(31, 34, 37)" : "rgb(255, 255, 255)");
        expect.soft({ report: await box(report), montos: await box(card(page, "montos")) }, `${key}: the open list moves no card`).toEqual(before);
        await page.keyboard.press("Escape");
        await expect(list).toHaveCount(0);
      }
      await fact(page, "category").getByRole("button", { expanded: false }).click();
      await fact(page, "category").getByRole("option", { name: /Gastos de representación/ }).click();
      await expect(fact(page, "category").getByTestId("row-saved")).toHaveText("Guardado");
      await expect(fact(page, "category").locator("[data-row-value]")).toContainText("Gastos de representación");
      expect({ report: await box(report), montos: await box(card(page, "montos")) }, "Guardado adds no line").toEqual(before);
      await expect(fact(page, "category").getByTestId("row-saved")).toHaveCount(0, { timeout: 4000 });
      expect({ report: await box(report), montos: await box(card(page, "montos")) }, "and takes none away when it leaves").toEqual(before);
    });
  }

  test("a saved row says Guardado in its action slot and keeps its height", async ({ page }) => {
    await openFiscalRecord(page);
    const row = fact(page, "counterparty");
    const before = await box(row);
    await row.locator("[data-row-value]").click();
    await row.locator("[data-row-open] input").fill("Ferretería Nueva");
    await page.keyboard.press("Enter");
    const saved = row.getByTestId("row-saved");
    await expect(saved).toHaveText("Guardado");
    const mark = await box(saved);
    const after = await box(row);
    expect(after.height).toBe(before.height);
    expect(right(after) - right(mark), "Guardado ends where the pencil does").toBeLessThanOrEqual(1);
    expect(mark.y).toBeGreaterThanOrEqual(after.y);
    expect(bottom(mark)).toBeLessThanOrEqual(bottom(after));
  });

  test("Montos aligns every amount to the value column's right edge", async ({ page }) => {
    await openFiscalRecord(page);
    const edges = [];
    for (const key of ["net_amount", "itbis", "amount"]) {
      const value = fact(page, key).locator("[data-row-value]");
      await expect(value).toHaveCSS("text-align", "right");
      edges.push(right(await box(value)));
    }
    expect(new Set(edges.map((edge) => Math.round(edge))).size).toBe(1);
  });

  test("a clean purchase shows no Tipo row", async ({ page }) => {
    await openFiscalRecord(page);
    await expect(fact(page, "occurred_on")).toBeVisible();
    await expect(fact(page, "document_type")).toHaveCount(0);
  });
});
