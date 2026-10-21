import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const evidence = process.env.CUADRAO_CONSENT_EVIDENCE_DIR;

const COPY = {
  title: "Antes de empezar",
  body: "Cuadrao guarda los recibos, facturas y datos que subes para leerlos, organizarlos y preparar tus reportes. Solo tú y las personas que invites a tu negocio pueden verlos. Puedes pedir que borremos tus datos cuando quieras.",
  optIn: "Entiendo y acepto que Cuadrao use mis datos para esto.",
  continue: "Continuar",
  privacy: "Ver aviso de privacidad",
};

/** The API's memory of acceptances: it outlives every page and browser. */
type Server = { accepted: Map<string, string>; holdAccept: Promise<void> | null };

async function openBusiness(page: Page, server: Server) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true, consent: "required" });
  const source = createFixtureBusinessDataSource({ chatAvailable: true });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    if (path === "consent" && route.request().method() === "GET") {
      const version = url.searchParams.get("version") ?? "";
      return route.fulfill({ json: { version, accepted_at: server.accepted.get(version) ?? null } });
    }
    if (path === "consent") {
      const { version } = route.request().postDataJSON() as { version: string };
      await server.holdAccept;
      if (!server.accepted.has(version)) server.accepted.set(version, new Date().toISOString());
      return route.fulfill({ json: { version, accepted_at: server.accepted.get(version) } });
    }
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de José" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, needs_attention_count: 0 } } });
    if (path === "receipt-reading") return route.fulfill({ json: { scope_version: 1, enabled: false, available: true, can_change: true, disclosure: "Permiso de prueba", disclosure_token: "a".repeat(64), route: null, consented_at: null, revoked_at: null } });
    if (path === "email") return route.fulfill({ json: { enabled: false, receiving_address: null } });
    if (path === "email/deliveries" || path === "captures") return route.fulfill({ json: { items: [] } });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
  await page.goto("/biz");
}

async function capture(page: Page, name: string) {
  if (!evidence) return;
  await page.screenshot({ path: `${evidence}/${name}.png`, fullPage: true });
}

for (const width of [1440, 390]) {
  test(`consent is asked once and kept on the server, at ${width}px`, async ({ page, browser }) => {
    const server: Server = { accepted: new Map(), holdAccept: null };
    await page.setViewportSize({ width, height: 900 });
    await openBusiness(page, server);

    const screen = page.getByTestId("business-consent-screen");
    await expect(screen.getByRole("heading", { level: 1 })).toHaveText(COPY.title);
    await expect(screen.getByText(COPY.body, { exact: true })).toBeVisible();
    await expect(screen.getByText(COPY.optIn, { exact: true })).toBeVisible();
    await expect(screen.getByText(COPY.privacy)).toHaveCount(0);
    const go = screen.getByRole("button", { name: COPY.continue, exact: true });
    await expect(go).toBeDisabled();
    await expect(page.locator("#business-overview-title")).toHaveCount(0);
    await capture(page, `consent-${width}`);

    await screen.getByRole("checkbox").check();
    await expect(go).toBeEnabled();
    await screen.getByRole("checkbox").uncheck();
    await expect(go).toBeDisabled();
    await screen.getByRole("checkbox").check();

    let release!: () => void;
    server.holdAccept = new Promise((resolve) => { release = resolve; });
    await go.click();
    const loading = page.getByTestId("business-consent-loading");
    await expect(loading.locator('[data-layout="overview"]')).toBeVisible();
    await capture(page, `skeleton-${width}`);
    release();
    server.holdAccept = null;
    await expect(page.locator("#business-overview-title")).toBeVisible();
    expect(server.accepted.size).toBe(1);
    await capture(page, `inicio-${width}`);

    await page.reload();
    await expect(page.locator("#business-overview-title")).toBeVisible();
    await expect(page.getByTestId("business-consent-screen")).toHaveCount(0);

    const fresh: BrowserContext = await browser.newContext({ viewport: { width, height: 900 } });
    try {
      const other = await fresh.newPage();
      await openBusiness(other, server);
      await expect(other.locator("#business-overview-title")).toBeVisible();
      await expect(other.getByTestId("business-consent-screen")).toHaveCount(0);
    } finally {
      await fresh.close();
    }
  });
}
