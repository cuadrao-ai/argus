import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

async function offline(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
}

async function capture(page: Page, name: string) {
  if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/${name}.png`, fullPage: true });
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`Business access at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("the owner sees who has access, invites an email and cancels the invite", async ({ page }) => {
      await offline(page);
      await page.goto("/dev/business-preview?view=business&tab=equipo");
      await expect(page.getByRole("heading", { name: "Negocio", exact: true }).first()).toBeVisible();
      await expect(page.getByTestId("business-settings-tabs").getByRole("radio", { name: viewport.width < 720 ? "Equipo" : "Equipo y accesos" })).toHaveAttribute("aria-checked", "true");
      const grants = page.getByTestId("business-access-grants");
      await expect(grants).toContainText("Dueño");
      await expect(grants).toContainText("Tu propio acceso no se puede quitar.");
      await expect(grants).toContainText("Miembro");
      await expect(grants.getByRole("button", { name: "Quitar acceso" })).toHaveCount(1);
      await capture(page, `access-spanish-${viewport.width}`);
      const form = page.getByTestId("business-access-give");
      await form.getByPlaceholder("Correo electrónico").fill("nuevo@example.test");
      await form.getByRole("button", { name: "Dar acceso" }).click();
      const invites = page.getByTestId("business-access-invites");
      await expect(invites.getByText("nuevo@example.test", { exact: true })).toBeVisible();
      await capture(page, `access-invite-spanish-${viewport.width}`);
      await invites.getByRole("button", { name: "Reenviar", exact: true }).click();
      await expect(invites.getByText("nuevo@example.test", { exact: true })).toBeVisible();
      await expect(invites.getByRole("button", { name: "Reenviar", exact: true })).toBeEnabled();
      await invites.getByRole("button", { name: "Cancelar invitación" }).click();
      await expect(page.getByRole("alertdialog")).toContainText("nuevo@example.test");
      await page.getByRole("alertdialog").getByRole("button", { name: "Cancelar invitación" }).click();
      await expect(invites).toHaveCount(0);
      await expect(page.getByText("—")).toHaveCount(0);
    });
  });
}
