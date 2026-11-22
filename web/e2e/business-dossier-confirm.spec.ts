import { expect, test } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import type { ListoGap } from "../lib/business-dossier";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

test.use({ viewport: { width: 1440, height: 1100 } });

const cases = [
  {
    name: "all-confirmable",
    gaps: ["missing_rnc", "missing_ncf"],
    confirmable: ["missing_rnc", "missing_ncf"],
    labels: ["Falta el RNC", "Falta el NCF"],
    canAccept: true,
  },
  {
    name: "mixed-gaps",
    gaps: ["missing_ncf", "unverified_sender"],
    confirmable: ["missing_ncf"],
    labels: ["Falta el NCF", "Remitente sin verificar"],
    canAccept: false,
  },
] satisfies { name: string; gaps: [ListoGap, ...ListoGap[]]; confirmable: ListoGap[]; labels: string[]; canAccept: boolean }[];

for (const { name, gaps, confirmable, labels, canAccept } of cases) {
  test(`receipt confirmation with ${name}`, async ({ page, baseURL }, testInfo) => {
    if (!baseURL || !["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname)) {
      throw new Error("Dossier confirmation evidence requires a loopback app");
    }

    await page.emulateMedia({ reducedMotion: "reduce" });
    const id = dossierFixtureIds.ready;
    await installReceiptBusiness(page, ([resource, draftId, section], route, source) => {
      if (resource === "drafts" && draftId === id && section === "dossier" && route.request().method() === "GET") {
        return source.dossier(id).then((dossier) => ({
          ...dossier,
          bandeja_group: { group: "attention", reason: gaps[0], label: "needs_attention" },
          listo_gaps: gaps,
          confirmable,
        }));
      }
    });
    await page.goto(`/biz?draft=${id}`);
    await page.getByTestId("receipt-review-footer").getByRole("button", { name: /^Aceptar\b/ }).click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog.getByRole("listitem")).toContainText(labels);
    await expect(dialog.getByRole("button", { name: "Corregir", exact: true })).toBeEnabled();
    const acceptAnyway = dialog.getByRole("button", { name: "Aceptar de todos modos", exact: true });
    if (canAccept) await expect(acceptAnyway).toBeEnabled();
    else await expect(acceptAnyway).toHaveCount(0);

    await page.screenshot({ path: testInfo.outputPath(`dossier-confirm-${name}.png`), animations: "disabled" });
  });
}
