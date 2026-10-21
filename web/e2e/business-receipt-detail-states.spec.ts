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
    return source.receipt("rcpt-ferreteria").then((receipt) => ({ ...receipt, activity: { state: "reading", unread: false, completion_cursor: null }, bandeja: { por_revisar: false, con_problema: false, leyendo: true } }));
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
      const lines = await history.locator("li > p").allTextContents();
      expect(lines.length).toBeGreaterThan(0);
      expect(lines.filter((line) => /revisi[oó]n|tras aprobar|primer flujo|registrado/i.test(line)), "no dev wording in the rail").toEqual([]);
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
      await page.waitForTimeout(200);
      expect(await skeleton.count(), "200ms in, the page is still blank").toBe(0);
      await expect(skeleton).toBeVisible();
      await page.screenshot({ path: `${SHOT_DIR}/loading-${width}.png` });
      await expect(skeleton.getByTestId("business-skeleton-top")).toBeVisible();
      await expect(skeleton.getByTestId("business-skeleton-fields")).toBeVisible();
      const shownWords = await page.getByTestId("workspace-panel-region").evaluate((region) => [...region.querySelectorAll("*")].filter((element) => !element.closest(".sr-only") && [...element.childNodes].some((node) => node.nodeType === 3 && /Cargando/i.test(node.textContent ?? ""))).length);
      expect(shownWords, "no visible Cargando line while the skeleton shows").toBe(0);
      await noHorizontalScroll(page);
      await expect(page.getByTestId("receipt-top-block")).toBeVisible({ timeout: 8000 });
    });
  });
}
