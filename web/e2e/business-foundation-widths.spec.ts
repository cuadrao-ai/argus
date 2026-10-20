import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const WIDTHS = [
  { name: "mobile-small", width: 390 },
  { name: "mobile", width: 480 },
  { name: "tablet", width: 800 },
  { name: "desktop", width: 1100 },
  { name: "large", width: 1440 },
] as const;

const SHOTS = [
  { name: "phone", width: 390 },
  { name: "tablet", width: 800 },
  { name: "desktop", width: 1280 },
] as const;

const phase = process.env.FOUNDATION_SHOT === "before" ? "before" : "after";
const searchEnabled = process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED === "true";

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/biz needs the Business pilot server");

function monthCloseWire(month: string) {
  const [year, index] = month.split("-").map(Number);
  const last = new Date(Date.UTC(year, index, 0)).getUTCDate();
  return {
    month,
    from: `${month}-01`,
    to: `${month}-${String(last).padStart(2, "0")}`,
    closed: false,
    reasons: [],
    missing_rnc: [],
    missing_ncf: [],
    cuentas_por_cobrar: [],
    cuentas_por_pagar: [],
    currencies: [{ currency: "DOP", income_before_itbis: "48500.00", expense_before_itbis: "12300.00", net_result: "36200.00", itbis_owed: "6516.00" }],
  };
}

async function installBusiness(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split("/business/")[1].split("/");
    try {
      let json: unknown;
      if (parts[0] === "space") json = await source.ensureSpace("es-419");
      else if (parts[0] === "spaces") json = { spaces: await source.spaces() };
      else if (parts[0] === "workspace") json = await source.workspace();
      else if (parts[0] === "overview") json = await source.overview(url.searchParams.get("from") ?? "2026-10-01", url.searchParams.get("to") ?? "2026-10-31");
      else if (parts[0] === "receipt-reading") json = { enabled: false, available: true, can_change: true, disclosure: "Permiso", disclosure_token: "a".repeat(64), route: { gateway: "synthetic", interpretation: [], reply: [] }, consented_at: null, revoked_at: null };
      else if (parts[0] === "receipts" && parts.length === 1) json = await source.receiptPage!(url.searchParams.get("view") === "all" ? "all" : "inbox");
      else if (parts[0] === "receipts" && parts.length === 2) json = await source.receipt(parts[1]);
      else if (parts[0] === "email" && parts.length === 1) json = await source.emailIntake();
      else if (parts[0] === "month-close" && parts.length === 1) json = monthCloseWire(url.searchParams.get("month") ?? "2026-10");
      else if (["captures", "expenses"].includes(parts[0]) || parts.join("/") === "email/deliveries") json = { items: [] };
      else return route.fulfill({ status: 404, json: { code: "fixture_only" } });
      return route.fulfill({ json });
    } catch (error) {
      const failure = error as { status?: number; code?: string };
      return route.fulfill({ status: failure.status ?? 500, json: { code: failure.code ?? "fixture_failure" } });
    }
  });
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth - root.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(1);
}

async function openScreen(page: Page, screen: "inicio" | "bandeja" | "receipt") {
  await page.goto(screen === "bandeja" || screen === "receipt" ? "/biz?view=inbox" : "/biz");
  await expect(page.getByTestId("workspace-panel-region")).toBeVisible();
  await expect(page.getByTestId("business-switcher")).toBeVisible();
  if (screen === "inicio") {
    await expect(page.getByRole("heading", { name: "Mi negocio" })).toBeVisible();
    await expect(page.getByTestId("month-close-cards")).toBeVisible();
    await expect(page.getByTestId("business-primary-upload")).toBeVisible();
  }
  if (screen === "bandeja" || screen === "receipt") {
    await expect(page.getByTestId("business-inbox-receipts")).toBeVisible();
  }
  if (screen === "bandeja") {
    await expect(page.getByTestId("business-primary-upload")).toBeVisible();
  }
  if (screen === "receipt") {
    await page.getByTestId("business-inbox-receipts").getByRole("button", { name: /Ferretería La Esquina/ }).click();
    await expect(page.getByRole("heading", { name: "Ferretería La Esquina" })).toBeVisible();
    await expect(page.getByTestId("status-pill")).toBeVisible();
  }
}

for (const shot of SHOTS) {
  test.describe(`foundation shots ${shot.name}`, () => {
    test.use({ viewport: { width: shot.width, height: 900 } });
    for (const screen of ["inicio", "bandeja", "receipt"] as const) {
      test(`${phase} ${screen}`, async ({ page }) => {
        await installBusiness(page);
        await openScreen(page, screen);
        await page.screenshot({
          path: `test-results/business-web-foundation/${phase}-${screen}-${shot.name}.png`,
          fullPage: false,
        });
        if (phase === "after") await noHorizontalScroll(page);
      });
    }
  });
}

for (const band of WIDTHS) {
  test.describe(`foundation scroll ${band.name}`, () => {
    test.use({ viewport: { width: band.width, height: 844 } });
    for (const screen of ["inicio", "bandeja", "receipt"] as const) {
      test(`${screen} has no sideways scroll`, async ({ page }) => {
        test.skip(phase === "before", "baseline capture does not assert the new shell");
        await installBusiness(page);
        await openScreen(page, screen);
        await noHorizontalScroll(page);
        if (band.width < 720) {
          await expect(page.getByTestId("chat-shell-menu-trigger")).toHaveCount(0);
          await expect(page.getByTestId("business-bottom-tabs")).toBeVisible();
          await expect(page.getByRole("button", { name: "Buscar" })).toHaveCount(searchEnabled ? 1 : 0);
          await expect(page.getByTestId("business-phone-account").getByRole("button", { name: "Ajustes" })).toBeVisible();
        }
      });
    }
  });
}
