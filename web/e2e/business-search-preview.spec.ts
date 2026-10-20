import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

async function openPreview(page: Page, language: "en" | "es-419" = "en") {
  await page.route("**/*", (route) => {
    const { hostname } = new URL(route.request().url());
    return ["127.0.0.1", "localhost"].includes(hostname)
      ? route.continue()
      : route.abort("blockedbyclient");
  });
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  await page.route("**/api/v1/search?**", (route) =>
    route.fulfill({ json: { items: [], next_cursor: null, ledger_groups: [] } }),
  );
  await page.goto("/dev/business-preview");
  await expect(page.getByTestId("business-sidebar-nav")).toBeVisible();
}

async function openSearch(page: Page, placeholder: string) {
  await page.getByTestId("header-search").click();
  const input = page.getByPlaceholder(placeholder);
  await expect(input).toBeFocused();
  return input;
}

const results = (page: Page) => page.getByTestId("workspace-search-results");
const panelHeading = (page: Page, name: string) =>
  page.getByTestId("workspace-panel-region").getByRole("heading", { name, exact: true });

test.describe("Business search in the omnisearch", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("an expense found by merchant opens its receipt and original by keyboard", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Search a merchant, amount or note");

    await input.fill("nube hosting");
    const expenses = results(page).getByRole("group", { name: "Expenses" });
    await expect(expenses.getByRole("button")).toHaveCount(1);
    await expect(expenses.getByRole("button")).toContainText("Nube Hosting");
    await expect(expenses.getByRole("button")).toContainText("24.00");
    await expect(results(page).getByRole("group", { name: "Receipts" })).toHaveCount(0);
    await expect(page.getByText("No results found")).toHaveCount(0);

    await page.keyboard.press("ArrowDown");
    await expect(expenses.getByRole("button")).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(input).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    await expect(input).toHaveCount(0);
    await expect(panelHeading(page, "Saved expense")).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download" }).click();
    expect((await download).suggestedFilename()).toBeTruthy();
  });

  test("a receipt found by merchant or file name opens its review", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Search a merchant, amount or note");

    await input.fill("papeleria-oct");
    const receipts = results(page).getByRole("group", { name: "Receipts" });
    await expect(receipts.getByRole("button")).toContainText("Papelería Central");
    await input.fill("ferreteria");
    await expect(receipts.getByRole("button")).toContainText("Ferretería La Esquina");
    await expect(receipts.getByRole("button")).toContainText("Ready to review");
    await receipts.getByRole("button").click();

    await expect(input).toHaveCount(0);
    await expect(panelHeading(page, "Review receipt")).toBeVisible();
  });

  test("an expense without a receipt opens its row in Expenses", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Search a merchant, amount or note");

    await input.fill("estacion");
    await results(page).getByRole("button", { name: /Estación Ruta 3/ }).click();

    await expect(panelHeading(page, "Expenses")).toBeVisible();
    await expect(page.locator('li[aria-current="true"]')).toContainText("Estación Ruta 3");
  });

  test("owner-funded expense keeps its Spanish funding, date and category in search and its list", async ({ page }) => {
    await openPreview(page, "es-419");
    const input = await openSearch(page, "Busca comercio, monto o nota");
    await input.fill("comedor");
    const hit = results(page).getByRole("button", { name: /Comedor Doña Ana/ });
    await expect(hit).toContainText("Dinero del dueño");
    await expect(hit).toContainText("Comidas");
    const detail = await hit.innerText();
    await expect(hit).not.toContainText("Operating account");
    if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/owner-funded-search-spanish.png`, fullPage: true });
    await hit.click();
    const row = page.locator('li[aria-current="true"]');
    await expect(row).toContainText("Comedor Doña Ana");
    await expect(row).toContainText("Dinero del dueño");
    await expect(row).toContainText("Comidas");
    const date = detail.match(/\d{1,2} [a-z]+ \d{4}/)?.[0];
    expect(date).toBeTruthy();
    await expect(row).toContainText(date!);
    await expect(row).not.toContainText("Operating account");
    if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/owner-funded-expenses-spanish.png`, fullPage: true });
  });

  test("no match keeps the existing empty state with a Business hint", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Search a merchant, amount or note");

    await input.fill("zzqqxx");
    await expect(page.getByText("No results found")).toBeVisible();
    await expect(page.getByText("Try a merchant or a file name.")).toBeVisible();
    await expect(results(page)).toHaveCount(0);
  });

  test("a failed search says so and retries in place", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Search a merchant, amount or note");

    await page.evaluate(() => {
      (globalThis as { __businessFixtureFailNextWrite?: string }).__businessFixtureFailNextWrite = "server_error";
    });
    await input.fill("hosting");
    await expect(page.getByRole("alert").filter({ hasText: "We couldn't search your business." })).toBeVisible();
    await page.getByRole("button", { name: "Try searching again" }).first().click();
    await expect(results(page).getByRole("button", { name: /Nube Hosting/ })).toBeVisible();
  });

  test("Spanish shows the same results in Spanish", async ({ page }) => {
    await openPreview(page, "es-419");
    const input = await openSearch(page, "Busca comercio, monto o nota");

    await input.fill("hosting");
    await expect(results(page).getByRole("group", { name: "Gastos" })).toContainText("Nube Hosting");
    await input.fill("zzqqxx");
    await expect(page.getByText("Prueba con el nombre de un comercio o de un archivo.")).toBeVisible();
  });
});

test.describe("Business chats in the omnisearch", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("reads only Business chats and offers no decision filters or preview pane", async ({ page }) => {
    const chatReads: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (/\/api\/v1\/(conversations|history|search)$/.test(url.pathname)) {
        chatReads.push(`${request.method()} ${url.pathname}${url.search}`);
      }
    });
    await openPreview(page);
    // Answer like the server: decision filters only when they are asked for.
    await page.route("**/api/v1/search?**", (route) => {
      const asked = new URL(route.request().url()).searchParams.get("include_ledger_groups");
      const ledger_groups = asked === "true"
        ? ["promising", "watching", "rejected", "revisit_later"].map((decision_state) => ({ decision_state, count: 1 }))
        : null;
      return route.fulfill({ json: { items: [], next_cursor: null, ledger_groups } });
    });
    const input = await openSearch(page, "Search a merchant, amount or note");
    await input.fill("ledger");
    await expect(page.getByText("No results found")).toBeVisible();

    for (const name of ["Promising", "Watching", "Rejected", "Revisit later"]) {
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
    }
    await expect(page.getByRole("region", { name: "Preview" })).toHaveCount(0);
    await expect(page.getByText("Select a result to preview its details.")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^(Expand|Collapse)$/ })).toHaveCount(0);

    const reads = chatReads.filter((read) => read.startsWith("GET"));
    expect(reads.some((read) => read.includes("/api/v1/search?"))).toBe(true);
    expect(reads.some((read) => read.includes("/api/v1/conversations?"))).toBe(true);
    expect(reads.filter((read) => !read.includes("surface=business"))).toEqual([]);
    expect(reads.filter((read) => read.includes("include_ledger_groups"))).toEqual([]);
  });
});
