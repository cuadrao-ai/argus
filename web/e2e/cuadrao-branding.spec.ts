import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

async function offline(page: Page, theme: "light" | "dark" = "light") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
}

async function capture(page: Page, name: string) {
  if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/${name}.png`, fullPage: true });
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`Cuadrao branding at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("Business sidebar mark preserves its existing controls and hydrated title", async ({ page }) => {
      await offline(page);
      await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.ready}`);
      await expect(page.getByTestId("business-record-review")).toBeVisible();
      await expect(page).toHaveTitle("Cuadrao");
      if (viewport.width === 390) {
        await page.getByTestId("chat-shell-menu-trigger").click();
        await expect(page.getByTestId("sidebar-drawer-logo")).toHaveAttribute("src", "/brand/cuadrao-mark-light.svg");
        await expect(page.getByText("cuadrao", { exact: true })).toBeVisible();
        await capture(page, `brand-sidebar-spanish-${viewport.width}`);
        await page.getByTestId("sidebar-drawer-close").click();
        await expect(page.getByTestId("sidebar-drawer-logo")).toBeHidden();
      } else {
        await expect(page.getByText("cuadrao", { exact: true })).toBeVisible();
        await page.getByRole("button", { name: "Collapse sidebar", exact: true }).click();
        const mark = page.locator('img[src="/brand/cuadrao-mark-light.svg"]');
        await expect(mark).toBeVisible();
        await expect.poll(() => mark.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
        await capture(page, `brand-sidebar-spanish-${viewport.width}`);
        await page.getByRole("button", { name: "Expand sidebar", exact: true }).click();
        await expect(page.getByText("cuadrao", { exact: true })).toBeVisible();
      }
      await expect(page).toHaveTitle("Cuadrao");
      const icon = await page.request.get("/favicon.ico");
      expect(icon.ok()).toBe(true);
      expect(await icon.body()).toEqual(readFileSync("app/favicon.ico"));
    });

    for (const theme of ["light", "dark"] as const) {
      test(`Spanish Business sign-in and signup retain artwork and ${theme} palette`, async ({ page }) => {
        await offline(page, theme);
        await page.goto("/?auth=login&preview=true&return_to=%2Fbiz%3Freceipt%3Drcpt-papeleria");
        await expect(page.getByRole("heading", { name: "Cuadrao", exact: true })).toBeVisible();
        const card = page.locator('[data-auth-brand="cuadrao"]');
        await expect(card).toContainText("¿Nuevo en Cuadrao?");
        const artwork = page.locator(`img[src="/brand/cuadrao-lockup-${theme}.svg"]`);
        await expect(artwork).toBeVisible();
        await expect.poll(() => artwork.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
        await card.locator('input[type="email"]').fill("ejemplo-local@example.com");
        await card.locator('input[type="password"]').fill("synthetic-local-password");
        const submit = card.locator('button[type="submit"]');
        await expect(submit).toHaveText("Iniciar sesión");
        await expect(submit).toHaveCSS("background-color", theme === "light" ? "rgb(41, 74, 64)" : "rgb(171, 212, 191)");
        await expect(card.locator('a[href^="/auth/forgot-password"]')).toHaveAttribute("href", "/auth/forgot-password");
        await capture(page, `brand-signin-${theme}-spanish-${viewport.width}`);
        await card.getByRole("button", { name: "Registrarse", exact: true }).click();
        await expect(card.locator('input[type="text"]')).toBeVisible();
        await expect(card).toContainText("Mínimo 8 caracteres.");
        await expect(card.locator('button[type="submit"]')).toHaveText("Registrarse");
        await expect(artwork).toBeVisible();
        await expect(page).toHaveTitle("Cuadrao");
        await capture(page, `brand-signup-${theme}-spanish-${viewport.width}`);
      });
    }
  });
}

test("Personal hydration keeps its original sidebar and tab brand", async ({ page }) => {
  await offline(page);
  await page.goto("/chat");
  await expect(page.getByTestId("chat-input")).toBeVisible();
  await expect(page).toHaveTitle("Argus");
  await expect(page.getByRole("complementary").getByText("argus", { exact: true })).toBeVisible();
  await expect(page.locator('img[src="/brand/cuadrao-mark-light.svg"]')).toHaveCount(0);
});
