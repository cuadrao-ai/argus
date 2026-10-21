import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

async function capture(page: Page, name: string) {
  const directory = process.env.CUADRAO_RECORD_EVIDENCE_DIR;
  if (!directory) return;
  await expect(page.getByText(/^Cargando/)).toHaveCount(0);
  await page.screenshot({ path: `${directory}/${name}.png` });
}

for (const theme of ["light", "dark"] as const) {
  for (const viewport of [{ name: "desktop", width: 1280, height: 900 }, { name: "phone", width: 390, height: 844 }]) {
    test(`Aprobar y siguiente opens the next receipt of the Bandeja: ${theme} ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
      await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
      await page.goto("/dev/business-preview?view=inbox");
      const badge = page.getByTestId("business-inbox-count");
      if (viewport.name === "desktop") await expect(badge).toHaveText("5");
      const rows = page.getByTestId("business-inbox-receipts");
      await expect(rows.getByRole("button", { name: /Ferretería La Esquina/ })).toBeVisible();
      await rows.getByRole("button", { name: /Ferretería La Esquina/ }).click();

      await page.getByLabel("Pagado desde").selectOption({ index: 1 });
      await page.getByRole("button", { name: "Guardar detalles de revisión", exact: true }).click();
      const next = page.getByRole("button", { name: "Aprobar y siguiente", exact: true });
      await expect(next).toBeEnabled();
      await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeEnabled();
      await next.scrollIntoViewIfNeeded();
      await capture(page, `approve-next-${theme}-${viewport.name}`);

      await next.click();
      await expect(page).toHaveURL(/receipt=rcpt-papeleria/);
      await expect(page.getByRole("heading", { name: "Revisar recibo" })).toBeVisible();
      await expect(page.getByLabel("Comercio")).toHaveValue("Papelería Central");
      if (viewport.name === "desktop") await expect(badge).toHaveText("4");
      await capture(page, `next-receipt-${theme}-${viewport.name}`);
    });
  }
}
