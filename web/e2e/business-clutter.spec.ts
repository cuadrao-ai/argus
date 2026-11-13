import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";
import { monthCloseWire, OPEN_ITEMS_WIRE } from "./support/month-close-wire";
const baseline = process.env.CUADRAO_CLUTTER_BASELINE === "true";
const evidence = process.env.CUADRAO_CLUTTER_EVIDENCE_DIR;
async function setup(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipt = await source.receipt("rcpt-ferreteria");
  const activity = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 8, needs_attention_count: 1 };
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
    if (path === "overview") return route.fulfill({ json: { ...await source.overview("2026-10-01", "2026-10-31"), totals: [], fiscal_totals: [], without_fiscal_totals: [] } });
    if (path === "receipts") return route.fulfill({ json: { items: [{ ...receipt, status: "review_ready" }], activity } });
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (["email/deliveries", "captures"].includes(path)) return route.fulfill({ json: { items: [] } });
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    if (path === "month-close") return route.fulfill({ json: monthCloseWire(url.searchParams.get("month") ?? "2026-10") });
    if (path === "open-items") return route.fulfill({ json: OPEN_ITEMS_WIRE });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}
for (const width of [1280, 390]) {
  test(`action first and one Bandeja heading at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await setup(page);
    for (const view of ["overview", "inbox"]) {
      await page.goto(view === "overview" ? "/biz" : "/biz?view=inbox");
      await expect(page.getByTestId(view === "overview" ? "home-attention" : "reception-preview")).toBeVisible();
      if (evidence) await page.screenshot({ path: `${evidence}/${baseline ? "before" : "after"}-${view}-${width}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (baseline) continue;
      if (view === "overview") {
        const action = page.getByTestId("home-attention");
        await expect(action.getByTestId("home-attention-count")).toHaveText("8");
        await expect(action.getByTestId("home-attention-rows").locator("li")).toHaveCount(1);
        const cards = page.getByTestId("home-month");
        await expect(cards).toBeVisible();
        if (width === 390) expect((await action.boundingBox())!.y).toBeLessThan((await cards.boundingBox())!.y);
        else expect((await action.boundingBox())!.x).toBeLessThan((await cards.boundingBox())!.x);
        await expect(cards).not.toContainText("RD$ 0");
      } else {
        await expect(page.getByTestId("reception-preview")).toContainText("Ferretería La Esquina");
        await expect(page.getByRole("heading", { name: "Bandeja", exact: true })).toHaveCount(1);
      }
    }
  });
}
