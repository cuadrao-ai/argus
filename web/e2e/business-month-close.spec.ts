import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";
import { monthCloseWire } from "./support/month-close-wire";

test.describe("Inicio with settlement off", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  async function openWire(page: Page, phase: "ready" | "empty" | "failed" = "ready") {
    await page.route("**/*", (route) => (["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort()));
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    const state = { openItems: 0, monthReads: 0, phase };
    await page.route("**/api/v1/business/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname.split("/business/")[1];
      if (path === "workspace") return route.fulfill({ json: { ...await source.workspace(), settlement_available: false } });
      if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
      if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
      if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
      if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, needs_attention_count: 0 } } });
      if (path === "receipt-reading") return route.fulfill({ json: { enabled: false, available: true, can_change: false } });
      if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
      if (path === "email/deliveries" || path === "captures") return route.fulfill({ json: { items: [] } });
      if (path === "consent") return fulfillAcceptedBusinessConsent(route);
      if (path === "month-close") {
        state.monthReads++;
        if (state.phase === "failed") return route.fulfill({ status: 503, json: { code: "synthetic_failure" } });
        const wire = monthCloseWire(url.searchParams.get("month") ?? "2026-10");
        if (state.phase === "empty") return route.fulfill({ json: { ...wire, earliest_month: null, currencies: [], cuentas_por_cobrar: [] } });
        return route.fulfill({ json: { ...wire, earliest_month: "2026-01", cuentas_por_cobrar: [], missing_fiscal_rows: [{ family: "purchase", currency: "DOP", count: 3, by_currency: false }], currencies: wire.currencies.map(block => ({ ...block, net_result_final: true, itbis_charged: "8730.00", itbis_charged_minor: 873000, documents_counted: 4, documents_total: 4, documents_in_bandeja: 0 })) } });
      }
      if (path === "open-items") { state.openItems++; return route.fulfill({ status: 404, json: { code: "business_settlement_unavailable" } }); }
      return route.fulfill({ status: 404, json: { code: "fixture_only" } });
    });
    await page.goto("/biz");
    await expect(page.getByTestId("home-month-body")).toHaveAttribute("data-state", phase === "failed" ? "error" : "ready");
    return state;
  }

  for (const width of [1280, 390]) {
    test(`the approved month, two ITBIS totals and fiscal rows show directly at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const state = await openWire(page);
      for (const [id, amount] of [["income", "48500.00"], ["expenses", "12300.00"], ["net", "36200.00"], ["itbis-sales", "8730.00"], ["itbis-purchases", "6516.00"]]) {
        await expect(page.getByTestId(`home-month-${id}`)).toHaveAttribute("data-amount", amount);
      }
      await expect(page.getByTestId("home-month-fiscal")).toContainText("3");
      await expect(page.getByTestId("home-month-fiscal-open")).toBeVisible();
      for (const id of ["month-close-blockers", "month-close-close", "month-close-steps-note", "month-close-money", "month-close-receivable", "month-close-payable"]) await expect(page.getByTestId(id)).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Ver cuáles", exact: true })).toHaveCount(0);
      expect(state.openItems).toBe(0);
      const month = await page.getByTestId("month-close-month").innerText();
      await page.getByTestId("month-close-month-prev").click();
      await expect(page.getByTestId("month-close-month")).not.toHaveText(month);
      await expect(page.getByTestId("home-month-itbis-sales")).toHaveAttribute("data-amount", "8730.00");
      expect(state.monthReads).toBeGreaterThan(1);
      expect(state.openItems).toBe(0);
    });
  }

  test("an empty month shows its first-day state rather than settlement rows", async ({ page }) => {
    const state = await openWire(page, "empty");
    await expect(page.getByTestId("home-month-first-day")).toBeVisible();
    await expect(page.getByTestId("home-month-net")).toHaveAttribute("data-amount", "0");
    await expect(page.getByTestId("home-month-fiscal")).toHaveCount(0);
    expect(state.openItems).toBe(0);
  });

  test("a failed month read retries inside the month card", async ({ page }) => {
    const state = await openWire(page, "failed");
    const month = page.getByTestId("home-month-body");
    await expect(month.getByRole("alert")).toContainText("No pudimos cargar el mes");
    state.phase = "ready";
    await month.getByRole("button", { name: "Reintentar", exact: true }).click();
    await expect(month).toHaveAttribute("data-state", "ready");
    expect(state.monthReads).toBe(2);
    expect(state.openItems).toBe(0);
  });

  test("being offline docks one banner at the top and leaves the toasts alone", async ({ page }) => {
    await openWire(page);
    await expect(page.getByTestId("connection-banner")).toHaveCount(0);
    await page.context().setOffline(true);
    await expect(page.getByTestId("connection-banner")).toBeVisible();
    await expect(page.getByTestId("connection-banner")).toHaveCount(1);
    await expect(page.getByTestId("toast-viewport")).not.toContainText(/conexión|internet/i);
    await page.context().setOffline(false);
    await expect(page.getByTestId("connection-banner")).toHaveCount(0);
  });

});
