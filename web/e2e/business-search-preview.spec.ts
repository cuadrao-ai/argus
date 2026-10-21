import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

// Business is Spanish only, so every string below is the es-419 copy.
async function openPreview(page: Page, language: "en" | "es-419" = "es-419", query = "") {
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
  // The preview starts with chat off, as the product does; the chats test asks for it with ?chat=on.
  await page.goto(`/dev/business-preview${query}`);
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
    const input = await openSearch(page, "Busca comercio, monto o nota");

    await input.fill("nube hosting");
    const expenses = results(page).getByRole("group", { name: "Gastos" });
    await expect(expenses.getByRole("button")).toHaveCount(1);
    await expect(expenses.getByRole("button")).toContainText("Nube Hosting");
    await expect(expenses.getByRole("button")).toContainText("24.00");
    await expect(results(page).getByRole("group", { name: "Recibos" })).toHaveCount(0);
    await expect(page.getByText(/No encontramos nada con/)).toHaveCount(0);

    await page.keyboard.press("ArrowDown");
    await expect(expenses.getByRole("button")).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(input).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    await expect(input).toHaveCount(0);
    await expect(panelHeading(page, "Transacciones")).toBeVisible();
    const tray = page.getByTestId("side-drawer");
    await expect(tray.getByRole("heading", { name: "Nube Hosting" })).toBeVisible();
    const download = page.waitForEvent("download");
    await tray.getByRole("link", { name: "Descargar" }).click();
    expect((await download).suggestedFilename()).toBeTruthy();
  });

  test("a receipt found by merchant or file name opens its review", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Busca comercio, monto o nota");

    await input.fill("papeleria-oct");
    const receipts = results(page).getByRole("group", { name: "Recibos" });
    await expect(receipts.getByRole("button")).toContainText("Papelería Central");
    await input.fill("ferreteria");
    await expect(receipts.getByRole("button")).toContainText("Ferretería La Esquina");
    await expect(receipts.getByRole("button")).toContainText("Listo para revisar");
    await receipts.getByRole("button").click();
    await page.getByRole("button", { name: "Abrir registro", exact: true }).click();

    await expect(input).toHaveCount(0);
    await expect(page.getByTestId("side-drawer").getByRole("heading", { name: "Ferretería La Esquina", level: 2 })).toBeVisible();
    await expect(page.getByLabel("Pagado desde")).toBeVisible();
  });

  test("an expense without a receipt opens its row in Transacciones", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Busca comercio, monto o nota");

    await input.fill("estacion");
    await results(page).getByRole("button", { name: /Estación Ruta 3/ }).click();
    await page.getByRole("button", { name: "Abrir registro", exact: true }).click();

    await expect(panelHeading(page, "Transacciones")).toBeVisible();
    await expect(page.locator('tr[aria-selected="true"]')).toContainText("Estación Ruta 3");
  });

  test("owner-funded expense keeps its Spanish funding, date and category in search and its list", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Busca comercio, monto o nota");
    await input.fill("comedor");
    const hit = results(page).getByRole("button", { name: /Comedor Doña Ana/ });
    await expect(hit).toContainText("Dinero del dueño");
    await expect(hit).toContainText("Comidas");
    const detail = await hit.innerText();
    await expect(hit).not.toContainText("Cuenta corriente");
    if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/owner-funded-search-spanish.png`, fullPage: true });
    await hit.click();
    await page.getByRole("button", { name: "Abrir registro", exact: true }).click();
    const row = page.locator('tr[aria-selected="true"]');
    await expect(row).toContainText("Comedor Doña Ana");
    await expect(row).toContainText("Dinero del dueño");
    await expect(row).toContainText("Comidas");
    const date = detail.match(/\d{1,2} [a-z]+ \d{4}/)?.[0];
    expect(date).toBeTruthy();
    // The list names a day of this year without the year.
    await expect(row).toContainText(date!.replace(/ \d{4}$/, ""));
    await expect(row).not.toContainText("Cuenta corriente");
    if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/owner-funded-expenses-spanish.png`, fullPage: true });
  });

  test("no match keeps the existing empty state with a Business hint", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Busca comercio, monto o nota");

    await input.fill("zzqqxx");
    await expect(page.getByText("No encontramos nada con «zzqqxx».")).toBeVisible();
    await expect(page.getByText("Busca por comercio, monto, categoría, cuenta o el texto de una nota.")).toBeVisible();
    await expect(results(page)).toHaveCount(0);
  });

  test("a failed search says so and retries in place", async ({ page }) => {
    await openPreview(page);
    const input = await openSearch(page, "Busca comercio, monto o nota");

    await page.evaluate(() => {
      (globalThis as { __businessFixtureFailNextWrite?: string }).__businessFixtureFailNextWrite = "server_error";
    });
    await input.fill("hosting");
    await expect(page.getByRole("alert").filter({ hasText: "No pudimos buscar en tu negocio." })).toBeVisible();
    await page.getByRole("button", { name: "Intentar la búsqueda de nuevo" }).first().click();
    await expect(results(page).getByRole("button", { name: /Nube Hosting/ })).toBeVisible();
  });

  test("Spanish shows the same results in Spanish", async ({ page }) => {
    await openPreview(page, "en");
    const input = await openSearch(page, "Busca comercio, monto o nota");

    await input.fill("hosting");
    await expect(results(page).getByRole("group", { name: "Gastos" })).toContainText("Nube Hosting");
    await input.fill("zzqqxx");
    await expect(page.getByText("Busca por comercio, monto, categoría, cuenta o el texto de una nota.")).toBeVisible();
  });
});

test.describe("Business chats in the omnisearch", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("reads only Business chats and offers no decision filters", async ({ page }) => {
    const chatReads: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (/\/api\/v1\/(conversations|history|search)$/.test(url.pathname)) {
        chatReads.push(`${request.method()} ${url.pathname}${url.search}`);
      }
    });
    await openPreview(page, "es-419", "?chat=on");
    // Answer like the server: decision filters only when they are asked for.
    await page.route("**/api/v1/search?**", (route) => {
      const asked = new URL(route.request().url()).searchParams.get("include_ledger_groups");
      const ledger_groups = asked === "true"
        ? ["promising", "watching", "rejected", "revisit_later"].map((decision_state) => ({ decision_state, count: 1 }))
        : null;
      return route.fulfill({ json: { items: [], next_cursor: null, ledger_groups } });
    });
    const input = await openSearch(page, "Busca comercio, monto o nota");
    await input.fill("ledger");
    await expect(page.getByText(/No encontramos nada con/)).toBeVisible();

    for (const name of ["Prometedores", "En seguimiento", "Rechazados", "Revisar luego", "Promising", "Watching", "Rejected", "Revisit later"]) {
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
    }

    const reads = chatReads.filter((read) => read.startsWith("GET"));
    expect(reads.some((read) => read.includes("/api/v1/search?"))).toBe(true);
    expect(reads.some((read) => read.includes("/api/v1/conversations?"))).toBe(true);
    expect(reads.filter((read) => !read.includes("surface=business"))).toEqual([]);
    expect(reads.filter((read) => read.includes("include_ledger_groups"))).toEqual([]);
  });
});
