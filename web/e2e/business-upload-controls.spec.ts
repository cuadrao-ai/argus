import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";
import { monthCloseWire, OPEN_ITEMS_WIRE } from "./support/month-close-wire";

const baseline = process.env.CUADRAO_UPLOAD_BASELINE === "true";
const evidence = process.env.CUADRAO_UPLOAD_EVIDENCE_DIR;

async function setup(page: Page, options: { enterable?: boolean; preparable?: boolean; language?: "en" | "es-419"; owner?: boolean } = {}) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: options.language ?? "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const original = await source.receipt("rcpt-unknown");
  const receipt = { ...original, filename: "recibo-interrumpido.jpg", attention: "interrupted" as const, preparable: options.preparable ?? true, enterable: options.enterable ?? true };
  const state = { preparations: 0, failed: false, hold: false, receipts: 0 };
  await page.route("**/api/v1/business/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1).map((space) => ({ ...space, role: options.owner === false ? "accountant" : space.role })) } });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "receipts") { state.receipts++; return route.fulfill({ json: { items: [receipt], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 1, needs_attention_count: 1 } } }); }
    if (path === `receipts/${receipt.id}`) return route.fulfill({ json: receipt });
    if (path === `receipts/${receipt.id}/prepare`) {
      state.preparations++;
      if (state.hold) await new Promise((resolve) => setTimeout(resolve, 500));
      return route.fulfill({ status: state.failed ? 503 : 200, json: state.failed ? { code: "synthetic_failure" } : receipt });
    }
    if (path === "receipt-reading") return route.fulfill({ json: { scope_version: 1, enabled: false, available: true, can_change: true, disclosure: "Permiso de prueba", disclosure_token: "a".repeat(64), route: null, consented_at: null, revoked_at: null } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (path === "email/inbox" && route.request().method() === "GET") return route.fulfill({ json: { groups: [{ id: "remitentes_nuevos", items: [] }, { id: "bandeja", items: [] }] } });
    if (path === "email/deliveries" || path === "captures") return route.fulfill({ json: { items: [] } });
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    if (path === "month-close") return route.fulfill({ json: monthCloseWire(new URL(request.url()).searchParams.get("month") ?? "2026-10") });
    if (path === "open-items") return route.fulfill({ json: OPEN_ITEMS_WIRE });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
  return state;
}

for (const width of [1280, 390]) {
  test(`owner upload and failed receipt recovery at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const state = await setup(page);
    const capture = async (name: string) => {
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (evidence) await page.screenshot({ path: `${evidence}/${baseline ? "before" : "after"}-${name}-${width}.png`, fullPage: true });
    };
    await page.goto("/biz");
    const region = page.getByTestId("workspace-panel-region");
    await expect(page.getByTestId("month-close-cards")).toBeVisible();
    await capture("overview");
    if (!baseline) {
      // Inicio repeats no top-bar action: a desktop's Agregar sits in the top bar, a phone's on the screen.
      const upload = page.getByTestId(width === 390 ? "add-menu-page" : "add-menu-header").getByTestId("business-primary-upload");
      await expect(upload).toHaveText("Agregar");
      await expect(page.getByTestId("business-primary-upload")).toHaveCount(1);
      await expect(region.getByTestId("inicio-export")).toHaveCount(0);
      const bounds = await upload.boundingBox();
      expect(bounds!.height).toBeGreaterThanOrEqual(44);
      expect(bounds!.y).toBeLessThan(400);
      await upload.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog", { name: "Agregar", exact: true })).toBeVisible();
      const historyReturned = page.evaluate(() => new Promise<void>((resolve) => window.addEventListener("popstate", () => resolve(), { once: true })));
      await page.keyboard.press("Escape");
      await historyReturned;
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
    await page.goto("/biz?view=inbox");
    const row = page.getByTestId("bandeja-row").first();
    await expect(row).toContainText("recibo-interrumpido.jpg");
    await expect(row.getByTestId("bandeja-row-state")).toContainText("La lectura se detuvo");
    await row.scrollIntoViewIfNeeded();
    await capture("inbox");
    if (baseline) return;
    await expect(row.getByRole("button")).toHaveCount(1);
    await row.getByRole("button").click();
    await expect(page).toHaveURL(/receipt=rcpt-unknown/);
    const retry = page.getByRole("button", { name: "Reintentar con IA", exact: true });
    await expect(retry).toBeVisible();
    expect((await retry.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    state.failed = true;
    await retry.click();
    await expect.poll(() => state.preparations).toBe(1);
    await capture("retry-failed");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await capture("record-reduced-motion");
  });
}

for (const preparable of [false, true]) {
  test(`the record offers Reintentar con IA only when the server says it can prepare (${preparable})`, async ({ page }) => {
    await setup(page, { preparable });
    await page.goto("/biz?view=inbox");
    const row = page.getByTestId("bandeja-row").first();
    await expect(row.getByRole("button")).toHaveCount(1);
    await row.getByRole("button").click();
    await expect(page).toHaveURL(/receipt=rcpt-unknown/);
    await expect(page.getByTestId("receipt-attention")).toBeVisible();
    await expect(page.getByRole("button", { name: "Reintentar con IA", exact: true })).toHaveCount(preparable ? 1 : 0);
  });
}

test("English keeps existing canonical labels and accountant has no upload hero", async ({ page }) => {
  await setup(page, { language: "en", owner: false });
  await page.goto("/biz");
  await expect(page.getByTestId("month-close-cards")).toBeVisible();
  await expect(page.getByTestId("business-primary-upload")).toHaveCount(0);
  await page.goto("/biz?view=inbox");
  const row = page.getByTestId("bandeja-row").first();
  await expect(row.getByTestId("bandeja-row-state")).toContainText("Reading stopped");
  await expect(row.getByRole("button")).toHaveCount(1);
  await expect(page.getByTestId("business-primary-upload")).toHaveCount(0);
  await row.getByRole("button").click();
  await expect(page.getByRole("button", { name: "Try again with AI", exact: true })).toBeVisible();
});
