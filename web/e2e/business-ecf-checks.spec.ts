import { expect, test, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

/** The record of an electronic invoice shows what the file proved, and a line to review never blocks approval. */

async function openRecord(page: Page, id: string, language: "en" | "es-419") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  await page.goto(`/dev/business-preview?draft=${id}`);
  await expect(page.getByTestId("business-record-review")).toBeVisible();
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`Electronic invoice verification at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("the card lists each check with its state and keeps approval available", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.fiscal, "es-419");
      const card = page.getByTestId("receipt-ecf-checks");
      await expect(card).toBeVisible();
      await expect(card.getByRole("heading", { name: "Verificación de la factura electrónica" })).toBeVisible();
      await expect(card).toContainText("Contenido sin cambios desde la firma");
      await expect(card).toContainText("Revisar: la lectura difiere del XML en ITBIS");
      await expect(card).toContainText("Aceptación por la DGII no consultada");
      await expect(card.locator('[data-state="failed"]')).toHaveCount(1);
      await expect(card.locator("li")).toHaveCount(6);
      await expect(card).toContainText("El código QR coincide con lo leído");
      const verify = card.getByTestId("receipt-dgii-verify");
      await expect(verify).toHaveAttribute("href", /^https:\/\/ecf\.dgii\.gov\.do\//);
      await expect(verify).toHaveAttribute("target", "_blank");
      await expect(verify).toHaveAttribute("rel", "noopener noreferrer");
      await expect(verify).toHaveText("Verificar en DGII");
      await expect(card).toContainText("Vigente en la fecha que declara el documento");
      // The fixture was checked days ago; the relative time says so in words.
      await expect(card).toContainText(/comprobado (hace|anteayer|ayer)/);
      await expect(card).not.toContainText("firma verificada");
      await expect(card).not.toContainText("al firmar");
      // A line to review is information for a person, never a blocker.
      await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toHaveCount(1);
    });

    test("a record from any other source shows no card", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.ready, "en");
      await expect(page.getByTestId("receipt-ecf-checks")).toHaveCount(0);
    });
  });
}
