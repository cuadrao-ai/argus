import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

test.skip(process.env.BANDEJA_FIRST_SCREEN !== "1", "Runs with the Bandeja first-screen config");

async function setup(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipt = await source.receipt("rcpt-ferreteria");
  const activity = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 1, needs_attention_count: 0 };
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
    if (path === "overview") return route.fulfill({ json: { ...await source.overview("2026-10-01", "2026-10-31"), totals: [], fiscal_totals: [], without_fiscal_totals: [] } });
    if (path === "receipts") return route.fulfill({ json: { items: [receipt], activity } });
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (["email/deliveries", "captures"].includes(path)) return route.fulfill({ json: { items: [] } });
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}

for (const width of [1280, 390]) {
  test(`owner sees the receipt and one Agregar on the first Bandeja screen at ${width}`, async ({ page }) => {
    const height = width === 390 ? 844 : 900;
    await page.setViewportSize({ width, height });
    await setup(page);
    await page.goto("/biz?view=inbox");
    const receipts = page.getByTestId("business-inbox-receipts");
    // A desktop's Agregar sits in the top bar; a phone's at the top of the screen.
    const upload = page.getByTestId(width === 390 ? "add-menu-page" : "add-menu-header").getByTestId("business-primary-upload");
    const segments = page.getByTestId("bandeja-segments");
    await expect(receipts).toBeVisible();
    await expect(upload).toHaveText("Agregar");
    await expect(page.getByTestId("business-primary-upload")).toHaveCount(1);
    await expect(page.getByTestId(width === 390 ? "add-menu-header" : "add-menu-page")).toHaveCount(0);
    await expect(page.getByTestId("bandeja-emails-line")).toHaveCount(0);
    await expect(page.getByTestId("bandeja-segments").locator('[data-segment="review"]')).toHaveText(width === 390 ? "Revisar1" : "Por revisar1");
    await expect(page.getByText("necesita tu atención")).toHaveCount(0);
    await expect(page.getByText(/Revisar \d+ recibo/)).toHaveCount(0);
    await expect(receipts).toContainText("RD$");
    await expect(receipts).not.toContainText("DOP");
    await expect(page.getByTestId("receipt-reading-control")).toHaveCount(0);
    await expect(page.getByText("Nada aquí es un gasto hasta que lo confirmes.")).toHaveCount(0);
    await expect(page.getByTestId("email-address")).toHaveCount(0);
    const receiptBox = await receipts.boundingBox();
    const uploadBox = await upload.boundingBox();
    expect(receiptBox).toBeTruthy();
    expect(uploadBox).toBeTruthy();
    expect(uploadBox!.height).toBeGreaterThanOrEqual(44);
    expect(uploadBox!.y).toBeLessThan(receiptBox!.y);
    expect(receiptBox!.y).toBeLessThan(height);
    await page.screenshot({ path: test.info().outputPath(`after-inbox-${width}.png`) });
    await segments.locator('[data-segment="emails"]').click();
    await expect(page.getByTestId("bandeja-emails").getByTestId("email-copy-address")).toHaveText("Copiar dirección");
    await expect(receipts).toHaveCount(0);
  });
}
