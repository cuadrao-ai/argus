import { expect, test } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { SHOT_DIR, expectTargets, installReceiptBusiness, noHorizontalScroll, openReceipt, type BusinessOverride } from "./support/business-receipt-fixture";

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/biz needs the Business pilot server");

const prepared: BusinessOverride = (parts, _route, source) => {
  if (parts[0] === "receipts" && parts[1] === "rcpt-ferreteria" && parts.length === 2) return source.receipt("rcpt-ferreteria").then((receipt) => ({ ...receipt, draft_id: dossierFixtureIds.fiscal }));
  return undefined;
};

const reading: BusinessOverride = (parts, _route, source) => {
  if (parts[0] === "receipts" && parts[1] === "rcpt-ferreteria" && parts.length === 2) {
    return source.receipt("rcpt-ferreteria").then((receipt) => ({ ...receipt, read_pending: true, activity: { state: "reading", unread: false, completion_cursor: null } }));
  }
  return undefined;
};

const slow: BusinessOverride = (parts, _route, source) => {
  if (parts[0] === "receipts" && parts[1] === "rcpt-ferreteria" && parts.length === 2) return new Promise((resolve) => setTimeout(resolve, 4000)).then(() => source.receipt("rcpt-ferreteria"));
  return undefined;
};

for (const width of [1440, 390] as const) {
  test.describe(`receipt detail states at ${width}`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("Historial sits under the fields on a desktop and last on a phone, collapsed to three", async ({ page }) => {
      await installReceiptBusiness(page, prepared);
      await openReceipt(page, /Ferretería La Esquina/);
      const history = page.getByTestId("receipt-history");
      await expect(history.getByRole("heading", { name: "Historial" })).toBeVisible();
      expect(await history.locator("li").count()).toBeLessThanOrEqual(3);
      const fields = (await page.getByTestId("receipt-review-fields").boundingBox())!;
      const source = (await page.getByTestId("receipt-review-source").boundingBox())!;
      const rail = (await history.boundingBox())!;
      if (width >= 1024) {
        expect(rail.y).toBeGreaterThanOrEqual(fields.y + fields.height);
        expect(Math.round(rail.x)).toBe(Math.round(fields.x));
      } else {
        expect(rail.y).toBeGreaterThanOrEqual(source.y + source.height);
      }
      const seeAll = history.getByRole("button", { name: "Ver todo" });
      if (await seeAll.count()) {
        await expectTargets(page, '[data-testid="receipt-history"] button');
        await seeAll.click();
        await expect(seeAll).toHaveCount(0);
      }
      await expect(history).not.toContainText(/Revisión|tras aprobar|primer flujo/);
      await history.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page);
      await page.screenshot({ path: `${SHOT_DIR}/historial-${width}.png` });
    });

    test("the AI reading state sweeps the source, holds four empty fields and hides the total", async ({ page }) => {
      await installReceiptBusiness(page, reading);
      await openReceipt(page, /Ferretería La Esquina/);
      const state = page.getByTestId("receipt-reading-state");
      await expect(state.getByRole("status")).toHaveText("Leyendo tu recibo…");
      await expect(state.locator("dt")).toHaveText(["Proveedor", "NCF", "ITBIS", "Total"]);
      await expect(page.getByTestId("receipt-total")).toHaveCount(0);
      const band = page.getByTestId("receipt-reading-band");
      expect(await band.evaluate((element) => getComputedStyle(element).animationDuration)).toBe("1.6s");
      expect(await band.evaluate((element) => getComputedStyle(element).backgroundImage)).toContain("rgba(47, 90, 73, 0.2)");
      await noHorizontalScroll(page);
      await page.screenshot({ path: `${SHOT_DIR}/ai-reading-${width}.png` });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await expect(band).toBeHidden();
    });

    test("loading paints nothing for 300ms, then a skeleton of the top block and fields, never a Cargando line", async ({ page }) => {
      await installReceiptBusiness(page, slow);
      await page.goto("/biz?view=inbox");
      await expect(page.getByTestId("business-inbox-receipts")).toBeVisible();
      await page.getByTestId("business-inbox-receipts").getByRole("button", { name: /Ferretería La Esquina/ }).click();
      const skeleton = page.locator('[data-testid="business-loading"][data-layout="detail"]');
      await expect(skeleton).toHaveCount(0, { timeout: 200 });
      await expect(skeleton).toBeVisible();
      await page.screenshot({ path: `${SHOT_DIR}/loading-${width}.png` });
      await expect(skeleton.getByTestId("business-skeleton-top")).toBeVisible();
      await expect(skeleton.getByTestId("business-skeleton-fields")).toBeVisible();
      await expect(page.getByText("Cargando", { exact: false })).toBeHidden();
      await noHorizontalScroll(page);
      await expect(page.getByTestId("receipt-top-block")).toBeVisible({ timeout: 8000 });
    });
  });
}
