import { expect, test } from "@playwright/test";
import { createBusinessReportHttpFixture } from "../__tests__/fixtures/business-report-http-fixture";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

test("an accepted record can be deleted, undone, and restored from Eliminados", async ({ page }, testInfo) => {
  const now = "2026-10-20T15:00:00Z";
  const purgeAt = "2026-10-22T15:00:00Z";
  const merchant = "Taller Rivera";
  const receiptId = "rcpt-confirmed";
  const reports = createBusinessReportHttpFixture();
  const [record] = reports.records.splice(4, 1);
  const draftId = record.draft_id;
  if (!draftId) throw new Error("The report fixture must name a draft.");
  record.counterparty = merchant;
  record.gross_amount = record.recorded_amount = "123.45";
  record.attachment_sources = [{ source_id: draftId, receipt_id: receiptId, filename: "factura.pdf", media_type: "application/pdf", source_available: true, download_available: true }];
  reports.records.splice(0, reports.records.length, record, reports.records[5]);
  let deleted = false;
  const deletion = {
    actor: { actor_id: "30000000-0000-4000-8000-000000000001", display_name: "Ana Peña", shown_as: "name" },
    at: now, purge_at: purgeAt, key: "delete-test", previous_state: { state: "accepted", group: null },
  };

  await page.clock.setFixedTime(new Date(now));
  await installReceiptBusiness(page, (parts, route, source) => {
    const request = route.request();
    if (parts[0] === "reports" || parts[0] === "report-views") {
      return reports.request(request.url(), {
        method: request.method(), headers: request.headers(), body: request.postData() ?? undefined,
      }).then(async (response) => {
        await route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) });
        return null;
      });
    }
    if (parts[0] === "receipts") {
      const group = {
        group: deleted ? "eliminados" : null,
        reason: null, label: deleted ? null : "accepted", draft_id: draftId, version: 4,
      };
      const receipt = source.receipt(receiptId).then((item) => ({
        ...item, draft_id: draftId, merchant, title: merchant, status: deleted ? "dismissed" : "confirmed",
        deleted: deleted ? deletion : null, delete_available: !deleted, restore_available: deleted, bandeja_group: group,
      }));
      if (parts[1] === receiptId && parts.length === 2) return receipt;
      if (parts.length === 1) {
        const view = new URL(request.url()).searchParams.get("view");
        return Promise.all([receipt, source.receiptPage!("inbox").then(({ activity }) => activity)]).then(([item, counts]) => ({
          items: view === "all" && deleted ? [item] : [],
          activity: { ...counts, bandeja_eliminados_count: deleted ? 1 : 0 },
        }));
      }
    }
    if (parts[0] === "drafts" && [draftId, receiptId].includes(parts[1])) {
      const [, id, action] = parts;
      if (action === "dossier") return source.dossier(dossierFixtureIds.recordedThenMarked).then((dossier) => ({
        ...dossier, draft_id: id, title: merchant, review_state: deleted ? "dismissed" : "accepted", personal: false,
        deleted: deleted ? deletion : null, delete_available: !deleted, restore_available: deleted,
        facts: { ...dossier.facts, counterparty: { ...dossier.facts.counterparty, value: merchant } },
      }));
      if (action === "delete" || action === "restore") {
        expect(request.method()).toBe("POST");
        expect(request.headers()["idempotency-key"]).toBeTruthy();
        deleted = action === "delete";
        if (deleted) reports.records.splice(reports.records.indexOf(record), 1);
        else reports.records.unshift(record);
        return source.receiptPage!("inbox").then(({ activity }) => activity).then((counts) => ({
          document_id: id, deleted, purge_at: deleted ? purgeAt : null,
          registros_count: reports.records.length,
          inbox_counts: { ...counts, bandeja_eliminados_count: deleted ? 1 : 0 },
        }));
      }
    }
    return undefined;
  });

  const registros = page.getByRole("grid", { name: "Registros" });
  const recordRow = registros.getByRole("row").filter({ has: page.getByRole("gridcell", { name: "123.45", exact: true }) });
  const dossier = page.getByTestId("business-record-review");
  const toast = page.getByTestId("toast-viewport");
  const deleteRecord = async () => {
    await expect(recordRow).toBeVisible();
    await recordRow.click();
    await expect(page.getByRole("heading", { name: merchant, exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Más", exact: true }).click();
    await page.getByText("Eliminar documento", { exact: true }).click();
    await page.getByRole("button", { name: "Eliminar", exact: true }).click();
    await expect(toast).toContainText("Eliminado. Lo restauras en 2 días desde Eliminados.");
    await expect(dossier).toHaveCount(0);
    await expect(registros).toBeVisible();
    await expect(recordRow).toHaveCount(0);
  };

  await page.goto("/biz?view=transactions");
  await deleteRecord();
  await page.screenshot({ path: testInfo.outputPath("accepted-delete-undo.png"), animations: "disabled" });
  await toast.getByRole("button", { name: "Deshacer", exact: true }).click();
  await expect(recordRow).toBeVisible();

  await deleteRecord();
  await page.getByRole("button", { name: /^Bandeja/ }).click();
  await page.getByRole("tab", { name: /Eliminados/ }).click();
  const deletedRow = page.getByTestId("deleted-document-row").filter({ hasText: merchant });
  await expect(deletedRow.getByText("Registros", { exact: true })).toBeVisible();
  await expect(deletedRow.getByTestId("purge-countdown")).toHaveText("Borrado definitivo en 2 días");
  await page.screenshot({ path: testInfo.outputPath("accepted-delete-eliminados.png"), animations: "disabled" });
  await deletedRow.getByRole("button", { name: "Restaurar", exact: true }).click();
  await expect(toast).toContainText("Documento restaurado en Registros");
  await expect(deletedRow).toHaveCount(0);
  await page.getByRole("button", { name: "Registros", exact: true }).click();
  await expect(recordRow).toBeVisible();
});
