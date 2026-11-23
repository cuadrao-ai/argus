import { expect, test, type Locator } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import type { ReceiptDetail } from "../lib/business-api";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

const file = "lectura-de-prueba.svg";
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="440"><rect width="320" height="440" fill="white"/><text x="32" y="64" font-size="20">Comprobante de prueba</text></svg>';

const activeLoops = (region: Locator) => region.evaluate((element) =>
  element.getAnimations({ subtree: true }).filter(animation => animation.effect?.getTiming().iterations === Infinity).length,
);

for (const state of ["reading", "held", "failed"] as const) {
  for (const motion of state === "reading" ? ["no-preference", "reduce"] as const : ["no-preference"] as const) {
    test(`dossier shows the server's ${state} receipt with ${motion} motion`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.emulateMedia({ reducedMotion: motion });
      const source = createFixtureBusinessDataSource();
      const base = await source.receipt("rcpt-blurry");
      const reading = state === "reading";
      const failed = state === "failed";
      const receipt: ReceiptDetail = {
        ...base, draft_id: null, merchant: null, filename: file, media_type: "image/svg+xml",
        status: reading ? "queued" : "needs_attention", attention: reading ? null : failed ? "not_a_receipt" : "read_budget_day",
        error_code: reading ? null : failed ? "not_a_receipt" : "business_read_budget_day",
        enterable: false, preparable: state === "held", read_pending: reading, delete_available: true, activity: null,
        bandeja: { por_revisar: false, con_problema: failed, leyendo: reading },
        bandeja_group: { group: failed ? "attention" : "reading", reason: failed ? "not_a_receipt" : "reading", label: failed ? "cant_read" : "reading", draft_id: null, version: null },
      };
      await installReceiptBusiness(page, (parts, route) => {
        if (parts[0] !== "receipts" || parts[1] !== receipt.id) return undefined;
        if (parts.length === 2) return Promise.resolve(receipt);
        if (parts[2] === "source") return route.fulfill({ contentType: "image/svg+xml", body: svg }).then(() => null);
        return undefined;
      }, state === "held" ? "dark" : "light");
      await page.goto(`/biz?receipt=${receipt.id}`);
      const drawer = page.getByTestId("side-drawer");
      const fields = drawer.getByRole("tabpanel", { name: "General", exact: true });
      await expect(drawer.getByRole("heading", { name: file })).toBeVisible();
      await expect(drawer.getByText(failed ? "No se pudo leer" : "Leyendo…", { exact: true }).first()).toBeVisible();
      await expect(drawer.getByRole("tab", { name: "Datos fiscales" })).toHaveCount(0);
      if (failed) {
        await expect(fields.getByText("Esto no parece un recibo", { exact: true })).toBeVisible();
        await expect(drawer.getByRole("button", { name: "Subir otro documento", exact: true })).toBeVisible();
        await expect(drawer.getByRole("button", { name: "Leer de nuevo" })).toHaveCount(0);
      } else {
        if (state === "held") await expect(fields).toContainText("Hoy se alcanzó el límite de lecturas.");
        await expect(fields).not.toContainText("%");
        await expect(fields.locator("input,select")).toHaveCount(0);
        const original = drawer.getByTestId("receipt-review-source");
        await expect(original.getByTestId("receipt-viewer")).toBeVisible();
        if (reading && motion === "no-preference") {
          await expect.poll(() => activeLoops(original)).toBeGreaterThanOrEqual(2);
        } else {
          await expect.poll(() => activeLoops(original)).toBe(0);
          await expect.poll(() => activeLoops(fields)).toBe(0);
        }
        const remove = drawer.getByRole("button", { name: "Eliminar documento", exact: true });
        await expect(remove).toBeVisible();
        await expect(drawer.getByTestId("dossier-size")).toBeEnabled();
      }
      await page.screenshot({ path: testInfo.outputPath(`dossier-${state}-${motion}.png`) });
      if (reading && motion === "no-preference") {
        const remove = drawer.getByRole("button", { name: "Eliminar documento", exact: true });
        await expect(remove).toHaveText("Eliminar documento", { useInnerText: true });
        await drawer.getByTestId("dossier-size").click();
        await expect(drawer.getByRole("tab", { name: "Documento", exact: true })).toBeVisible();
        await expect(remove).toBeVisible();
        await expect(remove).toHaveText("", { useInnerText: true });
        await page.screenshot({ path: testInfo.outputPath("dossier-reading-narrow.png") });
      }
    });
  }
}

test("an owner can recover an interrupted read with an expired preparation grant", async ({ page }, testInfo) => {
  const base = await createFixtureBusinessDataSource().receipt("rcpt-blurry");
  const receipt: ReceiptDetail = {
    ...base, draft_id: null, preparable: true, read_pending: false,
    attention: "interrupted", error_code: "business_record_not_found",
    bandeja_group: { group: "attention", reason: "interrupted", label: "cant_read", draft_id: null, version: null },
  };
  const writes: string[] = [];
  await installReceiptBusiness(page, ([resource, id, action], route) => {
    if (resource !== "receipts" || id !== receipt.id) return;
    if (!action) return Promise.resolve(receipt);
    if (route.request().method() === "POST" && (action === "rebind" || action === "prepare")) {
      writes.push(action);
      return Promise.resolve(receipt);
    }
  });
  await page.goto(`/biz?receipt=${receipt.id}`);
  const rebind = page.getByRole("button", { name: "Vincular a mi acceso actual", exact: true });
  await expect(rebind).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("dossier-interrupted-grant.png"), animations: "disabled" });
  await rebind.click();
  await expect.poll(() => writes).toEqual(["rebind", "prepare"]);
});
