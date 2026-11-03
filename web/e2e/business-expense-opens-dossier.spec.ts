import { expect, test, type Page } from "@playwright/test";
import { installBusinessRouteFixture, showAllRecords } from "./support/job2-business-route-fixture";
import { atMidMonth, reviewAction } from "./support/business-receipt-fixture";

// Business is Spanish only, so every string below is the es-419 copy.
/** A saved expense opens the record it was recorded from: the Transacciones row and the search hit both land on the dossier. */

async function openBusiness(page: Page) {
  await installBusinessRouteFixture(page);
  await page.goto("/biz");
  await expect(page.getByTestId("business-sidebar-nav")).toBeVisible();
}

async function approveFromInbox(page: Page) {
  const nav = page.getByTestId("business-sidebar-nav");
  await nav.getByRole("button", { name: /^Bandeja/ }).click();
  await reviewAction(page, /Ferretería La Esquina/).click();
  await expect(page.getByLabel(/Pagado desde/)).toHaveCount(0);
  await page.getByRole("button", { name: "Aprobar", exact: true }).click();
  await expect(page.getByTestId("business-record-review")).toContainText("Se registró un gasto");
}

const dossier = (page: Page) => page.getByTestId("business-record-review");

test.describe("A saved expense opens its record", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("the Registros row opens the dossier of the receipt it was recorded from", async ({ page }) => {
    await openBusiness(page);
    await approveFromInbox(page);
    const nav = page.getByTestId("business-sidebar-nav");
    const panel = page.getByTestId("workspace-panel-region");
    await nav.getByRole("button", { name: /^Registros/ }).click();
    await expect(page.getByRole("heading", { name: "Registros", exact: true, level: 1 })).toBeVisible();
    await panel.locator("tr[data-record-id]").filter({ hasText: "Ferretería La Esquina" }).first().click();
    await expect(dossier(page)).toBeVisible();
    await expect(page).toHaveURL(/[?&]draft=/);
    await expect(dossier(page)).toContainText("Se registró un gasto");
    await expect(dossier(page)).toContainText("Ferretería La Esquina");
    await expect(dossier(page).getByRole("region", { name: "Historial" })).toBeVisible();
    await dossier(page).getByTestId("receipt-history").getByRole("button", { name: /^Historial/ }).click();
    await expect(dossier(page).getByTestId("receipt-history").getByText("Aprobado", { exact: true })).toBeVisible();
    // On a desktop the record lies over Registros; its close control returns, and the address follows.
    await expect(page.getByTestId("transacciones-records")).toBeVisible();
    await page.getByTestId("side-drawer").getByRole("button", { name: "Cerrar", exact: true }).click();
    await expect(page.getByTestId("side-drawer")).toHaveCount(0);
    await expect(page).not.toHaveURL(/[?&](receipt|draft)=/);
  });

  test("an expense entered by hand opens its own detail, which says no receipt is attached", async ({ page }) => {
    await atMidMonth(page);
    await openBusiness(page);
    const nav = page.getByTestId("business-sidebar-nav");
    const panel = page.getByTestId("workspace-panel-region");
    await nav.getByRole("button", { name: /^Registros/ }).click();
    await showAllRecords(page);
    await panel.locator("tr[data-record-id]").filter({ hasText: "Estación Ruta 3" }).click();
    const detail = page.getByTestId("business-expense-detail");
    await expect(detail).toBeVisible();
    await expect(page).toHaveURL(/[?&]expense=exp-gas/);
    await expect(detail.getByRole("heading", { name: "Estación Ruta 3" })).toBeVisible();
    await expect(detail).toContainText("Sin recibo adjunto");
    await expect(detail).toContainText(/Registrado el/);
    await expect(detail).toContainText("Revisión 1");
    await expect(page.getByRole("heading", { name: "Registros", exact: true, level: 2 })).toBeVisible();
    await page.getByTestId("side-drawer").getByRole("button", { name: "Cerrar", exact: true }).click();
    test.info().annotations.push({ type: "issue", description: "Closing the saved expense does not restore focus to its Registros row." });
    await expect(panel.locator("tr[data-record-id]").filter({ hasText: "Estación Ruta 3" })).toBeFocused();
    await expect(page).not.toHaveURL(/[?&]expense=/);
  });

  test("the search hit opens the same dossier", async ({ page }) => {
    await openBusiness(page);
    await approveFromInbox(page);
    await page.getByTestId("business-sidebar-nav").getByRole("button", { name: /^Inicio/ }).click();
    await page.getByTestId("header-search").click();
    const input = page.getByPlaceholder("Busca comercio, monto o nota");
    await expect(input).toBeFocused();
    await input.fill("ferreteria");
    const expenses = page.getByTestId("workspace-search-results").getByRole("group", { name: "Gastos" });
    await expect(expenses.getByRole("button")).toContainText("Ferretería La Esquina");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await expect(input).toHaveCount(0);
    await expect(dossier(page)).toBeVisible();
    await expect(dossier(page)).toContainText("Se registró un gasto");
  });

  test("a direct ?expense= link resolves the record the way the row does", async ({ page }) => {
    await installBusinessRouteFixture(page);
    // An expense that names a receipt opens that receipt's record, never "Sin recibo adjunto".
    await page.goto("/biz?expense=exp-hosting");
    await expect(page).toHaveURL(/[?&]receipt=rcpt-confirmed/);
    const record = page.locator('[data-testid="business-record-review"], section[aria-labelledby="receipt-review-title"]').first();
    await expect(record).toBeVisible();
    await expect(page.getByTestId("business-expense-detail")).toHaveCount(0);
    await expect(record).not.toContainText("Sin recibo adjunto");
    // An expense entered by hand opens its own detail in the tray, labelled by its title, and says no receipt is attached; the tray title takes focus.
    await page.goto("/biz?expense=exp-gas");
    const detail = page.getByTestId("business-expense-detail");
    await expect(detail).toBeVisible();
    await expect(detail.getByRole("heading", { name: "Estación Ruta 3" })).toHaveAttribute("id", "expense-detail-title");
    await expect(detail).toHaveAttribute("aria-labelledby", "expense-detail-title");
    await expect(detail).toContainText("Sin recibo adjunto");
    await expect(page.getByTestId("side-drawer").getByRole("heading", { level: 2 }).first()).toBeFocused();
  });
});
