import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

async function setup(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "en", theme: "light", emptyChat: true });
  await page.addInitScript(() => {
    window.localStorage.setItem("i18nextLng", "en");
    const seen: string[] = [];
    const current = () => document.documentElement.lang;
    seen.push(current());
    new MutationObserver(() => seen.push(current())).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["lang"],
    });
    Object.assign(window, { __businessLangs: seen });
  });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipt = await source.receipt("rcpt-ferreteria");
  const activity = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 1, needs_attention_count: 0 };
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "My business" } });
    if (path === "spaces") {
      const spaces = (await source.spaces()).slice(0, 1).map((space) => ({ ...space, name: "My business" }));
      return route.fulfill({ json: { spaces } });
    }
    if (path === "overview") return route.fulfill({ json: { ...await source.overview("2026-10-01", "2026-10-31"), totals: [], fiscal_totals: [], without_fiscal_totals: [] } });
    if (path === "receipts") return route.fulfill({ json: { items: url.searchParams.get("view") === "all" ? [receipt] : [receipt], activity } });
    if (path === `receipts/${receipt.id}`) return route.fulfill({ json: receipt });
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (["email/deliveries", "captures", "updates"].includes(path)) return route.fulfill({ json: { items: [] } });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}

test("an en-US browser with stored English and an English account still shows Spanish Business", async ({ page }, testInfo) => {
  await setup(page);
  const response = await page.goto("/biz");
  const html = await response?.text();
  expect(html ?? "").toMatch(/<html[^>]*\slang="es"/);
  expect(html ?? "").not.toMatch(/<html[^>]*\slang="en"/);
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  const langs = await page.evaluate(() => (window as Window & { __businessLangs?: string[] }).__businessLangs ?? []);
  expect(langs.every((lang) => lang === "es")).toBe(true);
  expect(await page.evaluate(() => window.localStorage.getItem("i18nextLng"))).toBe("en");
  const overview = page.locator("#business-overview-title");
  await expect(overview).toHaveText("Mi negocio");
  await expect(page.getByTestId("overview-inbox")).toContainText("1 por revisar");
  await expect(page.getByTestId("overview-inbox")).toContainText("Abrir la bandeja");
  await expect(page.getByTestId("overview-real-expenses")).toContainText("Gastos reales");
  await expect(page.getByTestId("overview-real-expenses")).toContainText("Todavía no hay gastos guardados en este período.");
  await expect(page.getByTestId("overview-fiscal-expenses")).toContainText("Con valor fiscal");
  await expect(page.getByTestId("overview-fiscal-expenses")).toContainText("Ninguno con valor fiscal en este período.");
  await expect(page.getByTestId("business-sidebar-nav")).toContainText("Resumen");
  await expect(page.getByTestId("business-primary-upload")).toHaveText("Subir recibo");
  await expect(page.getByRole("button", { name: "Registrar gasto" }).first()).toBeVisible();
  for (const english of ["Upload receipts", "My business", "Record expense", "Open inbox", "Actual expenses"]) {
    await expect(page.getByText(english, { exact: true })).toHaveCount(0);
  }
  await page.screenshot({ path: testInfo.outputPath("overview-en-us.png"), fullPage: true });

  await page.getByTestId("business-primary-upload").click();
  const upload = page.getByRole("dialog", { name: "Subir recibos" });
  await expect(upload).toBeVisible();
  await expect(upload).not.toContainText("Upload receipts");
  await page.screenshot({ path: testInfo.outputPath("upload-en-us.png") });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByRole("button", { name: "Registrar gasto" }).click();
  const record = page.getByRole("dialog", { name: "Registrar gasto" });
  await expect(record).toBeVisible();
  for (const label of ["Comercio", "Total en DOP", "Fecha", "Pagado desde", "Categoría"]) {
    await expect(record).toContainText(label);
  }
  await expect(record).not.toContainText("Record expense");
  await expect(record).not.toContainText("Merchant");
  await expect(record).not.toContainText("Paid from");
  await page.screenshot({ path: testInfo.outputPath("record-expense-en-us.png") });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByTestId("overview-inbox").click();
  await page.getByTestId("business-inbox-receipts").getByRole("button", { name: /Ferretería La Esquina/ }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  const review = page.getByRole("main");
  await expect(review).toContainText("Comercio");
  await expect(review).toContainText("Fecha");
  await expect(review).toContainText("Categoría");
  await expect(review).toContainText("Moneda");
  await expect(review).toContainText("Pagado desde");
  await expect(review).not.toContainText("Merchant");
  await expect(review).not.toContainText("Paid from");
  await page.screenshot({ path: testInfo.outputPath("review-en-us.png"), fullPage: true });
});
