import { expect, test, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { SHOT_DIR, expectTargets, installReceiptBusiness, noHorizontalScroll, openReceipt, type BusinessOverride } from "./support/business-receipt-fixture";

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/biz needs the Business pilot server");

/** Ferretería La Esquina opens the fiscal record, so the page shows every card the brief names. */
function prepared(change?: (dossier: Record<string, unknown>) => void): BusinessOverride {
  return (parts, _route, source) => {
    if (parts[0] === "receipts" && parts[1] === "rcpt-ferreteria" && parts.length === 2) {
      return source.receipt("rcpt-ferreteria").then((receipt) => ({ ...receipt, draft_id: dossierFixtureIds.fiscal }));
    }
    if (parts[0] === "drafts" && parts[1] === dossierFixtureIds.fiscal && parts[2] === "dossier") {
      return source.dossier(dossierFixtureIds.fiscal).then((dossier) => {
        const next = structuredClone(dossier) as unknown as Record<string, unknown>;
        change?.(next);
        return next;
      });
    }
    return undefined;
  };
}

const withoutDate = (dossier: Record<string, unknown>) => {
  const facts = dossier.facts as Record<string, unknown>;
  facts.occurred_on = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
  dossier.blockers = [{ code: "fact_required", field: "occurred_on" }];
  dossier.approval_available = false;
};

async function box(page: Page, selector: string) {
  const found = await page.locator(selector).first().boundingBox();
  expect(found, selector).not.toBeNull();
  return found!;
}

for (const width of [1440, 390] as const) {
  test.describe(`receipt detail layout at ${width}`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("supplier, total and status come first; labelled cards; a full-width footer that never covers a card", async ({ page }) => {
      await installReceiptBusiness(page, prepared());
      await openReceipt(page, /Ferretería La Esquina/);
      const review = page.getByTestId("business-record-review");
      const top = page.getByTestId("receipt-top-block");
      await expect(top.getByRole("heading", { level: 2 })).toHaveText(/\S/);
      await expect(top.getByTestId("receipt-total")).toHaveText(/^RD\$ \d{1,3}(,\d{3})*\.\d{2}$/);
      await expect(top.getByTestId("status-pill")).toBeVisible();
      const topBox = await box(page, '[data-testid="receipt-top-block"]');
      const fieldsBox = await box(page, '[data-testid="receipt-review-fields"]');
      const sourceBox = await box(page, '[data-testid="receipt-review-source"]');
      expect(topBox.y + topBox.height).toBeLessThanOrEqual(fieldsBox.y);
      if (width >= 1024) {
        // A desktop opens the record in a tray beside the Bandeja: one column, the source on top.
        await expect(page.getByTestId("business-inbox-receipts")).toBeVisible();
        expect(sourceBox.y + sourceBox.height).toBeLessThanOrEqual(fieldsBox.y + 0.5);
        const trayBox = await box(page, '[data-testid="side-drawer"]');
        expect(Math.round(trayBox.width), "the tray prefers 640px").toBe(640);
        expect(Math.round(trayBox.x + trayBox.width)).toBe(width);
      } else {
        expect(fieldsBox.y + fieldsBox.height).toBeLessThanOrEqual(sourceBox.y);
      }

      const facts = page.getByTestId("receipt-current-facts");
      for (const label of ["Fecha de actividad", "Monto", "Moneda", "Datos fiscales", "RNC", "NCF", "ITBIS", "e-CF", "Categoría"]) {
        await expect(facts.getByText(label, { exact: true }).first()).toBeVisible();
      }
      const labelsAbove = await facts.locator("[data-fact]").evaluateAll((rows) => rows.every((row) => {
        const label = row.querySelector("dt")!.getBoundingClientRect();
        const value = row.querySelector("dd")!.getBoundingClientRect();
        return label.bottom <= value.top + 0.5;
      }));
      expect(labelsAbove, "every label sits above its field").toBe(true);
      for (const shown of [facts, top]) {
        await expect(shown).not.toContainText("Desconocido");
        await expect(shown).not.toContainText("Sin dato");
      }
      for (const card of await facts.locator("section").all()) {
        expect(await card.getByText("Leído del recibo", { exact: true }).count()).toBeLessThanOrEqual(1);
      }
      await expect(facts.locator(".lucide-circle-dashed")).toHaveCount(0);

      const footer = page.getByTestId("receipt-review-footer");
      await expect(footer.getByRole("button", { name: "Aprobar", exact: true })).toBeVisible();
      await expect(footer.getByRole("button", { name: "Aprobar y siguiente" })).toBeVisible();
      await expectTargets(page, '[data-testid="receipt-review-footer"] button');
      await expectTargets(page, '[data-testid="receipt-current-facts"] button');
      await noHorizontalScroll(page);
      if (width >= 1024) {
        // The tray pins its footer under its own scroll area, across the tray.
        const tray = page.getByTestId("side-drawer");
        await expect(tray.locator('[data-footer-slot] [data-testid="receipt-review-footer"]')).toBeVisible();
        const trayBox = await box(page, '[data-testid="side-drawer"]');
        const slot = await box(page, "[data-footer-slot]");
        expect(Math.round(slot.y + slot.height + 12), "the footer meets the tray's bottom edge").toBe(Math.round(trayBox.y + trayBox.height));
        await page.screenshot({ path: `${SHOT_DIR}/full-receipt-${width}.png` });
        const scroller = tray.locator(".argus-thin-scrollbar");
        await scroller.evaluate((element) => element.scrollTo(0, element.scrollHeight));
        const footerTop = (await box(page, "[data-footer-slot]")).y;
        const cardBottoms = await review.locator("section, [data-testid='receipt-marks-card'], [data-testid='fiscal-declaration']").evaluateAll((cards) => cards.map((card) => card.getBoundingClientRect()).filter((rect) => rect.height > 0).map((rect) => rect.bottom));
        for (const bottom of cardBottoms) expect(bottom, "no card hides under the footer").toBeLessThanOrEqual(footerTop + 0.5);
        await page.screenshot({ path: `${SHOT_DIR}/full-receipt-bottom-${width}.png` });
        return;
      }
      const region = await page.getByTestId("workspace-panel-region").evaluate((element) => ({ left: element.getBoundingClientRect().left, width: element.clientWidth }));
      const footerBox = await box(page, '[data-testid="receipt-review-footer"]');
      expect(Math.round(footerBox.width), "the footer spans the pane").toBe(Math.round(region.width));
      expect(Math.round(footerBox.x)).toBe(Math.round(region.left));
      await noHorizontalScroll(page);
      const pane = (await page.getByTestId("workspace-panel-region").boundingBox())!;
      expect(Math.round(footerBox.y + footerBox.height), "before scrolling, the footer sticks to the pane's bottom edge").toBe(Math.round(pane.y + pane.height));
      await page.screenshot({ path: `${SHOT_DIR}/full-receipt-${width}.png` });

      await page.getByTestId("workspace-panel-region").evaluate((element) => element.scrollTo(0, element.scrollHeight));
      const footerTop = (await box(page, '[data-testid="receipt-review-footer"]')).y;
      const atEnd = await box(page, '[data-testid="receipt-review-footer"]');
      expect(Math.round(atEnd.y + atEnd.height), "at the end the footer still meets the pane's bottom edge").toBe(Math.round(pane.y + pane.height));
      const cardBottoms = await review.locator("section, [data-testid='receipt-marks-card'], [data-testid='fiscal-declaration']").evaluateAll((cards) => cards.map((card) => card.getBoundingClientRect()).filter((rect) => rect.height > 0).map((rect) => rect.bottom));
      for (const bottom of cardBottoms) expect(bottom, "no card hides under the footer").toBeLessThanOrEqual(footerTop + 0.5);
      if (width < 720) {
        const tabs = await box(page, '[data-testid="business-bottom-tabs"]');
        expect(footerTop + (await box(page, '[data-testid="receipt-review-footer"]')).height).toBeLessThanOrEqual(tabs.y + 1);
      }
      await page.screenshot({ path: `${SHOT_DIR}/full-receipt-bottom-${width}.png` });
    });

    test(width >= 1024 ? "the tray reads source, then fields" : "the fields come before the source in reading order", async ({ page }) => {
      await installReceiptBusiness(page, prepared());
      await openReceipt(page, /Ferretería La Esquina/);
      const order = await page.getByTestId("business-record-review").evaluate((review) => {
        const fields = review.querySelector('[data-testid="receipt-review-fields"]')!;
        const source = review.querySelector('[data-testid="receipt-review-source"]')!;
        return Boolean(fields.compareDocumentPosition(source) & Node.DOCUMENT_POSITION_FOLLOWING);
      });
      expect(order).toBe(width < 1024);
    });

    test("a disabled Aprobar always says why", async ({ page }) => {
      await installReceiptBusiness(page, prepared(withoutDate));
      await openReceipt(page, /Ferretería La Esquina/);
      const footer = page.getByTestId("receipt-review-footer");
      await expect(footer.getByRole("button", { name: "Aprobar", exact: true })).toBeDisabled();
      await expect(footer.getByTestId("approve-reason")).toHaveText("Agrega la fecha para aprobar");
      await expect(footer.getByTestId("approve-reason")).toHaveCSS("color", "rgb(86, 99, 94)");
      await noHorizontalScroll(page);
      await page.screenshot({ path: `${SHOT_DIR}/disabled-aprobar-${width}.png` });
    });

    test("a receipt that will not load says so in red with Reintentar, and Reintentar loads it", async ({ page }) => {
      let failures = 1;
      await installReceiptBusiness(page, (parts, route) => {
        if (parts[0] === "receipts" && parts[1] === "rcpt-ferreteria" && parts.length === 2 && failures > 0) {
          failures -= 1;
          return route.fulfill({ status: 404, json: { code: "not_found" } }).then(() => null);
        }
        return undefined;
      });
      await openReceipt(page, /Ferretería La Esquina/).catch(() => undefined);
      const error = page.getByTestId("receipt-load-error");
      await expect(error.getByRole("alert")).toBeVisible();
      await expect(error.getByRole("alert")).toHaveCSS("color", "rgb(158, 47, 57)");
      await expect(error.locator(".lucide-circle-alert")).toBeVisible();
      await expectTargets(page, '[data-testid="receipt-load-error"] button');
      await page.screenshot({ path: `${SHOT_DIR}/error-${width}.png` });
      await error.getByRole("button", { name: "Reintentar" }).click();
      await expect(page.getByTestId("receipt-top-block")).toBeVisible();
    });
  });
}

test.describe("receipt detail at a narrow desktop", () => {
  test.use({ viewport: { width: 1100, height: 900 } });
  test("the tray takes at most half the screen and the Bandeja stays beside it", async ({ page }) => {
    await installReceiptBusiness(page, prepared());
    await openReceipt(page, /Ferretería La Esquina/);
    const tray = (await page.getByTestId("side-drawer").boundingBox())!;
    expect(Math.round(tray.width)).toBe(550);
    const list = (await page.getByTestId("business-inbox-receipts").boundingBox())!;
    expect(list.x + list.width).toBeLessThanOrEqual(tray.x + 0.5);
    await noHorizontalScroll(page);
  });
});
