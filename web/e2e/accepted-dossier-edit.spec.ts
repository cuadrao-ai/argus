import { expect, test } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installReceiptBusiness, reviewAction } from "./support/business-receipt-fixture";

test("an accepted record opened from Bandeja saves a correction and shows the dated approval and revision in Historial", async ({ page }, testInfo) => {
  const id = dossierFixtureIds.recordedThenMarked;
  const source = await installReceiptBusiness(page, ([resource, draft, action], route, data) => {
    if (resource === "receipts" && draft === "rcpt-confirmed" && !action) {
      return data.receipt(draft).then(receipt => ({ ...receipt, draft_id: id }));
    }
    if (resource !== "drafts" || draft !== id || action !== "review") return;
    const request = route.request();
    expect(request.method()).toBe("PATCH");
    const { version, facts } = request.postDataJSON();
    return data.reviewDraft(id, version, facts, request.headers()["idempotency-key"]);
  });
  const original = await source.dossier(id);
  const approval = original.approval_result;
  if (approval?.status !== "recorded") throw new Error("Expected an accepted fixture with a recorded approval");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/biz?view=inbox");
  await page.getByRole("tab", { name: /^Todos/ }).click();
  await reviewAction(page, /Nube Hosting/).click();

  const drawer = page.getByTestId("side-drawer");
  const row = drawer.locator('[data-fact="counterparty"]');
  await row.getByRole("button", { name: /^Editar/ }).click();
  await expect(row.getByRole("button", { name: /^Cancelar/ })).toBeVisible();
  await expect(drawer.getByRole("button", { name: /^Aceptar\b|^Reabrir$/ })).toHaveCount(0);
  await expect(drawer.getByText("Aceptado", { exact: true }).filter({ visible: true })).toHaveCount(0);
  await row.getByRole("textbox").fill("Ferretería Central de Prueba");
  await page.screenshot({ path: testInfo.outputPath("accepted-edit.png"), animations: "disabled" });
  await row.getByRole("button", { name: /^Guardar/ }).click();
  await expect(row).toContainText("Ferretería Central de Prueba");

  await drawer.getByRole("tab", { name: "Historial" }).click();
  const history = drawer.getByTestId("receipt-history");
  const diff = history.getByTestId("history-diff").filter({ hasText: "Ferretería Central de Prueba" });
  await expect(diff.locator("del")).toHaveText(original.facts.counterparty.value!);
  await expect(diff.locator("ins")).toHaveText("Ferretería Central de Prueba");
  const accepted = history.getByRole("listitem").filter({ hasText: "Aceptado" });
  await expect(accepted.locator("time")).toHaveAttribute("datetime", approval.approved_at);
  await page.screenshot({ path: testInfo.outputPath("accepted-history.png"), animations: "disabled" });
});
