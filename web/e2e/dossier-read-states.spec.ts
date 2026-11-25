import { expect, test, type Locator } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import type { ReceiptDetail } from "../lib/business-api";
import type { BusinessDossier, BusinessSupportingFile } from "../lib/business-dossier";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

const file = "lectura-de-prueba.svg";
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="440"><rect width="320" height="440" fill="white"/><text x="32" y="64" font-size="20">Comprobante de prueba</text></svg>';

const activeLoops = (region: Locator) => region.evaluate((element) =>
  element.getAnimations({ subtree: true }).filter(animation => animation.effect?.getTiming().iterations === Infinity).length,
);

for (const state of ["reading", "held", "failed"] as const) {
  for (const motion of state === "reading" ? ["no-preference", "reduce"] as const : ["no-preference"] as const) {
    test(`dossier shows the server's ${state} receipt with ${motion} motion`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.emulateMedia({ reducedMotion: motion });
      const source = createFixtureBusinessDataSource();
      const base = await source.receipt("rcpt-blurry");
      const reading = state === "reading";
      const failed = state === "failed";
      const receipt: ReceiptDetail = {
        ...base, draft_id: null, merchant: null, filename: file, media_type: "image/svg+xml",
        status: reading ? "queued" : "needs_attention", attention: reading ? null : failed ? "not_a_receipt" : "read_budget_day",
        error_code: reading ? null : failed ? "not_a_receipt" : "business_read_budget_day",
        enterable: false, preparable: state === "held", read_pending: reading, delete_available: true, activity: null,
        bandeja: { por_revisar: false, con_problema: failed, leyendo: reading },
        bandeja_group: { group: failed ? "attention" : "reading", reason: failed ? "not_a_receipt" : "reading", label: failed ? "cant_read" : "reading", draft_id: null, version: null },
      };
      await installReceiptBusiness(page, (parts, route) => {
        if (parts[0] !== "receipts" || parts[1] !== receipt.id) return undefined;
        if (parts.length === 2) return Promise.resolve(receipt);
        if (parts[2] === "source") return route.fulfill({ contentType: "image/svg+xml", body: svg }).then(() => null);
        return undefined;
      }, state === "held" ? "dark" : "light");
      await page.goto(`/biz?receipt=${receipt.id}`);
      const drawer = page.getByTestId("side-drawer");
      const fields = drawer.getByRole("tabpanel", { name: "General", exact: true });
      await expect(drawer.getByRole("heading", { name: file })).toBeVisible();
      await expect(drawer.getByText(failed ? "No se pudo leer" : "Leyendo…", { exact: true }).first()).toBeVisible();
      await expect(drawer.getByRole("tab", { name: "Datos fiscales" })).toHaveCount(0);
      if (failed) {
        await expect(fields.getByText("Esto no parece un recibo", { exact: true })).toBeVisible();
        await expect(drawer.getByRole("button", { name: "Subir otro documento", exact: true })).toBeVisible();
        await expect(drawer.getByRole("button", { name: "Leer de nuevo" })).toHaveCount(0);
      } else {
        if (state === "held") await expect(fields).toContainText("Hoy se alcanzó el límite de lecturas.");
        await expect(fields).not.toContainText("%");
        await expect(fields.locator("input,select")).toHaveCount(0);
        const original = drawer.getByTestId("receipt-review-source");
        await expect(original.getByTestId("receipt-viewer")).toBeVisible();
        if (reading && motion === "no-preference") {
          await expect.poll(() => activeLoops(original)).toBeGreaterThanOrEqual(2);
        } else {
          await expect.poll(() => activeLoops(original)).toBe(0);
          await expect.poll(() => activeLoops(fields)).toBe(0);
        }
        const remove = drawer.getByRole("button", { name: "Eliminar documento", exact: true });
        await expect(remove).toBeVisible();
        await expect(drawer.getByTestId("dossier-size")).toBeEnabled();
      }
      await page.screenshot({ path: testInfo.outputPath(`dossier-${state}-${motion}.png`) });
      if (reading && motion === "no-preference") {
        const remove = drawer.getByRole("button", { name: "Eliminar documento", exact: true });
        await expect(remove).toHaveText("Eliminar documento", { useInnerText: true });
        await drawer.getByTestId("dossier-size").click();
        await expect(drawer.getByRole("tab", { name: "Documento", exact: true })).toBeVisible();
        await expect(remove).toBeVisible();
        await expect(remove).toHaveText("", { useInnerText: true });
        await page.screenshot({ path: testInfo.outputPath("dossier-reading-narrow.png") });
      }
    });
  }
}

