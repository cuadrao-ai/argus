import { expect, test } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { SHOT_DIR, bandejaRows, expectTargets, installReceiptBusiness, noHorizontalScroll, openReceipt, reviewAction, type BusinessOverride } from "./support/business-receipt-fixture";

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/biz needs the Business pilot server");

const prepared: BusinessOverride = (parts, _route, source) => {
  if (parts[0] === "receipts" && parts[1] === "rcpt-ferreteria" && parts.length === 2) return source.receipt("rcpt-ferreteria").then((receipt) => ({ ...receipt, draft_id: dossierFixtureIds.fiscal }));
  return undefined;
};

const reading: BusinessOverride = (parts, _route, source) => {
  if (parts[0] === "receipts" && parts[1] === "rcpt-ferreteria" && parts.length === 2) {
    return source.receipt("rcpt-ferreteria").then((receipt) => ({ ...receipt, draft_id: null, activity: { state: "reading", unread: false, completion_cursor: null }, bandeja: { por_revisar: false, con_problema: false, leyendo: true } }));
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

    test("Historial sits below the fields and expands from its collapsed state", async ({ page }) => {
      await installReceiptBusiness(page, prepared);
      await openReceipt(page, /Ferretería La Esquina/);
      const history = page.getByTestId("receipt-history");
      await expect(history.getByRole("heading", { name: "Historial" })).toBeVisible();
      const toggle = history.getByRole("button", { name: /^Historial/ });
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(history.locator("ol")).toBeHidden();
      const fields = (await page.getByTestId("receipt-review-fields").boundingBox())!;
      const rail = (await history.boundingBox())!;
      if (width >= 1024) {
        expect(rail.y).toBeGreaterThanOrEqual(fields.y + fields.height);
        expect(Math.round(rail.x)).toBe(Math.round(fields.x));
      } else {
        expect(rail.y).toBeGreaterThanOrEqual(fields.y + fields.height);
        const tabs = page.getByTestId("receipt-review-tabs");
        await expect(page.getByTestId("receipt-review-source")).toBeHidden();
        await tabs.getByRole("radio", { name: "Original", exact: true }).click();
        await expect(page.getByTestId("receipt-review-source")).toBeVisible();
        await expect(history).toBeHidden();
        await tabs.getByRole("radio", { name: "Formulario", exact: true }).click();
      }
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await expect(history.locator("ol")).toBeVisible();
      const lines = await history.locator("li > p").allTextContents();
      expect(lines.length).toBeGreaterThan(0);
      expect(lines.filter((line) => /revisi[oó]n|tras aprobar|primer flujo|registrado/i.test(line)), "no dev wording in the rail").toEqual([]);
      await history.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page);
      await page.screenshot({ path: `${SHOT_DIR}/historial-${width}.png` });
      test.info().annotations.push({ type: "issue", description: "ReceiptHistory.tsx:153 renders the Historial toggle at 40px; the required target is 44px." });
      await expectTargets(page, '[data-testid="receipt-history"] button');
    });

    test("the AI reading state sweeps the source, holds four empty fields and hides the total", async ({ page }) => {
      await installReceiptBusiness(page, reading);
      await openReceipt(page, /Ferretería La Esquina/);
      const state = page.getByTestId("receipt-reading-state");
      await expect(state.getByRole("status")).toHaveText("Leyendo tu recibo…");
      await expect(state.locator("dt")).toHaveText(["Proveedor", "NCF", "ITBIS", "Total"]);
      await expect(page.getByTestId("receipt-total")).toHaveCount(0);
      if (width < 1024) await page.getByTestId("receipt-review-tabs").getByRole("radio", { name: "Original", exact: true }).click();
      const band = page.getByTestId("receipt-reading-band");
      await expect(band).toBeVisible();
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
      await expect(bandejaRows(page)).toBeVisible();
      await reviewAction(page, /Ferretería La Esquina/).click();
      const skeleton = page.locator('[data-testid="business-loading"][data-layout="detail"]');
      await page.waitForTimeout(200);
      expect(await skeleton.count(), "200ms in, the page is still blank").toBe(0);
      await expect(skeleton).toBeVisible();
      await page.screenshot({ path: `${SHOT_DIR}/loading-${width}.png` });
      await expect(skeleton.getByTestId("business-skeleton-top")).toBeVisible();
      await expect(skeleton.getByTestId("business-skeleton-fields")).toBeVisible();
      const shownWords = await page.getByTestId(width >= 1024 ? "side-drawer" : "workspace-panel-region").evaluate((region) => [...region.querySelectorAll("*")].filter((element) => !element.closest(".sr-only") && [...element.childNodes].some((node) => node.nodeType === 3 && /Cargando/i.test(node.textContent ?? ""))).length);
      expect(shownWords, "no visible Cargando line while the skeleton shows").toBe(0);
      await noHorizontalScroll(page);
      await expect(page.getByTestId("receipt-top-block")).toBeVisible({ timeout: 8000 });
    });
  });
}
