import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";
import { BUSINESS_PRIVACY_NOTICE_VERSION } from "../lib/business-privacy-notice";

const evidence = process.env.CUADRAO_CONSENT_EVIDENCE_DIR;

async function setup(page: Page, language: "en" | "es-419") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true, consent: "required" });
  const source = createFixtureBusinessDataSource({ chatAvailable: true });
  await page.route("**/api/v1/business/**", async (route) => {
    const path = new URL(route.request().url()).pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de José" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, needs_attention_count: 0 } } });
    if (path === "receipt-reading") return route.fulfill({ json: { scope_version: 1, enabled: false, available: true, can_change: true, disclosure: "Permiso de prueba", disclosure_token: "a".repeat(64), route: null, consented_at: null, revoked_at: null } });
    if (path === "email") return route.fulfill({ json: { enabled: false, receiving_address: null } });
    if (path === "email/deliveries" || path === "captures" || path === "updates") return route.fulfill({ json: { items: [] } });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}

async function capture(page: Page, name: string) {
  if (!evidence) return;
  await page.screenshot({ path: `${evidence}/${name}.png`, fullPage: true });
}

for (const language of ["es-419", "en"] as const) {
  for (const width of [1280, 390]) {
    test(`privacy notice consent ${language} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await setup(page, language);
      const copy = language === "es-419"
        ? {
            title: "[BORRADOR] Antes de usar IA en tu negocio",
            privacy: "[BORRADOR] Leer el aviso de privacidad",
            notice: "[BORRADOR] Aviso de privacidad de Cuadrao Business",
            declineTitle: "[BORRADOR] Sin este permiso, la IA queda apagada",
            held: "siguen apagados",
            accept: "[BORRADOR] Aceptar y continuar",
            accepted: "[BORRADOR] Aceptación registrada en este navegador",
          }
        : {
            title: "[DRAFT] Before AI is used for your business",
            privacy: "[DRAFT] Read the privacy notice",
            notice: "[DRAFT] Cuadrao Business privacy notice",
            declineTitle: "[DRAFT] Without this permission, AI stays off",
            held: "stay off",
            accept: "[DRAFT] Accept and continue",
            accepted: "[DRAFT] Acceptance kept in this browser",
          };
      const shot = (name: string) => capture(page, `${name}-${language}-${width === 1280 ? "desktop" : "mobile"}`);

      await page.goto("/biz");
      const screen = page.getByTestId("business-consent-screen");
      await expect(screen.getByRole("heading", { name: copy.title })).toBeVisible();
      await expect(screen.getByText(BUSINESS_PRIVACY_NOTICE_VERSION)).toBeVisible();
      const accept = screen.getByTestId("business-consent-accept");
      await expect(accept).toBeDisabled();
      await expect(page.getByTestId("overview-real-expenses")).toHaveCount(0);

      await screen.getByRole("heading", { name: copy.title }).focus();
      await page.keyboard.press("Tab");
      await expect(screen.getByRole("button", { name: copy.privacy })).toBeFocused();
      await page.keyboard.press("Enter");
      const notice = page.getByRole("dialog", { name: copy.notice });
      await expect(notice.getByTestId("business-privacy-notice")).toBeVisible();
      await expect(notice.getByText(/\[A CONFIRMAR\]/)).toBeVisible();
      await shot("privacy");
      await page.keyboard.press("Escape");
      await expect(notice).toHaveCount(0);

      await shot("consent");
      await screen.getByTestId("business-consent-decline").click();
      const declined = page.getByTestId("business-consent-declined");
      await expect(declined.getByRole("heading", { name: copy.declineTitle })).toBeVisible();
      await shot("decline");
      await declined.getByTestId("business-consent-continue-without").click();
      await expect(page.getByTestId("business-consent-held")).toContainText(copy.held);
      await expect(page.getByTestId("overview-real-expenses")).toBeVisible();
      await expect(page.getByTestId("receipt-reading-control")).toHaveCount(0);

      await page.getByTestId("business-consent-held").getByRole("button").click();
      await expect(screen).toBeVisible();
      await expect(accept).toBeDisabled();
      await screen.getByRole("checkbox").check();
      await expect(accept).toBeEnabled();
      await accept.click();
      const saved = page.getByTestId("business-consent-accepted");
      await expect(saved.getByRole("heading", { name: copy.accepted })).toBeVisible();
      await shot("accepted");
      await saved.getByTestId("business-consent-continue").click();
      await expect(page.getByTestId("business-consent-screen")).toHaveCount(0);
      await expect(page.getByTestId("business-consent-held")).toHaveCount(0);
      await expect(page.getByTestId("overview-real-expenses")).toBeVisible();

      await page.reload();
      await expect(page.getByTestId("business-consent-screen")).toHaveCount(0);
      await expect(page.getByTestId("overview-real-expenses")).toBeVisible();
    });
  }
}
