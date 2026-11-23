import { expect, test, type Locator, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

type Theme = "light" | "dark";
const CARD: Record<Theme, string> = { light: "rgb(255, 254, 250)", dark: "rgb(31, 34, 37)" };
const fields = (page: Page) => page.getByTestId("receipt-review-fields");
const fact = (page: Page, key: string) => fields(page).locator(`[data-fact="${key}"]`);
const report = (page: Page) => page.getByTestId("receipt-facts-choices");
const more = (page: Page) => page.getByTestId("receipt-more").getByRole("button", { name: "Más", exact: true });
const saleSwitch = (page: Page) => page.getByTestId("receipt-mark-sale");
const toast = (page: Page) => page.getByTestId("toast-viewport");

async function openPurchase(page: Page, theme: Theme = "light") {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: theme });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
  await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.fiscal}`);
  await expect(fields(page)).toBeVisible();
}

async function turnIntoSale(page: Page) {
  await more(page).click();
  await saleSwitch(page).click();
  await expect(report(page).getByRole("heading")).toHaveText("Reporte 607");
  await expect(page.getByRole("menu", { name: "Más" }), "Más closes on the change").toBeHidden();
}

async function box(locator: Locator) {
  const found = await locator.boundingBox();
  expect(found).not.toBeNull();
  return found!;
}

test.describe("the Venta switch and the sale's dossier against the locked boards", () => {
  for (const theme of ["light", "dark"] as const) {
    test(`Más holds a Venta row drawn as the Personal row (${theme})`, async ({ page }) => {
      await openPurchase(page, theme);
      await more(page).click();
      const personal = page.getByTestId("receipt-mark-personal");
      await expect(saleSwitch(page)).toHaveAttribute("aria-checked", "false");
      await expect(saleSwitch(page)).toContainText("Venta");
      await expect(saleSwitch(page)).toContainText("Pásalo al Reporte 607.");
      const [first, second] = [await box(personal), await box(saleSwitch(page))];
      expect({ x: second.x, width: second.width, height: second.height }, "the same row").toEqual({ x: first.x, width: first.width, height: first.height });
      expect(second.y, "under Personal").toBeGreaterThan(first.y);
      for (const style of ["color", "background-color", "font-size"]) expect(await saleSwitch(page).evaluate((node, name) => getComputedStyle(node).getPropertyValue(name), style), style).toBe(await personal.evaluate((node, name) => getComputedStyle(node).getPropertyValue(name), style));
    });

    test(`on makes it a sale with a toast and Deshacer, and the sale shows Cliente and Reporte 607 (${theme})`, async ({ page }) => {
      await openPurchase(page, theme);
      await expect(report(page).getByRole("heading")).toHaveText("Reporte 606");
      await turnIntoSale(page);
      await expect(toast(page)).toContainText("Ahora es una venta. Va al Reporte 607.");
      await expect(fact(page, "counterparty").locator("span").first()).toHaveText("Cliente");
      await expect(report(page).locator("li[data-fact] > span:first-child")).toHaveText(["Tipo de ingreso", "Forma de pago"]);
      await expect(fields(page).getByText("Tipo de gasto")).toHaveCount(0);
      await expect(fact(page, "document_type")).toHaveCount(0);
      await expect(report(page), "the card is the app's own surface").toHaveCSS("background-color", CARD[theme]);

      await toast(page).getByRole("button", { name: "Deshacer" }).click();
      await expect(report(page).getByRole("heading")).toHaveText("Reporte 606");
      await expect(fact(page, "counterparty").locator("span").first()).toHaveText("Emisor");
    });

    test(`Forma de pago is one pick that saves in place, and the list moves nothing (${theme})`, async ({ page }) => {
      await openPurchase(page, theme);
      await turnIntoSale(page);
      const row = fact(page, "sale_payment");
      const before = await box(report(page));
      await row.getByRole("button", { expanded: false }).click();
      const list = row.getByRole("listbox");
      await expect(list.getByRole("option")).toHaveText(["Efectivo", "Cheque, transferencia o depósito", "Tarjeta de débito o crédito", "Venta a crédito", "Bonos o certificados de regalo", "Permuta", "Otras formas de venta"]);
      await expect(list).toHaveCSS("background-color", theme === "dark" ? "rgb(31, 34, 37)" : "rgb(255, 255, 255)");
      expect(await box(report(page)), "the open list moves no card").toEqual(before);
      await list.getByRole("option", { name: "Tarjeta de débito o crédito" }).click();
      await expect(row.locator("[data-row-value]")).toHaveText("Tarjeta de débito o crédito");
      await expect(row.locator('[aria-busy="true"]')).toHaveCount(0);
      await expect(row, "a saved pick says nothing more than its value").not.toContainText("Guardado");
      expect(await box(report(page)), "the save adds no line").toEqual(before);
    });

    test(`Datos fiscales of a sale shows its own cards and rows (${theme})`, async ({ page }) => {
      await openPurchase(page, theme);
      await turnIntoSale(page);
      await page.getByRole("tab", { name: "Datos fiscales" }).click();
      const editor = page.getByTestId("fiscal-declaration");
      await expect(editor.locator("section[data-group] h3")).toHaveText(["Reporte 607", "Monto facturado", "ITBIS", "Retenciones", "Otros impuestos"]);
      await expect(editor.locator("ul:not([hidden]) > li[data-fact] > span:first-child")).toHaveText(["Tipo de ID", "Monto facturado", "ITBIS facturado"]);
      await expect(editor.getByText("Sin retenciones.")).toBeVisible();
      await expect(editor.getByText("Sin otros impuestos.")).toBeVisible();
      await editor.getByRole("button", { name: "Agregar retención" }).click();
      await expect(editor.locator('section[data-group="retentions"] li[data-fact] > span:first-child')).toHaveText(["ITBIS retenido por terceros", "Retención de renta por terceros", "Fecha de retención"]);
      await expect(editor.locator("section[data-group]").first()).toHaveCSS("background-color", CARD[theme]);
    });
  }

  test("Historial says the type change as one line", async ({ page }) => {
    await openPurchase(page);
    await turnIntoSale(page);
    await page.getByRole("tab", { name: "Historial" }).click();
    await expect(page.locator('[data-tab-panel="historial"]')).toContainText("Tipo");
    await expect(page.locator('[data-tab-panel="historial"]')).toContainText(/Compra\s*→?\s*Venta/);
  });
});
