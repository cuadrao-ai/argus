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
    // Back returns to Expenses, and the address follows.
    await dossier(page).getByRole("button", { name: "Expenses" }).click();
    await expect(panel.getByRole("heading", { name: "Expenses", exact: true })).toBeVisible();
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
    await detail.getByRole("button", { name: "Expenses" }).click();
    await expect(panel.getByRole("heading", { name: "Expenses", exact: true })).toBeVisible();
    await expect(page).not.toHaveURL(/[?&]expense=/);
  });

  test("the search hit opens the same dossier", async ({ page }) => {
    await openPreview(page);
    await approveFromInbox(page);
    await page.getByTestId("business-sidebar-nav").getByRole("button", { name: /^Overview/ }).click();
    await page.getByRole("button", { name: /^Search/ }).first().click();
    const input = page.getByPlaceholder("Search expenses, receipts and chats");
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
});
