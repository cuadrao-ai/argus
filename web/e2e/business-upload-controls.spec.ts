import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

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
    if (path === "email/deliveries" || path === "captures" || path === "updates") return route.fulfill({ json: { items: [] } });
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
    await expect(page.getByTestId("overview-real-expenses")).toBeVisible();
    await capture("overview");
    if (!baseline) {
      const upload = region.getByTestId("business-primary-upload");
      await expect(upload).toHaveText("Subir recibo");
      await expect(region.getByRole("button", { name: "Subir recibo", exact: true })).toHaveCount(1);
      const bounds = await upload.boundingBox();
      expect(bounds!.height).toBeGreaterThanOrEqual(44);
      expect(bounds!.y).toBeLessThan(400);
      await upload.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog", { name: "Subir recibos", exact: true })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
    await page.goto("/biz?view=inbox");
    const row = page.getByTestId("business-inbox-receipts").locator("li").first();
    await expect(row).toContainText("recibo-interrumpido.jpg");
    await row.scrollIntoViewIfNeeded();
    await capture("inbox");
    if (baseline) return;
    const retry = row.getByRole("button", { name: "Reintentar", exact: true });
    const manual = row.getByRole("button", { name: "Escribir datos", exact: true });
    await expect(manual).toBeVisible();
    for (const button of [retry, manual]) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    state.failed = true;
    await retry.click();
    await expect(row.getByRole("alert")).toContainText("Tu recibo está guardado");
    expect(state.preparations).toBe(1);
    await capture("retry-failed");
    state.failed = false;
    state.hold = true;
    const reads = state.receipts;
    await retry.focus();
    await page.keyboard.press("Enter");
    await expect(retry).toBeDisabled();
    await page.keyboard.press("Enter");
    await expect.poll(() => state.receipts).toBeGreaterThan(reads);
    expect(state.preparations).toBe(2);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await capture("inbox-reduced-motion");
    await manual.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Comercio", { exact: true })).toBeEditable();
    await expect(page).toHaveURL(/receipt=rcpt-unknown/);
    expect(state.preparations).toBe(2);
    await capture("manual-entry");
  });
}

for (const permissions of [{ enterable: false, preparable: false }, { enterable: true, preparable: false }, { enterable: false, preparable: true }]) {
  test(`recovery follows server permission ${JSON.stringify(permissions)}`, async ({ page }) => {
    await setup(page, permissions);
    await page.goto("/biz?view=inbox");
    const row = page.getByTestId("business-inbox-receipts").locator("li").first();
    await expect(row.getByRole("button", { name: "Reintentar", exact: true })).toHaveCount(permissions.preparable ? 1 : 0);
    await expect(row.getByRole("button", { name: "Escribir datos", exact: true })).toHaveCount(permissions.enterable ? 1 : 0);
  });
}

test("English keeps existing canonical labels and accountant has no upload hero", async ({ page }) => {
  await setup(page, { language: "en", owner: false });
  await page.goto("/biz");
  await expect(page.getByTestId("overview-real-expenses")).toBeVisible();
  await expect(page.getByTestId("business-primary-upload")).toHaveCount(0);
  await page.goto("/biz?view=inbox");
  const row = page.getByTestId("business-inbox-receipts").locator("li").first();
  await expect(row.getByRole("button", { name: "Retry", exact: true })).toBeVisible();
  await expect(row.getByRole("button", { name: "Record expense", exact: true })).toBeVisible();
  await expect(page.getByTestId("business-primary-upload")).toHaveCount(0);
});
