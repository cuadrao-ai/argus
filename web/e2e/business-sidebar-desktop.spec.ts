import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/biz needs the Business pilot server");

const SHOTS = process.env.SIDEBAR_FIX_SHOTS === "true";

async function installBusiness(page: Page, storedMode: string | null) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.addInitScript((mode) => {
    if (mode) window.localStorage.setItem("argus:sidebar_mode", mode);
    else window.localStorage.removeItem("argus:sidebar_mode");
  }, storedMode);
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split("/business/")[1].split("/");
    let json: unknown;
    if (parts[0] === "consent") return fulfillAcceptedBusinessConsent(route);
    if (parts[0] === "space") json = await source.ensureSpace("es-419");
    else if (parts[0] === "spaces") json = { spaces: await source.spaces() };
    else if (parts[0] === "workspace") json = await source.workspace();
    else if (parts[0] === "overview") json = await source.overview("2026-10-01", "2026-10-31");
    else if (parts[0] === "receipt-reading") json = { enabled: false, available: true, can_change: true, disclosure: "Permiso", disclosure_token: "a".repeat(64), route: { gateway: "synthetic", interpretation: [], reply: [] }, consented_at: null, revoked_at: null };
    else if (parts[0] === "receipts" && parts.length === 1) json = await source.receiptPage!(url.searchParams.get("view") === "all" ? "all" : "inbox");
    else if (parts[0] === "email" && parts.length === 1) json = await source.emailIntake();
    else if (parts[0] === "month-close") json = { month: "2026-10", from: "2026-10-01", to: "2026-10-31", closed: false, reasons: [], missing_rnc: [], missing_ncf: [], cuentas_por_cobrar: [], cuentas_por_pagar: [], currencies: [{ currency: "DOP", income_before_itbis: "48500.00", expense_before_itbis: "12300.00", net_result: "36200.00", itbis_owed: "6516.00" }] };
    else if (["captures", "updates", "expenses"].includes(parts[0]) || parts.join("/") === "email/deliveries") json = { items: [] };
    else return route.fulfill({ status: 404, json: { code: "fixture_only" } });
    return route.fulfill({ json });
  });
}

async function railGeometry(page: Page) {
  return page.evaluate(() => {
    const nav = document.querySelector('[data-testid="business-sidebar-nav"]') as HTMLElement;
    const aside = nav.closest("aside") as HTMLElement;
    const box = (element: Element) => element.getBoundingClientRect();
    const labels = /^(Inicio|Bandeja|Gastos|Novedades|Acceso|Ajustes)/;
    const rows = [...aside.querySelectorAll<HTMLButtonElement>("button")].filter((button) => labels.test(button.textContent?.trim() ?? ""));
    const active = rows.find((row) => row.getAttribute("aria-current") === "page") ?? null;
    return {
      width: Math.round(box(aside).width),
      background: getComputedStyle(aside).backgroundColor,
      borderRight: getComputedStyle(aside).borderRightWidth,
      navTop: Math.round(box(nav).top),
      navGapAboveFirstRow: Math.round(box(rows[0]).top - (aside.querySelector('[data-testid="business-switcher"]')?.getBoundingClientRect().bottom ?? 0)),
      rowHeights: rows.map((row) => Math.round(box(row).height)),
      rowLabels: rows.map((row) => row.textContent?.replace(/Ctrl.*$|⌘.*$/, "").replace(/\d+$/, "").trim()),
      footerBottomGap: Math.round(box(aside).bottom - box(rows[rows.length - 1]).bottom),
      activeHeight: active ? Math.round(box(active).height) : null,
      activeBackground: active ? getComputedStyle(active).backgroundColor : null,
      activeColor: active ? getComputedStyle(active).color : null,
      switcherName: aside.querySelector('[data-testid="business-current-name"]')?.textContent ?? null,
    };
  });
}

for (const width of [1440, 1024]) {
  test.describe(`Business rail at ${width}`, () => {
    test.use({ viewport: { width, height: 900 } });

    for (const storedMode of [null, "collapsed", "hover"]) {
      test(`opens labeled at 240px with a saved ${storedMode ?? "empty"} preference`, async ({ page }) => {
        await installBusiness(page, storedMode);
        await page.goto("/biz");
        await expect(page.getByTestId("business-current-name")).toBeVisible();
        await page.waitForTimeout(400);
        const rail = await railGeometry(page);
        expect(rail).toEqual({
          width: 240,
          background: "rgb(247, 245, 238)",
          borderRight: "1px",
          navTop: 108,
          navGapAboveFirstRow: 8,
          rowHeights: [44, 44, 44, 44, 44, 44],
          rowLabels: ["Inicio", "Bandeja", "Gastos", "Novedades", "Acceso", "Ajustes"],
          footerBottomGap: 12,
          activeHeight: 44,
          activeBackground: "rgb(227, 235, 225)",
          activeColor: "rgb(47, 90, 73)",
          switcherName: expect.any(String),
        });
        if (SHOTS && width === 1440 && storedMode === null) {
          await page.screenshot({ path: "test-results/sidebar-fix/biz-1440-expanded-local-fixture.png" });
        }
      });
    }

    test("collapses to a 64px icon stack only through the toggle", async ({ page }) => {
      await installBusiness(page, null);
      await page.goto("/biz");
      await expect(page.getByTestId("business-current-name")).toBeVisible();
      await page.getByTestId("business-sidebar-nav").getByRole("button", { name: /Bandeja/ }).click();
      await page.mouse.move(width - 10, 450);
      expect((await railGeometry(page)).width).toBe(240);
      await page.getByTestId("sidebar-rail-toggle").click();
      await page.waitForTimeout(400);
      const rail = await railGeometry(page);
      expect({ width: rail.width, rowHeights: rail.rowHeights, activeHeight: rail.activeHeight, navTop: rail.navTop }).toEqual({
        width: 64,
        rowHeights: [44, 44, 44, 44, 44, 44],
        activeHeight: 44,
        navTop: 108,
      });
      await page.getByTestId("business-sidebar-nav").getByRole("button", { name: "Gastos" }).hover();
      await expect(page.getByRole("tooltip").filter({ hasText: "Gastos" })).toBeVisible();
      if (SHOTS && width === 1440) {
        await page.screenshot({ path: "test-results/sidebar-fix/biz-1440-collapsed-local-fixture.png" });
      }
      await page.getByTestId("sidebar-rail-toggle").click();
      await page.waitForTimeout(400);
      expect((await railGeometry(page)).width).toBe(240);
    });
  });
}

test.describe("Business on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("keeps the bottom tabs and no rail", async ({ page }) => {
    await installBusiness(page, null);
    await page.goto("/biz");
    await expect(page.getByTestId("business-switcher")).toBeVisible();
    await expect(page.getByTestId("month-close-cards")).toBeVisible();
    await expect(page.locator("aside")).toHaveCount(0);
    if (SHOTS) await page.screenshot({ path: "test-results/sidebar-fix/biz-390-local-fixture.png" });
  });
});