test("an owner can recover an interrupted read with an expired preparation grant", async ({ page }, testInfo) => {
  const prepared = await createFixtureBusinessDataSource().receipt("rcpt-ferreteria");
  const receipt: ReceiptDetail = {
    ...prepared, status: "needs_attention", activity: { state: "read_failed", unread: false, completion_cursor: null },
    merchant: null, draft_id: null, preparable: true, read_pending: false,
    attention: "interrupted", error_code: "business_record_not_found",
    bandeja_group: { group: "attention", reason: "interrupted", label: "cant_read", draft_id: null, version: null },
  };
  const writes: string[] = [];
  await installReceiptBusiness(page, ([resource, id, action], route) => {
    if (resource !== "receipts" || id !== receipt.id) return;
    if (!action) return Promise.resolve(writes.includes("prepare") ? prepared : receipt);
    if (route.request().method() === "POST" && (action === "rebind" || action === "prepare")) {
      writes.push(action);
      return Promise.resolve(action === "prepare" ? prepared : receipt);
    }
  });
  await page.goto(`/biz?receipt=${receipt.id}`);
  const rebind = page.getByRole("button", { name: "Vincular a mi acceso actual", exact: true });
  await expect(rebind).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("dossier-interrupted-grant.png"), animations: "disabled" });
  await rebind.click();
  await expect(page.locator('[data-fact="amount"]')).toBeVisible();
  expect(writes).toEqual(["rebind", "prepare"]);
});

test("Detalles edits a record note and opens its supporting file in the document pane", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const source = createFixtureBusinessDataSource();
  const receipt = await source.receipt("rcpt-ferreteria");
  const base = await source.dossier(receipt.draft_id!);
  const id = "00000000-0000-4000-8000-000000000197";
  const support = { source_id: "00000000-0000-4000-8000-000000000198", receipt_id: "00000000-0000-4000-8000-000000000199", filename: "orden-de-compra.svg", media_type: "image/svg+xml", size_bytes: 8251, state: "linked" as const, unlink_available: true, restore_available: false, purge_at: null };
  let dossier = { ...base, draft_id: id, space_id: "fixture-space", current_note: "Revisar la orden.", note_edit_available: true, supporting_append_available: true, supporting_files: [support], annotation_unavailable_reason: null };
  await installReceiptBusiness(page, ([resource, target, action], route) => {
    if (resource === "drafts" && target === id) {
      if (action === "dossier") return Promise.resolve(dossier);
      if (action === "current-note") {
        const { note, expected_version } = route.request().postDataJSON();
        expect(expected_version).toBe(dossier.version);
        const version = dossier.version + 1;
        dossier = { ...dossier, version, current_note: note };
        return Promise.resolve({ result: { draft_id: id, version, note }, dossier });
      }
    }
    if (resource === "receipts" && target === support.receipt_id && action === "source") {
      return route.fulfill({ contentType: "image/svg+xml", body: svg }).then(() => null);
    }
  });
  await page.goto(`/biz?draft=${id}`);
  await page.getByRole("tab", { name: "Detalles", exact: true }).click();
  const details = page.getByRole("tabpanel", { name: "Detalles" });
  await details.getByRole("button", { name: "Editar nota" }).click();
  const note = details.getByRole("textbox", { name: "Nota" });
  await note.fill("Orden verificada.");
  await note.press("Control+Enter");
  await expect(details.getByText("Orden verificada.", { exact: true })).toBeVisible();
  await details.getByRole("button", { name: /^Ver\b/ }).click();
  const foot = page.getByTestId("dossier-document-foot");
  await expect(foot.getByRole("link")).toHaveAttribute("download", support.filename);
  await page.screenshot({ path: testInfo.outputPath("dossier-note-and-backing-file.png"), animations: "disabled" });
});

