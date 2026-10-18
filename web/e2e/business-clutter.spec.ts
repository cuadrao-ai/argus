import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";
const baseline = process.env.CUADRAO_CLUTTER_BASELINE === "true";
const evidence = process.env.CUADRAO_CLUTTER_EVIDENCE_DIR;
type Scenario = "pending" | "new" | "approved" | "dismissed" | "filtered" | "unknown" | "unapproved" | "unavailable";
async function setup(page: Page, scenario: Scenario = "pending", language: "en" | "es-419" = "es-419") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipt = await source.receipt("rcpt-ferreteria");
  const all = scenario === "new" ? [] : [{ ...receipt, status: scenario === "approved" ? "confirmed" : scenario === "dismissed" ? "dismissed" : "review_ready" }];
  const activity = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: scenario === "pending" || scenario === "filtered" ? 8 : 0, needs_attention_count: scenario === "pending" ? 1 : 0 };
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
    if (path === "overview") return route.fulfill({ json: { ...await source.overview("2026-10-01", "2026-10-31"), totals: [], fiscal_totals: [], without_fiscal_totals: [] } });
    if (path === "receipts" && url.searchParams.get("view") === "all" && scenario === "unavailable") return route.fulfill({ status: 503, json: { code: "fixture_unavailable" } });
    if (path === "receipts") return route.fulfill({ json: { items: url.searchParams.get("view") === "all" ? all : scenario === "pending" ? [receipt] : [], activity: scenario === "unknown" ? null : activity } });
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (["email/deliveries", "captures", "updates"].includes(path)) return route.fulfill({ json: { items: [] } });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}
for (const width of [1280, 390]) {
  test(`action first and one inbox subhead at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await setup(page);
    for (const view of ["overview", "inbox"]) {
      await page.goto(view === "overview" ? "/biz" : "/biz?view=inbox");
      await expect(page.getByTestId(view === "overview" ? "overview-real-expenses" : "business-inbox-receipts")).toBeVisible();
      if (evidence) await page.screenshot({ path: `${evidence}/${baseline ? "before" : "after"}-${view}-${width}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (baseline) continue;
      if (view === "overview") {
        const action = page.getByTestId("overview-inbox");
        await expect(action).toContainText("8 por revisar");
        await expect(action).toContainText("1 con problema");
        expect((await action.boundingBox())!.y).toBeLessThan((await page.getByTestId("overview-real-expenses").boundingBox())!.y);
        await expect(page.getByTestId("overview-real-expenses")).not.toContainText("RD$ 0");
      } else {
        await expect(page.getByTestId("receipt-reading-control")).toHaveCount(0);
        await expect(page.getByText(/Nada aquí es un gasto hasta que lo confirmes\./)).toHaveCount(1);
      }
    }
  });
}
for (const scenario of ["new", "approved", "dismissed", "filtered", "unknown", "unapproved", "unavailable"] as const) {
  test(`empty inbox requires saved approval proof for ${scenario}`, async ({ page }) => {
    await setup(page, scenario);
    await page.goto("/biz?view=inbox");
    const empty = page.getByTestId("business-inbox-empty");
    await expect(empty).toBeVisible();
    if (scenario === "approved") await expect(empty).toContainText("Todo aprobado. Pa'que cuadre.");
    else { await expect(empty).not.toContainText("Todo aprobado"); await expect(empty).toContainText("Sube un recibo"); }
  });
}
test("English keeps the existing empty copy", async ({ page }) => {
  await setup(page, "approved", "en");
  await page.goto("/biz?view=inbox");
  await expect(page.getByTestId("business-inbox-empty")).toContainText("Upload a receipt");
  await expect(page.getByTestId("business-inbox-empty")).not.toContainText("Todo aprobado");
});
