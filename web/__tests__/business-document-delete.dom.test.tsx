import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessCapture, ReceiptDetail, ReceiptActivityCounts } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(""), usePathname: () => "/biz", useRouter: () => ({ push() {}, replace() {} }) }));
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
const PREVIEW_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPlkAAAAASUVORK5CYII=";
const cleanups: (() => Promise<void>)[] = [];
let restorePurged = false;
afterEach(async () => { while (cleanups.length) await cleanups.pop()!(); document.body.innerHTML = ""; restorePurged = false; });

async function mount(role: "owner" | "admin" | "editor" | "viewer" = "owner", failFirst = false, noteCount = 0, deletedDossier = false) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(role === "owner" ? null : "synthetic-role");
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const ready = await fixture.receipt("rcpt-ferreteria");
  const blurry = await fixture.receipt("rcpt-blurry");
  const deletion = { actor: { actor_id: "c93a5c81-2f69-4c0d-932e-1a7c5526c941", display_name: "María Pérez" }, at: "2026-11-12T10:00:00Z", purge_at: "2026-11-19T10:00:00Z", key: "earlier-delete", previous_state: { state: "open", group: "attention" as const } };
  let dossierDeleted = true;
  let items: ReceiptDetail[] = [
    { ...blurry, id: "attention", merchant: "Documento equivocado", filename: "Documento equivocado", delete_available: true, bandeja_group: { group: "attention", reason: "unreadable", draft_id: null, version: null } },
    { ...ready, id: "ready", merchant: "Documento listo", delete_available: true, bandeja_group: { group: "listo", reason: null, draft_id: ready.draft_id, version: 1 } },
    { ...ready, id: "reading", merchant: "Documento leyendo", delete_available: false, bandeja_group: { group: "reading", reason: null, draft_id: null, version: null }, bandeja: { por_revisar: false, con_problema: false, leyendo: true } },
    { ...ready, id: "approved", merchant: "Documento aprobado", status: "confirmed", delete_available: false, bandeja_group: { group: null, reason: null, draft_id: null, version: null } },
    { ...(deletedDossier ? ready : blurry), id: "deleted", merchant: "Documento eliminado", filename: "Documento eliminado", status: "dismissed", delete_available: false, restore_available: true, deleted: deletion, bandeja_group: { group: "eliminados", reason: null, draft_id: null, version: null } },
  ];
  let notes: BusinessCapture[] = Array.from({ length: noteCount }, (_, index) => ({ draft_id: index ? `deleted-note-${index}` : "deleted-note", version: 2, revision: 1, source_id: `note-source-${index}`, text: index === 50 ? "Documento antiguo" : index ? `Documento anotado ${index}` : "Documento anotado", received_at: new Date(Date.UTC(2026, 10, 12, 9) - index * 60_000).toISOString(), review_state: "dismissed", deleted: deletion, delete_available: false, restore_available: true, bandeja_group: { group: "eliminados", reason: null, draft_id: index ? `deleted-note-${index}` : "deleted-note", version: 2 } }));
  const counts = (): ReceiptActivityCounts => ({ reading_count: 1, unread_count: 0, presentation: "none", pending_review_count: 3, needs_attention_count: 1, ready_to_review_count: 1, bandeja_attention_count: 1, bandeja_listo_count: 1, bandeja_eliminados_count: 11 });
  const captureOffsets: number[] = [];
  const calls: { id: string; key: string }[] = [];
  const restores: string[] = [];
  const purges: { id: string; key: string }[] = [];
  const source: BusinessDataSource = {
    ...fixture,
    spaces: async () => (await fixture.spaces()).map(space => ({ ...space, role: role === "owner" ? "owner" : "accountant", business_role: role, grant_id: role === "owner" ? space.grant_id : "synthetic-role", capabilities: role === "owner" ? space.capabilities : role === "viewer" ? ["read"] : ["read", "prepare"] })),
    receipts: async view => view === "all" ? items : items.filter(item => !item.deleted),
    receiptPage: async view => ({ items: view === "all" ? items : items.filter(item => !item.deleted), activity: counts() }),
    receiptActivity: async () => counts(),
    receipt: async id => items.find(item => item.id === id) ?? fixture.receipt(id),
    dossier: async id => {
      const current = await fixture.dossier(deletedDossier ? ready.draft_id! : id);
      return deletedDossier ? {
        ...current, draft_id: id, version: dossierDeleted ? 3 : 4,
        review_state: dossierDeleted ? "dismissed" : "open",
        deleted: dossierDeleted ? deletion : null,
        delete_available: !dossierDeleted, restore_available: dossierDeleted,
        approval_available: !dossierDeleted, approval_action: dossierDeleted ? null : current.approval_action,
        declaration_editable: !dossierDeleted, document_type_editable: !dossierDeleted,
      } : { ...current, delete_available: true, restore_available: false };
    },
    captures: async (_query, limit = 20, view, offset = 0) => {
      if (view === "eliminados") captureOffsets.push(offset);
      const matching = notes.filter(note => view === "eliminados" ? !!note.deleted : !note.deleted);
      return { items: matching.slice(offset, offset + limit), has_more: offset + limit < matching.length };
    },
    receiptSource: async () => new Blob([Buffer.from(PREVIEW_PNG, "base64")], { type: "image/png" }),
    uploadReceipt: async () => items.find(item => item.id === "deleted")!,
    emailDeliveries: async () => [],
    deleteDocument: async (id, key) => {
      calls.push({ id, key });
      if (failFirst && calls.length === 1) throw new Error("synthetic outage");
      items = items.map(item => item.id === id || item.draft_id === id ? { ...item, status: "dismissed", deleted: deletion, delete_available: false, restore_available: true, bandeja_group: { ...item.bandeja_group!, group: "eliminados" } } : item);
      return { document_id: id, deleted: true };
    },
    purgeDocument: async (id, key) => {
      purges.push({ id, key });
      if (failFirst && purges.length === 1) throw new Error("synthetic outage");
      items = items.filter(item => item.id !== id);
      notes = notes.filter(note => note.draft_id !== id);
      return { document_id: id, deleted: true };
    },
    restoreDocument: async id => {
      restores.push(id);
      if (restorePurged) {
        items = items.filter(item => item.id !== id);
        throw Object.assign(new Error("Purged"), { status: 404, code: "business_document_purged" });
      }
      dossierDeleted = false;
      notes = notes.map(note => note.draft_id === id ? { ...note, review_state: "open", deleted: null, delete_available: true, restore_available: false, bandeja_group: { ...note.bandeja_group!, group: "attention" } } : note);
      items = items.map(item => item.id === id || item.draft_id === id ? { ...item, status: "needs_attention", deleted: null, delete_available: true, restore_available: false, bandeja_group: { ...item.bandeja_group!, group: "attention" } } : item);
      return { document_id: id, deleted: false };
    },
  };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  let api: ReturnType<typeof useBusiness>;
  function Probe() { api = useBusiness(); return <BusinessPanel />; }
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><Probe /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>); });
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); setChosenGrant(null); });
  const wait = async (done: () => boolean) => {
    for (let i = 0; i < 80; i++) { await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)); }); if (done()) return; }
    assert.fail(`did not settle: ${document.body.textContent?.slice(0, 600)}`);
  };
  await act(async () => api!.openPanel({ kind: "inbox" }));
  await wait(() => api!.chosen !== null && api!.records.receiptActivity?.bandeja_eliminados_count === 11);
  await wait(() => document.querySelectorAll('[data-testid="reception-row"]').length === 4);
  const click = async (element: HTMLElement | null) => { assert.ok(element); await act(async () => element!.click()); };
  const button = (label: string, within: ParentNode = document) => [...within.querySelectorAll<HTMLButtonElement>("button")].find(node => node.textContent?.trim() === label) ?? null;
  return { act, wait, click, button, calls, restores, purges, captureOffsets, source, items, api: () => api! };
}

