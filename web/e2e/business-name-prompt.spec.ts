import { expect, test } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

for (const width of [1280, 390]) {
  test.describe(`Business name ${width}px`, () => {
    test.use({ viewport: { width, height: 844 } });
    test("owner skips once then saves before inviting", async ({ page }, testInfo) => {
      await page.route("**/*", route => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
      await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true, consent: "required" });
      const source = createFixtureBusinessDataSource({ chatAvailable: false });
      const state = { name: "Mi negocio", seen: false, invites: 0, consentedAt: null as string | null };
      const space = () => ({ id: "fixture-space", name: state.name, name_required: state.name === "Mi negocio", name_prompt_seen: state.seen });
      await page.route("**/api/v1/business/**", async route => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname.split("/business/")[1];
        if (path === "consent") {
          if (request.method() === "POST") state.consentedAt ??= new Date().toISOString();
          const version = request.method() === "POST" ? request.postDataJSON().version : url.searchParams.get("version");
          return route.fulfill({ json: { version, accepted_at: state.consentedAt } });
        }
        if (path === "space/name-prompt") {
          const show = !state.seen && space().name_required;
          state.seen = true;
          return route.fulfill({ json: { ...space(), show_prompt: show } });
        }
        if (path === "space" || path === "space/name") {
          if (request.method() === "PATCH") state.name = request.postDataJSON().name;
          return route.fulfill({ json: space() });
        }
        if (path === "spaces") return route.fulfill({ json: { spaces: [{ space_id: "fixture-space", name: state.name, grant_id: "owner-grant", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true }] } });
        if (path === "workspace") return route.fulfill({ json: await source.workspace() });
        if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
        if (path === "fiscal-profile") {
          if (request.method() === "PATCH") state.name = request.postDataJSON().name;
          return route.fulfill({ json: { name: state.name, tax_id: null, can_edit: true } });
        }
        if (path === "access") {
          if (request.method() === "POST") state.invites++;
          return route.fulfill({ json: { grants: [], invites: [] } });
        }
        if (["receipts", "captures"].includes(path)) return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none" } } });
        return route.fulfill({ status: 404, json: { code: "fixture_only" } });
      });
      await page.goto("/biz");
      const dialog = page.getByRole("dialog", { name: "¿Cómo se llama tu negocio?", exact: true });
      const consent = page.getByTestId("business-consent-screen");
      await expect(consent).toBeVisible();
      await expect(dialog).toHaveCount(0);
      expect(state.seen).toBe(false);
      await consent.getByRole("checkbox").check();
      await consent.getByRole("button", { name: "Continuar", exact: true }).click();
      await expect(page.getByTestId("workspace-panel-region")).toBeVisible();
      if (process.env.NAME_PROMPT_BASELINE === "1") {
        await page.screenshot({ path: testInfo.outputPath(`business-name-before-${width}.png`) });
        return;
      }
      await expect(dialog).toBeVisible();
      await expect(dialog.getByLabel("Nombre del negocio", { exact: true })).toBeFocused();
      const save = dialog.getByRole("button", { name: "Guardar", exact: true });
      await expect.poll(async () => { const box = await save.boundingBox(); return box ? box.y + box.height : 1000; }).toBeLessThanOrEqual(844);
      await page.screenshot({ path: testInfo.outputPath(`business-name-after-${width}.png`) });
      await page.evaluate(() => {
        (window as Window & { namingDismissed?: boolean }).namingDismissed = false;
        window.addEventListener("popstate", () => { (window as Window & { namingDismissed?: boolean }).namingDismissed = true; }, { once: true });
      });
      await dialog.getByRole("button", { name: "Ahora no", exact: true }).click();
      await page.waitForFunction(() => (window as Window & { namingDismissed?: boolean }).namingDismissed);
      await page.reload();
      await expect(page.getByTestId("workspace-panel-region")).toBeVisible();
      await expect(consent).toHaveCount(0);
      await expect(dialog).toHaveCount(0);
      expect(state.seen).toBe(true);
      await page.goto("/biz?view=business&tab=equipo");
      await page.getByRole("textbox", { name: /correo/i }).fill("accountant@example.test");
      await page.getByRole("button", { name: /Dar acceso/i }).click();
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole("button")).toHaveCount(1);
      await page.keyboard.press("Escape");
      await expect(dialog).toBeVisible();
      expect(state.invites).toBe(0);
      await page.screenshot({ path: testInfo.outputPath(`business-name-required-${width}.png`) });
      await dialog.getByLabel("Nombre del negocio", { exact: true }).fill("Colmado La Esquina");
      await dialog.getByRole("button", { name: "Guardar y continuar" }).click();
      await expect(dialog).toHaveCount(0);
      await expect.poll(() => state.invites).toBe(1);
      expect(state.name).toBe("Colmado La Esquina");
      await expect(page.getByRole("button", { name: "Colmado La Esquina", exact: true })).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`business-name-saved-${width}.png`) });
      // The name lives in Negocio > Datos, reached from the business card.
      await page.getByTestId("business-switcher").getByRole("button", { name: "Colmado La Esquina", exact: true }).click();
      await page.getByRole("menuitem", { name: "Configurar negocio" }).click();
      await expect(page.getByTestId("business-settings-tabs").getByRole("radio", { name: "Datos", exact: true })).toHaveAttribute("aria-checked", "true");
      const businessName = page.getByTestId("business-fiscal-profile").getByRole("textbox", { name: "Nombre del negocio", exact: true });
      await expect(businessName).toHaveValue("Colmado La Esquina");
      await page.screenshot({ path: testInfo.outputPath(`business-name-settings-${width}.png`) });
      await businessName.fill("Colmado La Esquina Norte");
      await page.getByTestId("business-fiscal-profile").getByRole("button", { name: "Guardar", exact: true }).click();
      await expect.poll(() => state.name).toBe("Colmado La Esquina Norte");
    });
  });
}
