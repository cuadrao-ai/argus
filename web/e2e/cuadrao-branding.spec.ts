import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture, type Language, type Theme } from "./support/breakpoint-fixture";

async function offline(page: Page, theme: Theme = "light", language: Language = "es-419") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language, theme, emptyChat: true });
}

async function capture(page: Page, name: string) {
  if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/${name}.png`, fullPage: true });
}

const COPY = {
  "es-419": { requestAccess: "Solicitar acceso", signIn: "Iniciar sesión", newTo: "¿Nuevo en Cuadrao?", signUp: "Registrarse", inbox: "Bandeja", collapse: "Contraer", expand: "Expandir" },
  en: { requestAccess: "Request access", signIn: "Sign in", newTo: "New to Cuadrao?", signUp: "Sign up", inbox: "Inbox", collapse: "Collapse", expand: "Expand" },
} as const;

const LANGUAGES: Language[] = ["es-419", "en"];
const THEMES: Theme[] = ["light", "dark"];
const short = (language: Language) => (language === "es-419" ? "spanish" : "english");

async function expectLockup(page: Page, theme: Theme) {
  await expect(page.getByRole("heading", { name: "Cuadrao", exact: true })).toBeVisible();
  const artwork = page.locator(`img[src="/brand/cuadrao-lockup-${theme}.svg"]`);
  await expect(artwork).toBeVisible();
  await expect.poll(() => artwork.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await expect(page.locator("main")).toHaveCSS("background-color", theme === "light" ? "rgb(250, 251, 248)" : "rgb(23, 43, 38)");
  await expect(page.getByText("argus", { exact: true })).toHaveCount(0);
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`Cuadrao branding at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("Business sidebar mark preserves its existing controls and hydrated title", async ({ page }) => {
      await offline(page);
      await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.ready}`);
      await expect(page.getByTestId("business-record-review")).toBeVisible();
      // The dev preview page names itself before the brand; the brand is what matters here.
      await expect(page).toHaveTitle(/Cuadrao$/);
      if (viewport.width === 390) {
        await page.getByTestId("chat-shell-menu-trigger").click();
        await expect(page.getByTestId("sidebar-drawer-logo")).toHaveAttribute("src", "/brand/cuadrao-mark-light.svg");
        await expect(page.getByText("cuadrao", { exact: true })).toBeVisible();
        await capture(page, `brand-sidebar-spanish-${viewport.width}`);
        await page.getByTestId("sidebar-drawer-close").click();
        await expect(page.getByTestId("sidebar-drawer-logo")).toBeHidden();
      } else {
        await expect(page.getByText("cuadrao", { exact: true })).toBeVisible();
        await page.getByRole("button", { name: COPY["es-419"].collapse, exact: true }).click();
        const mark = page.locator('img[src="/brand/cuadrao-mark-light.svg"]');
        await expect(mark).toBeVisible();
        await expect.poll(() => mark.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
        await capture(page, `brand-sidebar-spanish-${viewport.width}`);
        await page.getByRole("button", { name: COPY["es-419"].expand, exact: true }).click();
        await expect(page.getByText("cuadrao", { exact: true })).toBeVisible();
      }
      await expect(page).toHaveTitle(/Cuadrao$/);
      const icon = await page.request.get("/favicon.ico");
      expect(icon.ok()).toBe(true);
      expect(await icon.body()).toEqual(readFileSync("app/favicon.ico"));
      expect(await icon.body()).toEqual(readFileSync("../marketing/app/favicon.ico"));
      for (const path of ["/icons/cuadrao-192.png", "/icons/cuadrao-512.png", "/icons/apple-touch-icon-180.png", "/brand/cuadrao-mark-dark.svg"]) {
        expect((await page.request.get(path)).ok(), path).toBe(true);
      }
    });

    for (const theme of THEMES) {
      for (const language of LANGUAGES) {
        const copy = COPY[language];

        test(`${short(language)} ${theme} landing shows the Cuadrao lockup on the plain root`, async ({ page }) => {
          await offline(page, theme, language);
          await page.goto("/?preview=true");
          await expectLockup(page, theme);
          await expect(page).toHaveTitle("Cuadrao");
          const request = page.getByTestId("landing-request-access");
          await expect(request).toHaveText(copy.requestAccess);
          await expect(request).toHaveCSS("background-color", theme === "light" ? "rgb(47, 90, 73)" : "rgb(171, 212, 191)");
          await expect(page.getByRole("button", { name: copy.signIn, exact: true })).toBeVisible();
          await capture(page, `brand-landing-${theme}-${short(language)}-${viewport.width}`);
          await request.click();
          await expect(page.getByRole("heading", { name: language === "en" ? "Request access to Cuadrao" : "Solicita acceso a Cuadrao" })).toBeVisible();
          await expectLockup(page, theme);
          await capture(page, `brand-request-access-${theme}-${short(language)}-${viewport.width}`);
        });

        test(`${short(language)} ${theme} sign-in and signup keep the approved artwork and palette`, async ({ page }) => {
          await offline(page, theme, language);
          await page.goto("/?auth=login&preview=true");
          await expectLockup(page, theme);
          const card = page.locator('[data-auth-brand="cuadrao"].border');
          await expect(card).toContainText(copy.newTo);
          await card.locator('input[type="email"]').fill("ejemplo-local@example.com");
          await card.locator('input[type="password"]').fill("synthetic-local-password");
          const submit = card.locator('button[type="submit"]');
          await expect(submit).toHaveText(copy.signIn);
          await expect(submit).toHaveCSS("background-color", theme === "light" ? "rgb(41, 74, 64)" : "rgb(171, 212, 191)");
          await expect(card.locator('a[href^="/auth/forgot-password"]')).toHaveAttribute("href", "/auth/forgot-password");
          await capture(page, `brand-signin-${theme}-${short(language)}-${viewport.width}`);
          await card.getByRole("button", { name: copy.signUp, exact: true }).click();
          await expect(card.locator('input[type="text"]')).toBeVisible();
          await expect(card.locator('button[type="submit"]')).toHaveText(copy.signUp);
          await expectLockup(page, theme);
          await expect(page).toHaveTitle("Cuadrao");
          await capture(page, `brand-signup-${theme}-${short(language)}-${viewport.width}`);
        });

        test(`${short(language)} ${theme} Business inbox carries the Cuadrao sidebar brand`, async ({ page }) => {
          await offline(page, theme, language);
          await page.goto("/dev/business-preview?view=inbox");
          await expect(page).toHaveTitle(/Cuadrao$/);
          await expect(page.getByRole("heading", { name: copy.inbox }).first()).toBeVisible();
          if (viewport.width === 390) {
            await page.getByTestId("chat-shell-menu-trigger").click();
          }
          await expect(page.getByText("cuadrao", { exact: true })).toBeVisible();
          await expect(page.getByText("argus", { exact: true })).toHaveCount(0);
          await capture(page, `brand-biz-${theme}-${short(language)}-${viewport.width}`);
          if (viewport.width === 1280) {
            // The rail shows the mark only while collapsed.
            await page.getByRole("button", { name: copy.collapse, exact: true }).click();
          }
          const mark = page.locator(`img[src="/brand/cuadrao-mark-${theme}.svg"]:visible`).first();
          await expect(mark).toBeVisible();
          await expect.poll(() => mark.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
        });
      }
    }
  });
}

test("Personal chat carries the Cuadrao mark, wordmark and tab title; its chat copy is unchanged", async ({ page }) => {
  await offline(page);
  await page.goto("/chat");
  await expect(page.getByTestId("chat-input")).toBeVisible();
  await expect(page).toHaveTitle("Cuadrao");
  await expect(page.getByRole("complementary").getByText("cuadrao", { exact: true })).toBeVisible();
  await expect(page.getByRole("complementary").getByText("argus", { exact: true })).toHaveCount(0);
  const lockup = page.getByRole("main").getByRole("heading", { name: "Cuadrao", exact: true }).locator('img[src="/brand/cuadrao-lockup-light.svg"]');
  await expect(lockup).toBeVisible();
  await expect.poll(() => lockup.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await expect(page.getByRole("heading", { name: "argus" })).toHaveCount(0);
  await capture(page, "brand-personal-chat-spanish-1280");
});