test("trash belongs only to the server attention row and only the owner", async () => {
  for (const role of ["owner", "admin", "editor", "viewer"] as const) {
    const page = await mount(role);
    const trash = [...document.querySelectorAll<HTMLButtonElement>('button[aria-label^="Eliminar "]')];
    assert.equal(trash.length, role === "owner" ? 1 : 0);
    if (role === "owner") assert.equal(trash[0].getAttribute("aria-label"), "Eliminar Documento equivocado");
    await page.click(document.getElementById("reception-tab-attention"));
    assert.equal(document.querySelectorAll('button[aria-label^="Eliminar "]').length, role === "owner" ? 1 : 0);
    if (role !== "owner") {
      await page.click(document.getElementById("reception-tab-eliminados"));
      await page.wait(() => !!document.querySelector('[data-testid="deleted-document-row"]'));
      assert.equal(page.button("Restaurar"), null);
      await page.act(async () => page.api().openPanel({ kind: "receipt", receiptId: "ready", list: "inbox" }));
      await page.wait(() => !!document.querySelector('[data-testid="receipt-current-facts"]'));
      assert.equal(document.querySelector('[data-testid="delete-document-menu"]'), null);
    }
    await cleanups.pop()!(); document.body.innerHTML = "";
  }
});

test("delete asks with facts, starts on Cancel and Escape returns to the row", async () => {
  const page = await mount();
  const trash = document.querySelector<HTMLButtonElement>('button[aria-label="Eliminar Documento equivocado"]')!;
  trash.focus();
  await page.click(trash);
  await page.wait(() => document.activeElement?.textContent === "Cancelar");
  const dialog = document.querySelector('[role="alertdialog"]')!;
  assert.match(dialog.textContent ?? "", /¿Eliminar este documento\?/);
  assert.match(dialog.textContent ?? "", /Contraparte.*Fecha.*Total.*Archivo.*Estado/);
  assert.ok(page.button("Ver documento", dialog));
  await page.act(async () => { document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  await page.wait(() => !document.querySelector('[role="alertdialog"]'));
  assert.equal(page.calls.length, 0);
  assert.equal(document.activeElement, trash);
});

test("Ver documento opens the existing review and pins the confirmation bar", async () => {
  const page = await mount();
  await page.click(document.querySelector('button[aria-label="Eliminar Documento equivocado"]'));
  await page.click(page.button("Ver documento", document.querySelector('[role="alertdialog"]')!));
  await page.wait(() => !!document.querySelector('[data-testid="document-delete-bar"]'));
  assert.equal(page.api().panel.kind, "receipt");
  assert.equal(document.querySelectorAll('[role="alertdialog"]').length, 0);
  assert.equal(document.querySelectorAll('[data-testid="receipt-original-source"]').length, 1);
  await page.click(page.button("Cancelar", document.querySelector('[data-testid="document-delete-bar"]')!));
  assert.equal(document.querySelector('[data-testid="document-delete-bar"]'), null);
});

test("Más offers deletion for a ready document with the same dialog and no viewer link", async () => {
  const page = await mount();
  await page.act(async () => page.api().openPanel({ kind: "receipt", receiptId: "ready", list: "inbox" }));
  await page.wait(() => !!document.querySelector('[data-testid="delete-document-menu"]'));
  await page.click(document.querySelector('[data-testid="receipt-more"] > button'));
  await page.click(document.querySelector('[data-testid="delete-document-menu"]'));
  const dialog = document.querySelector('[role="alertdialog"]')!;
  assert.ok(dialog);
  assert.equal(page.button("Ver documento", dialog), null);
});

test("a failed delete retries its action key and the deleted document leaves Todos", async () => {
  const page = await mount("owner", true);
  await page.click(document.querySelector('button[aria-label="Eliminar Documento equivocado"]'));
  await page.click(page.button("Eliminar", document.querySelector('[role="alertdialog"]')!));
  await page.wait(() => !!document.querySelector('[data-testid="confirm-dialog-error"]'));
  await page.click(page.button("Eliminar", document.querySelector('[role="alertdialog"]')!));
  await page.wait(() => !document.querySelector('[role="alertdialog"]'));
  assert.equal(page.calls.length, 2);
  assert.equal(page.calls[0].key, page.calls[1].key);
  await page.wait(() => document.querySelectorAll('[data-testid="reception-row"]').length === 3);
});

test("Eliminados uses the server count, lists provenance and restores with a Ver toast", async () => {
  const page = await mount();
  const tab = document.getElementById("reception-tab-eliminados")!;
  assert.match(tab.textContent ?? "", /11/);
  await page.click(tab);
  const row = document.querySelector('[data-testid="deleted-document-row"]')!;
  assert.match(row.textContent ?? "", /Documento eliminado.*Necesitan atención.*María Pérez/);
  await page.click(page.button("Restaurar", row));
  await page.wait(() => !document.querySelector('[data-testid="deleted-document-row"]'));
  assert.deepEqual(page.restores, ["deleted"]);
  assert.match(document.body.textContent ?? "", /Documento restaurado en la Bandeja/);
  await page.click(document.getElementById("reception-tab-all"));
  await page.wait(() => !!document.querySelector('button[aria-label="Eliminar Documento eliminado"]'));
  await page.click(page.button("Ver"));
  await page.wait(() => page.api().panel.kind === "receipt");
});


test("an exact repeat upload says it is deleted and offers the owner's restore", async () => {
  const page = await mount();
  await page.act(async () => page.api().actions.create.find(action => action.id === "upload_receipt")!.run());
  await page.wait(() => !!document.querySelector('input[type="file"]'));
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  Object.defineProperty(input, "files", { configurable: true, value: [new File(["synthetic pdf"], "wrong.pdf", { type: "application/pdf" })] });
  await page.act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
  await page.wait(() => !!document.querySelector('[data-testid="receipt-upload-deleted-fold"]'));
  await page.click(document.querySelector<HTMLButtonElement>('[data-testid="receipt-upload-deleted-fold"] button[aria-expanded="false"]'));
  await page.wait(() => document.querySelector('[data-testid="receipt-upload-row"]')?.textContent?.includes("Eliminado antes") === true);
  const row = document.querySelector('[data-testid="receipt-upload-row"]')!;
  await page.click(page.button("Restaurar", row));
  await page.wait(() => !document.querySelector('[data-testid="receipt-upload-deleted-fold"]'));
  assert.deepEqual(page.restores, ["deleted"]);
});


test("Eliminados restores a standalone note draft to its server attention row", async () => {
  const page = await mount("owner", false, 1);
  await page.click(document.getElementById("reception-tab-eliminados"));
  const noteRow = () => [...document.querySelectorAll('[data-testid="deleted-document-row"]')].find(row => row.textContent?.includes("Documento anotado"));
  await page.wait(() => !!noteRow());
  await page.click(page.button("Restaurar", noteRow()!));
  await page.wait(() => !noteRow());
  assert.deepEqual(page.restores, ["deleted-note"]);
  await page.click(document.getElementById("reception-tab-attention"));
  await page.wait(() => !!document.querySelector('button[aria-label="Eliminar Documento anotado"]'));
  await page.click(document.getElementById("reception-tab-all"));
  assert.ok(document.querySelector('button[aria-label="Eliminar Documento anotado"]'));
});


test("an older deleted note beyond the first server page can be found and restored", async () => {
  const page = await mount("owner", false, 51);
  await page.click(document.getElementById("reception-tab-eliminados"));
  await page.wait(() => document.querySelectorAll('[data-testid="deleted-document-row"]').length > 0);
  await page.click(page.button("3"));
  const oldest = () => [...document.querySelectorAll('[data-testid="deleted-document-row"]')].find(row => row.textContent?.includes("Documento antiguo"));
  await page.wait(() => !!oldest());
  assert.deepEqual(page.captureOffsets, [0, 50]);
  await page.click(page.button("Restaurar", oldest()!));
  await page.wait(() => !oldest());
  assert.deepEqual(page.restores, ["deleted-note-50"]);
  await page.click(document.getElementById("reception-tab-all"));
  await page.wait(() => !!document.querySelector('button[aria-label="Eliminar Documento antiguo"]'));
});


test("the dialog preview renders the source through a CSP-safe data URL", async () => {
  const page = await mount();
  await page.click(document.querySelector('button[aria-label="Eliminar Documento equivocado"]'));
  const preview = () => document.querySelector<HTMLImageElement>('[data-testid="document-delete-facts"] img');
  await page.wait(() => !!preview());
  assert.equal(preview()!.getAttribute("src"), `data:image/png;base64,${PREVIEW_PNG}`);
  assert.equal(preview()!.width, 64);
  assert.equal(preview()!.height, 80);
});

for (const kind of ["draft", "receipt"] as const) {
  test(`restoring an open ${kind} dossier updates the same panel and the toast Ver keeps it editable`, async () => {
    const page = await mount("owner", false, 1, true);
    await page.act(async () => page.api().openPanel(kind === "receipt"
      ? { kind: "receipt", receiptId: "deleted", list: "inbox" }
      : { kind: "draft", draftId: "deleted-note", list: "inbox" }));
    await page.wait(() => !!page.button("Restaurar"));
    const frame = document.querySelector('[data-testid="business-record-review"]');
    const fields = document.querySelector('[data-testid="receipt-current-facts"]');
    assert.ok(frame);
    assert.ok(fields);
    assert.equal(page.button("Aprobar")?.disabled, true);
    assert.equal(fields.querySelector('button[aria-label^="Editar detalles"]'), null);

    await page.click(page.button("Restaurar"));

    assert.equal(page.button("Restaurar") === null, true, "Restaurar must disappear after the current dossier reloads");
    assert.equal(document.querySelector('[data-testid="business-record-review"]'), frame);
    assert.equal(page.api().panel.kind, kind);
    assert.equal(page.button("Aprobar")?.disabled, false);
    assert.ok(fields.querySelector('button[aria-label^="Editar detalles"]'));
    await page.click(page.button("Ver", document.querySelector('[data-testid="toast-viewport"]')!));
    assert.equal(document.querySelector('[data-testid="business-record-review"]'), frame);
    assert.equal(page.button("Restaurar"), null);
    assert.equal(page.button("Aprobar")?.disabled, false);
    await page.click(fields.querySelector<HTMLButtonElement>('button[aria-label^="Editar detalles"]'));
    assert.ok(fields.querySelector('[data-row-open]'));
  });
}

for (const kind of ["draft", "receipt"] as const) {
  test(`the ${kind} dossier Más delete closes the panel after server success`, async () => {
    const page = await mount();
    const ready = await page.source.receipt("ready");
    assert.ok(ready.draft_id);
    await page.act(async () => page.api().openPanel(kind === "receipt"
      ? { kind: "receipt", receiptId: ready.id, list: "inbox" }
      : { kind: "draft", draftId: ready.draft_id!, list: "inbox" }));
    await page.wait(() => !!document.querySelector('[data-testid="delete-document-menu"]'));
    await page.click(document.querySelector('[data-testid="receipt-more"] > button'));
    await page.click(document.querySelector('[data-testid="delete-document-menu"]'));
    await page.click(page.button("Eliminar", document.querySelector('[role="alertdialog"]')!));
    await page.wait(() => page.api().panel.kind === "inbox");
    assert.equal(document.querySelector('[data-testid="business-record-review"]'), null);
    assert.equal(document.querySelector('[data-testid="delete-document-bar"]'), null);
    assert.equal(document.querySelector('[role="alertdialog"]'), null);
    assert.equal(page.calls[0].id, ready.draft_id);

  });
}

test("Eliminados lines each row up with its headers: who on one line, when on its own quiet line, and the actions as one group", async () => {
  const page = await mount();
  await page.click(document.getElementById("reception-tab-eliminados"));
  const row = document.querySelector('[data-testid="deleted-document-row"]')!;
  const headers = [...document.querySelectorAll('[data-testid="deleted-columns"] > span')];
  assert.deepEqual(headers.map(header => header.textContent), ["Contenido", "Estaba en", "Eliminado por", "Se elimina", "Acciones"]);
  assert.equal(row.children.length, headers.length, "every header has its cell");
  const actor = row.querySelector('[data-testid="deleted-actor"]')!;
  assert.deepEqual([...actor.children].map(line => line.tagName), ["SPAN", "TIME"], "the name and the time are two lines");
  assert.equal(actor.children[0].textContent, "María Pérez");
  assert.equal(actor.children[1].getAttribute("datetime"), "2026-11-12T10:00:00Z");
  assert.doesNotMatch(actor.textContent ?? "", /·/);
  const actions = row.lastElementChild!;
  assert.deepEqual([...actions.querySelectorAll("button")].map(button => button.getAttribute("aria-label") ?? button.textContent), ["Eliminar definitivamente Documento eliminado", "Ver", "Restaurar"]);
  assert.equal(actions.querySelector('[data-testid="purge-document"]')!.textContent, "", "the hidden action is an icon, so showing it moves nothing");
});

test("Eliminados counts down to the server's purge day", async () => {
  const { purgeDays } = await import("@/components/business-app/recepcion/ReceptionDeletedRow");
  const now = new Date(2026, 10, 13, 9);
  assert.equal(purgeDays(new Date(2026, 10, 20, 8).toISOString(), now), 7);
  assert.equal(purgeDays(new Date(2026, 10, 14, 23).toISOString(), now), 1);
  assert.equal(purgeDays(new Date(2026, 10, 13, 23).toISOString(), now), 0);
  assert.equal(purgeDays(new Date(2026, 10, 12, 23).toISOString(), now), 0);
  const page = await mount();
  await page.click(document.getElementById("reception-tab-eliminados"));
  const countdown = document.querySelector('[data-testid="purge-countdown"]')!;
  assert.equal(countdown.getAttribute("datetime"), "2026-11-19T10:00:00Z");
  const days = purgeDays("2026-11-19T10:00:00Z");
  assert.equal(countdown.textContent, days > 0 ? `Se elimina en ${days} ${days === 1 ? "día" : "días"}` : "Se elimina hoy");
  assert.match(document.body.textContent ?? "", /Se eliminan definitivamente 7 días después/);
});

test("Eliminar definitivamente asks without Estado, retries its key and leaves no undo", async () => {
  const page = await mount("owner", true);
  await page.click(document.getElementById("reception-tab-eliminados"));
  const trigger = document.querySelector<HTMLButtonElement>('[data-testid="purge-document"]')!;
  assert.equal(trigger.getAttribute("aria-label"), "Eliminar definitivamente Documento eliminado");
  trigger.focus();
  await page.click(trigger);
  await page.wait(() => document.activeElement?.textContent === "Cancelar");
  const dialog = document.querySelector('[role="alertdialog"]')!;
  assert.match(dialog.textContent ?? "", /¿Eliminar definitivamente\?/);
  assert.match(dialog.textContent ?? "", /Contraparte.*Fecha.*Total.*Archivo/);
  assert.doesNotMatch(dialog.textContent ?? "", /Estado/);
  assert.match(dialog.textContent ?? "", /No se puede deshacer\. El archivo y sus datos se borran de Cuadrao\./);
  await page.act(async () => { document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  await page.wait(() => !document.querySelector('[role="alertdialog"]'));
  assert.equal(page.purges.length, 0);
  await page.click(trigger);
  await page.wait(() => !!document.querySelector('[role="alertdialog"]'));
  await page.click(document.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]'));
  await page.wait(() => !!document.querySelector('[data-testid="confirm-dialog-error"]'));
  assert.match(document.querySelector('[data-testid="confirm-dialog-error"]')!.textContent ?? "", /No se pudo eliminar definitivamente el documento/);
  await page.click(document.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]'));
  await page.wait(() => !document.querySelector('[data-testid="deleted-document-row"]'));
  assert.equal(page.purges.length, 2);
  assert.equal(page.purges[0].key, page.purges[1].key);
  assert.equal(page.purges[0].id, "deleted");
  assert.match(document.body.textContent ?? "", /Documento eliminado definitivamente/);
  assert.equal(page.button("Deshacer"), null);
  assert.match(document.body.textContent ?? "", /Los documentos que elimines quedan aquí 7 días\. Después se eliminan definitivamente\./);
});

test("only the owner sees Eliminar definitivamente", async () => {
  for (const role of ["admin", "editor", "viewer"] as const) {
    const page = await mount(role);
    await page.click(document.getElementById("reception-tab-eliminados"));
    await page.wait(() => !!document.querySelector('[data-testid="deleted-document-row"]'));
    assert.equal(document.querySelector('[data-testid="purge-document"]'), null);
    await cleanups.pop()!();
  }
});

test("restoring a document the expiry already purged says so", async () => {
  restorePurged = true;
  const page = await mount();
  await page.click(document.getElementById("reception-tab-eliminados"));
  const row = document.querySelector('[data-testid="deleted-document-row"]')!;
  await page.click(page.button("Restaurar", row));
  await page.wait(() => /Este documento ya se eliminó definitivamente\./.test(document.body.textContent ?? ""));
  await page.wait(() => !document.querySelector('[data-testid="deleted-document-row"]'));
  assert.doesNotMatch(document.body.textContent ?? "", /No se pudo restaurar/);
});
