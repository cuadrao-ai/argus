import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { createBusinessReportHttpFixture } from "../__tests__/fixtures/business-report-http-fixture";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture, type Theme } from "./support/breakpoint-fixture";
import { fulfillSyntheticBusinessFallback } from "./support/synthetic-business-fallback";

/** Registros on the report fixture. Each export request waits until the test lets the server answer. */
async function openRegistros(page: Page, theme: Theme) {
  const fixture = createBusinessReportHttpFixture();
  const held: (() => void)[] = [];
  await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
  await page.route("**/api/v1/business/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (/\/(reports\/|report-views(?:\/|$))/.test(path)) {
      if (path.endsWith("/reports/export")) await new Promise<void>((resolve) => { held.push(resolve); });
      const response = await fixture.request(request.url(), { method: request.method(), headers: request.headers(), body: request.postData() ?? undefined });
      return route.fulfill({ status: response.status, headers: { ...Object.fromEntries(response.headers), "access-control-expose-headers": "Content-Disposition" }, body: Buffer.from(await response.arrayBuffer()) });
    }
    return fulfillSyntheticBusinessFallback(route, { fulfillConsent: () => fulfillAcceptedBusinessConsent(route) });
  });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.fallback() : route.abort("blockedbyclient"));
  // A headless browser cannot answer the system Save As window, so the file downloads.
  await page.addInitScript(() => { delete (window as { showSaveFilePicker?: unknown }).showSaveFilePicker; });
  await page.goto("/biz?view=transactions");
  const answer = async () => {
    await expect.poll(() => held.length).toBeGreaterThan(0);
    held.shift()!();
  };
  return { fixture, answer };
}

async function exportNow(page: Page) {
  await page.getByTestId("records-export").click();
  const download = page.getByTestId("records-export-download");
  await expect(download).toBeEnabled();
  await download.click();
}

async function evidence(page: Page, name: string) {
  if (!process.env.EVIDENCE_DIR) return;
  await mkdir(process.env.EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: join(process.env.EVIDENCE_DIR, `${name}.png`) });
}

for (const theme of ["light", "dark"] as const) {
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    const phone = viewport.width < 768;
    const tag = `${viewport.width}-${theme}`;

    test(`the export runs in the island and ends in the toast at ${viewport.width}px, ${theme}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const { answer } = await openRegistros(page, theme);
      await exportNow(page);
      const island = page.getByTestId("receipt-upload-island");
      await expect(page.getByTestId("records-export-panel")).toHaveCount(0);
      await expect(island).toHaveAttribute("data-state", "preparing");
      await expect(island).toHaveAttribute("aria-label", "Preparando…");
      await expect(island).toHaveText(phone ? "" : "Preparando…");
      await expect(island.locator('[data-arrow="down"]')).toBeVisible();
      // The entrance takes 600ms.
      await page.waitForTimeout(700);
      await evidence(page, `1-preparando-${tag}`);

      await answer();
      await expect(island).toHaveAttribute("data-state", "done");
      await expect(island).toHaveText("");
      await expect(page.getByText("Listo. Revisa tus descargas")).toBeVisible();
      await expect(page.getByRole("button", { name: "Descargar de nuevo" })).toBeVisible();
      await page.waitForTimeout(450);
      await evidence(page, `2-listo-${tag}`);
      await expect(island).toHaveCount(0);
    });

    test(`a failed export turns the island red and a click from another screen reopens Exportar at the error at ${viewport.width}px, ${theme}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const { fixture, answer } = await openRegistros(page, theme);
      fixture.controls.exportFails = true;
      await exportNow(page);
      await answer();
      const island = page.getByTestId("receipt-upload-island");
      await expect(island).toHaveAttribute("data-state", "failed");
      await expect(island).toHaveAttribute("aria-label", "No pudimos preparar el archivo. Inténtalo de nuevo.");
      await expect(island).toHaveText("");
      await expect(page.getByTestId("records-export-panel")).toHaveCount(0);
      await page.waitForTimeout(700);
      await evidence(page, `3-fallo-${tag}`);
      expect((await island.boundingBox())!.width).toBe(40);

      await page.getByTestId(phone ? "business-bottom-tabs" : "business-sidebar-nav").getByText("Inicio", { exact: true }).click();
      await expect(page.getByTestId("records-export")).toHaveCount(0);
      await expect(island).toHaveAttribute("data-state", "failed");
      await island.click();
      const alert = page.getByTestId("records-export-panel").locator("xpath=ancestor::*[@role='dialog']").getByRole("alert");
      await expect(alert).toContainText("No pudimos preparar el archivo. Inténtalo de nuevo.");
      await expect(island).toHaveCount(0);
      await page.waitForTimeout(400);
      await evidence(page, `4-panel-en-el-error-${tag}`);

      fixture.controls.exportFails = false;
      await alert.getByRole("button", { name: "Reintentar" }).click();
      await expect(page.getByTestId("records-export-panel")).toHaveCount(0);
      await expect(island).toHaveAttribute("data-state", "preparing");
      await answer();
      await expect(page.getByText("Listo. Revisa tus descargas")).toBeVisible();
    });
  }
}
