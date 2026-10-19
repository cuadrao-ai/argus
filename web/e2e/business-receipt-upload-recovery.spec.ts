import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

async function openIntake(page: Page) {
  // All external traffic is refused. Every Business request is fixture-only.
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const attempts: { key: string; consent: string | undefined; bytes: Buffer }[] = [];
  const state = { status: 422 };
  await page.route("**/api/v1/business/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.split("/business/")[1];
    if (path === "workspace") {
      const workspace = await source.workspace();
      return route.fulfill({ json: { ...workspace, receipt_limits: { ...workspace.receipt_limits, media_types: [...workspace.receipt_limits.media_types, "application/xml", "text/xml"] } } });
    }
    if (path === "receipts" && request.method() === "POST") {
      attempts.push({ key: request.headers()["idempotency-key"], consent: request.headers()["x-extraction-consent"], bytes: request.postDataBuffer() ?? Buffer.alloc(0) });
      return route.fulfill({ status: state.status, json: { code: state.status === 415 ? "document_media_type_unsupported" : "invalid_document", detail: "PRIVATE_VALIDATION_DETAIL" } });
    }
    if (path === "receipt-reading") return route.fulfill({ json: { scope_version: 1, enabled: false, available: true, can_change: true, disclosure: "Permiso explícito del negocio para correo, WhatsApp y archivos.", disclosure_token: "a".repeat(64), route: { gateway: "synthetic", interpretation: [{ model: "fixture-reader" }], reply: [] }, consented_at: null, revoked_at: null } });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Negocio de prueba" } });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "receipts" || path === "captures" || path === "updates") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none" } } });
    if (path === "spaces") return route.fulfill({ json: { spaces: [] } });
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
  await page.goto("/biz");
  await expect(page.getByTestId("workspace-panel-region")).toBeVisible();
  await page.getByTestId("workspace-panel-region").getByRole("button", { name: "Subir recibo", exact: true }).click();
  return { dialog: page.getByRole("dialog", { name: "Subir recibos", exact: true }), attempts, state };
}

for (const width of [1280, 390]) {
  test.describe(`Receipt upload recovery ${width}px`, () => {
    test.use({ viewport: { width, height: 844 } });
    test("failed upload stays inline, retries the same file and idempotency key, and offers replacement for an unsupported file", async ({ page }, testInfo) => {
      const { dialog, attempts, state } = await openIntake(page);
      const picker = dialog.locator('input[type="file"]').first();
      const content = Buffer.alloc(Math.round(4.1 * 1024 * 1024), 1);
      await picker.setInputFiles({ name: "synthetic.jpg", mimeType: "image/jpeg", buffer: content });
      await expect(dialog.getByTestId("receipt-ai-consent")).toHaveCount(0);
      const reading = dialog.getByTestId("receipt-reading-control");
      await reading.scrollIntoViewIfNeeded();
      const readingBounds = await reading.boundingBox();
      const footerBounds = await dialog.getByTestId("receipt-intake-footer").boundingBox();
      if (!readingBounds || !footerBounds) throw new Error("Reading setting and footer must render");
      expect(readingBounds.y).toBeGreaterThanOrEqual(0);
      expect(readingBounds.y + readingBounds.height).toBeLessThanOrEqual(footerBounds.y);
      expect(footerBounds.y + footerBounds.height).toBeLessThanOrEqual(844);
      await page.screenshot({ path: testInfo.outputPath(`receipt-upload-reading-${width}.png`) });
      await dialog.getByRole("button", { name: "Guardar los archivos pendientes", exact: true }).click();
      await expect(dialog.getByRole("alert")).toHaveText("No pudimos leer el recibo. Inténtalo de nuevo.");
      await expect(dialog).not.toContainText("PRIVATE_VALIDATION_DETAIL");
      await expect(dialog).not.toContainText("422");
      await expect(dialog).not.toContainText("XML, XML");
      expect(attempts[0].consent).toBeUndefined();
      state.status = 415;
      await dialog.getByRole("button", { name: "Reintentar", exact: true }).click();
      await expect(dialog.getByRole("alert")).toContainText("Este archivo no es compatible. Prueba con");
      expect(attempts).toHaveLength(2);
      expect(attempts[1]).toEqual(attempts[0]);
      await expect(dialog.getByRole("button", { name: "Reintentar", exact: true })).toHaveCount(0);
      await page.screenshot({ path: testInfo.outputPath(`receipt-upload-unsupported-${width}.png`) });
      await dialog.getByRole("button", { name: "Elegir otro archivo", exact: true }).click();
      await picker.setInputFiles({ name: "replacement.png", mimeType: "image/png", buffer: Buffer.from("synthetic fixture") });
      await expect(dialog.getByTestId("receipt-upload-queue")).toContainText("replacement.png");
      await expect(dialog.getByTestId("receipt-upload-queue")).not.toContainText("synthetic.jpg");
      expect(attempts).toHaveLength(2);
    });
  });
}
