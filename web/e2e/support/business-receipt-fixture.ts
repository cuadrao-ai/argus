import { expect, type Page, type Route } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../../components/business-app/fixture-data";
import { installBreakpointFixture } from "./breakpoint-fixture";

type Source = ReturnType<typeof createFixtureBusinessDataSource>;
/** A spec's own answer for one Business path: undefined falls through to the fixture data, null means the override fulfilled the route itself. */
export type BusinessOverride = (parts: string[], route: Route, source: Source) => Promise<unknown> | undefined;

const MONTH = {
  month: "2026-10", from: "2026-10-01", to: "2026-10-31", closed: false, reasons: [], missing_rnc: [], missing_ncf: [],
  cuentas_por_cobrar: [], cuentas_por_pagar: [],
  currencies: [{ currency: "DOP", income_before_itbis: "48500.00", expense_before_itbis: "12300.00", net_result: "36200.00", itbis_owed: "6516.00" }],
};

/** The signed-in Spanish Business on fixture data, every API call answered in the page. */
export async function installReceiptBusiness(page: Page, override?: BusinessOverride, theme: "light" | "dark" = "light") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split("/business/")[1].split("/");
    try {
      const custom = override?.(parts, route, source);
      if (custom !== undefined) {
        const json = await custom;
        return json === null ? undefined : route.fulfill({ json });
      }
      let json: unknown;
      if (parts[0] === "space") json = await source.ensureSpace("es-419");
      else if (parts[0] === "spaces") json = { spaces: await source.spaces() };
      else if (parts[0] === "workspace") json = await source.workspace();
      else if (parts[0] === "overview") json = await source.overview(url.searchParams.get("from") ?? "2026-10-01", url.searchParams.get("to") ?? "2026-10-31");
      else if (parts[0] === "receipt-reading") json = { enabled: true, available: true, can_change: true, disclosure: "Permiso", disclosure_token: "a".repeat(64), route: { gateway: "synthetic", interpretation: [], reply: [] }, consented_at: null, revoked_at: null };
      else if (parts[0] === "receipts" && parts.length === 1) json = await source.receiptPage!(url.searchParams.get("view") === "all" ? "all" : "inbox");
      else if (parts[0] === "receipts" && parts[2] === "source") {
        const blob = await source.receiptSource(parts[1]);
        return route.fulfill({ body: Buffer.from(await blob.arrayBuffer()), contentType: blob.type });
      } else if (parts[0] === "receipts" && parts.length === 2) json = await source.receipt(parts[1]);
      else if (parts[0] === "drafts" && parts[2] === "dossier") json = await source.dossier(parts[1]);
      else if (parts[0] === "email" && parts.length === 1) json = await source.emailIntake();
      else if (parts[0] === "month-close" && parts.length === 1) json = MONTH;
      else if (parts.join("/") === "fiscal-profile/fields") json = { "606": [], "607": [] };
      else if (["captures", "updates", "expenses"].includes(parts[0]) || parts.join("/") === "email/deliveries") json = { items: [] };
      else return route.fulfill({ status: 404, json: { code: "fixture_only" } });
      return route.fulfill({ json });
    } catch (error) {
      const failure = error as { status?: number; code?: string };
      return route.fulfill({ status: failure.status ?? 500, json: { code: failure.code ?? "fixture_failure" } });
    }
  });
  return source;
}

/** Opens Bandeja and the receipt whose row names the given merchant. */
export async function openReceipt(page: Page, merchant: RegExp) {
  await page.goto("/biz?view=inbox");
  await expect(page.getByTestId("business-inbox-receipts")).toBeVisible();
  await page.getByTestId("business-inbox-receipts").getByRole("button", { name: merchant }).click();
  await expect(page.getByTestId("business-record-review")).toBeVisible();
}

export async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

/** Every listed element is at least 44 by 44 CSS pixels. */
export async function expectTargets(page: Page, selector: string) {
  const small = await page.locator(selector).evaluateAll((elements) => elements
    .map((element) => ({ html: element.outerHTML.slice(0, 120), box: element.getBoundingClientRect() }))
    .filter(({ box }) => box.width > 0 && (box.width < 44 || box.height < 44))
    .map(({ html, box }) => `${Math.round(box.width)}x${Math.round(box.height)} ${html}`));
  expect(small).toEqual([]);
}

export const SHOT_DIR = "test-results/design-receipt-detail";