test("Detalles keeps a removed file until the server withdraws its link-back offer", async ({ page }, testInfo) => {
  const source = createFixtureBusinessDataSource();
  const receipt = await source.receipt("rcpt-ferreteria");
  const base = await source.dossier(receipt.draft_id!);
  const sourceId = "00000000-0000-4000-8000-000000000198";
  const linked: BusinessSupportingFile = {
    source_id: sourceId, receipt_id: "00000000-0000-4000-8000-000000000199", filename: "respaldo.pdf",
    media_type: "application/pdf", size_bytes: 512, state: "linked", purge_at: null,
    unlink_available: true, restore_available: false,
  };
  let dossier: BusinessDossier = { ...base, space_id: "fixture-space", current_note: null, note_edit_available: true,
    supporting_append_available: true, annotation_unavailable_reason: null, supporting_files: [linked] };
  let now = "2026-11-15T16:00:00Z";
  let purgeAt = "2026-11-22T16:00:00Z";
  await page.clock.setFixedTime(new Date(now));
  await installReceiptBusiness(page, ([resource, target, action, fileId, command], route) => {
    if (resource !== "drafts" || target !== dossier.draft_id) return;
    if (action === "dossier") return Promise.resolve(dossier);
    if (action !== "supporting-files" || fileId !== sourceId) return;
    const restoring = command === "restore";
    expect(route.request().method()).toBe(restoring ? "POST" : "DELETE");
    expect(route.request().headers()["x-draft-version"]).toBe(String(dossier.version));
    const outcome = restoring ? "restored" : "unlinked";
    const version = dossier.version + 1;
    const file: BusinessSupportingFile = restoring ? linked : {
      ...linked, state: "unlinked", purge_at: purgeAt, restore_available: true, unlink_available: false,
    };
    dossier = { ...dossier, version, supporting_files: [file], history: [...dossier.history, {
      // A person's save over the record's facts, as the server writes a supporting file change.
      ...base.history.at(-1)!, before: base.facts, after: base.facts, version, created_at: now, supporting_change: outcome,
      source_ids: [sourceId], supporting_filename: linked.filename,
    }] };
    return Promise.resolve({ result: { draft_id: target, version, outcome, source_id: sourceId, purge_at: file.purge_at }, dossier });
  });
  const details = page.getByRole("tab", { name: "Detalles", exact: true });
  const row = page.getByTestId("dossier-supporting").getByRole("listitem").filter({ hasText: "respaldo.pdf" });
  const unlink = row.getByRole("button", { name: /^Quitar/ });
  await page.goto(`/biz?draft=${dossier.draft_id}`);
  await details.click();
  await unlink.click();
  await expect(row).toContainText("Se borra en 7 días");
  now = "2026-11-21T16:00:00Z";
  await page.clock.setFixedTime(new Date(now));
  await page.reload();
  await details.click();
  await expect(row).toContainText("Se borra mañana");
  await expect(row.getByRole("button")).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("dossier-supporting-file-link-back.png"), animations: "disabled" });

  await row.getByRole("button", { name: "Restaurar respaldo.pdf", exact: true }).click();
  await expect(unlink).toBeVisible();
  await expect(row).not.toContainText("Se borra");
  purgeAt = "2026-11-28T16:00:00Z";
  await unlink.click();
  await expect(row).toContainText("Se borra en 7 días");

  dossier = { ...dossier, supporting_files: dossier.supporting_files!.map(file => ({ ...file, restore_available: false })) };
  await page.reload();
  await details.click();
  await expect(row).toHaveCount(0);
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  const removals = page.getByTestId("history-supporting").filter({ hasText: "Archivo quitado" });
  await expect(removals).toHaveCount(2);
  await expect(removals.getByRole("button")).toHaveCount(0);
  await expect(removals.getByText(/Se borra|respaldo.pdf/)).toHaveCount(0);
});
