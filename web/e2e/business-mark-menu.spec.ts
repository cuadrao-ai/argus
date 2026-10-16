import { expect, test } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`Business menu and sticky review at ${viewport.width}px`, () => {
    test.use({ viewport });
    test.beforeEach(async ({ page }) => {
      await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
      await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    });
    test("mark opens access and the saved business switcher", async ({ page }) => {
      await page.goto("/dev/business-preview");
      if (viewport.width < 768) await page.getByTestId("chat-shell-menu-trigger").click();
      const trigger = page.getByRole("button", { name: "Mi negocio", exact: true });
      await trigger.click();
      const menu = page.getByRole("menu", { name: "Mi negocio", exact: true });
      await expect(menu).toContainText("MN");
      await expect(menu.getByRole("menuitem", { name: "Equipo y accesos" })).toBeVisible();
      if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/menu-${viewport.width}.png` });
      await page.keyboard.press("Escape");
      await expect(menu).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await trigger.click();
      await menu.getByRole("menuitem", { name: "Equipo y accesos" }).click();
      await expect(page).toHaveURL(/view=access/);
      await trigger.click();
      await page.getByRole("menuitem", { name: "Cambiar de negocio" }).click();
      await page.getByRole("option", { name: /Colmado Peña/ }).click();
      await expect(page.getByTestId("business-current-name").first()).toHaveText("Colmado Peña");
    });
    test("one-pass approval stays visible while the review scrolls", async ({ page }) => {
      await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.ready}`);
      const footer = page.getByTestId("receipt-review-footer");
      await expect(footer).toBeVisible();
      const approve = footer.getByRole("button", { name: "Aprobar", exact: true });
      await expect(approve).toBeEnabled();
      await expect(approve).toBeInViewport();
      if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/review-before-${viewport.width}.png` });
      await page.getByRole("button", { name: "Consultar registro actual", exact: true }).scrollIntoViewIfNeeded();
      await expect(approve).toBeInViewport();
      await approve.click();
      await expect(footer).toHaveCount(0);
      await expect(page.getByText(/Se registró un gasto/)).toBeVisible();
      if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/review-after-${viewport.width}.png` });
    });
  });
}
