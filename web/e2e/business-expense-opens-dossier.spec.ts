import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

/** A saved expense opens the record it was recorded from: the Expenses row and the search hit both land on the dossier. */

async function openPreview(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "en", theme: "light", emptyChat: true });
  await page.route("**/api/v1/search?**", (route) => route.fulfill({ json: { items: [], next_cursor: null, ledger_groups: [] } }));
  await page.goto("/dev/business-preview");
  await expect(page.getByTestId("business-sidebar-nav")).toBeVisible();
}

async function approveFromInbox(page: Page) {
  const nav = page.getByTestId("business-sidebar-nav");
  const panel = page.getByTestId("workspace-panel-region");
  await nav.getByRole("button", { name: /^Inbox/ }).click();
  // The receipt row, not the received-email group that names the same merchant.
  await panel.getByRole("button", { name: /Ferretería La Esquina.*Ready to review/ }).click();
  await page.getByLabel(/Paid from/).selectOption({ label: "Operating account · DOP" });
  await page.getByRole("button", { name: "Save review details" }).click();
  await page.getByRole("button", { name: "Approve expense", exact: true }).click();
  await expect(panel).toContainText("One expense was recorded after approval");
}

const dossier = (page: Page) => page.getByTestId("business-record-review");

test.describe("A saved expense opens its record", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("the Expenses row opens the dossier of the receipt it was recorded from", async ({ page }) => {
    await openPreview(page);
    await approveFromInbox(page);
    const nav = page.getByTestId("business-sidebar-nav");
    const panel = page.getByTestId("workspace-panel-region");
    await nav.getByRole("button", { name: /^Expenses/ }).click();
    await expect(panel.getByRole("heading", { name: "Expenses", exact: true })).toBeVisible();
    await panel.getByRole("button", { name: /Ferretería La Esquina/ }).first().click();
    await expect(dossier(page)).toBeVisible();
    await expect(page).toHaveURL(/[?&]receipt=/);
    await expect(dossier(page)).toContainText("One expense was recorded after approval");
    await expect(dossier(page)).toContainText("Ferretería La Esquina");
    await expect(dossier(page).getByText(/Revision history/)).toBeVisible();
    await expect(dossier(page).getByText(/^Revision \d+$/)).toBeVisible();
    // On a desktop the record sits in a tray beside Expenses; its close control returns, and the address follows.
    await expect(panel.getByRole("heading", { name: "Expenses", exact: true })).toBeVisible();
    await page.getByTestId("side-drawer").getByRole("button", { name: "Close", exact: true }).click();
    await expect(page.getByTestId("side-drawer")).toHaveCount(0);
    await expect(page).not.toHaveURL(/[?&]receipt=/);
  });

  test("an expense entered by hand opens its own detail, which says no receipt is attached", async ({ page }) => {
    await openPreview(page);
    const nav = page.getByTestId("business-sidebar-nav");
    const panel = page.getByTestId("workspace-panel-region");
    await nav.getByRole("button", { name: /^Expenses/ }).click();
    await panel.getByRole("button", { name: /Estación Ruta 3/ }).click();
    const detail = page.getByTestId("business-expense-detail");
    await expect(detail).toBeVisible();
    await expect(page).toHaveURL(/[?&]expense=exp-gas/);
    await expect(detail.getByRole("heading", { name: "Estación Ruta 3" })).toBeVisible();
    await expect(detail).toContainText("No receipt attached");
    await expect(detail).toContainText(/Recorded on/);
    await expect(detail).toContainText("Revision 1");
    await expect(panel.getByRole("heading", { name: "Expenses", exact: true })).toBeVisible();
    await page.getByTestId("side-drawer").getByRole("button", { name: "Close", exact: true }).click();
    await expect(panel.getByRole("button", { name: /Estación Ruta 3/ })).toBeFocused();
    await expect(page).not.toHaveURL(/[?&]expense=/);
  });

  test("the search hit opens the same dossier", async ({ page }) => {
    await openPreview(page);
    await approveFromInbox(page);
    await page.getByTestId("business-sidebar-nav").getByRole("button", { name: /^Overview/ }).click();
    await page.getByRole("button", { name: /^Search/ }).first().click();
    const input = page.getByPlaceholder("Search a merchant, amount or note");
    await expect(input).toBeFocused();
    await input.fill("ferreteria");
    const expenses = page.getByTestId("workspace-search-results").getByRole("group", { name: "Expenses" });
    await expect(expenses.getByRole("button")).toContainText("Ferretería La Esquina");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await expect(input).toHaveCount(0);
    await expect(dossier(page)).toBeVisible();
    await expect(dossier(page)).toContainText("One expense was recorded after approval");
  });

  test("a direct ?expense= link resolves the record the way the row does", async ({ page }) => {
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    // An expense that names a receipt opens that receipt's record, never "Sin recibo adjunto".
    await page.goto("/dev/business-preview?expense=exp-hosting");
    await expect(page).toHaveURL(/[?&]receipt=rcpt-confirmed/);
    const record = page.locator('[data-testid="business-record-review"], section[aria-labelledby="receipt-review-title"]').first();
    await expect(record).toBeVisible();
    await expect(page.getByTestId("business-expense-detail")).toHaveCount(0);
    await expect(record).not.toContainText("Sin recibo adjunto");
    // An expense entered by hand opens its own detail in the tray, labelled by its title, and says no receipt is attached; the tray title takes focus.
    await page.goto("/dev/business-preview?expense=exp-gas");
    const detail = page.getByTestId("business-expense-detail");
    await expect(detail).toBeVisible();
    await expect(detail.getByRole("heading", { name: "Estación Ruta 3" })).toHaveAttribute("id", "expense-detail-title");
    await expect(detail).toHaveAttribute("aria-labelledby", "expense-detail-title");
    await expect(detail).toContainText("Sin recibo adjunto");
    await expect(page.getByTestId("side-drawer").getByRole("heading", { level: 2 }).first()).toBeFocused();
  });
});
