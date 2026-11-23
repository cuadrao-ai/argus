import assert from "node:assert/strict";
import { test } from "bun:test";
import { button, fill, mount, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

const noteSelector = '[data-testid="dossier-note"] textarea';
const dialog = () => document.querySelector('[role="alertdialog"]');

function warnsOnReload() {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

test("Nota keeps unsaved text through tabs, a same-record entry, and canceled navigation", async () => {
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const id = dossierFixtureIds.ready;
  const panel = { kind: "draft", draftId: id, detailsCard: "note" } as const;
  const stored = "Nota guardada";
  const typed = "Nota todavía sin guardar";
  const page = await mount((fixture) => ({
    mode: "live",
    dossier: async (draft) => ({ ...await fixture.dossier(draft), space_id: "fixture-space", current_note: stored, note_edit_available: true }),
  }), "synthetic-person");
  const field = () => page.host.querySelector<HTMLTextAreaElement>(noteSelector);
  try {
    await page.open(panel, () => field()?.value === stored);
    assert.equal(warnsOnReload(), false, "opening the editor changes nothing");
    await fill(page, noteSelector, typed, HTMLTextAreaElement);
    assert.equal(field()?.value, typed);
    assert.equal(warnsOnReload(), true, "a reload or a closed browser tab warns before losing the note");

    for (const tab of ["general", "detalles"]) {
      await page.act(async () => page.host.querySelector<HTMLButtonElement>(`[data-tab="${tab}"]`)!.click());
      assert.equal(dialog(), null);
      assert.equal(field()?.value, typed);
    }
    await page.act(async () => page.api().openPanel({ ...panel }));
    assert.equal(dialog(), null);
    assert.equal(field()?.value, typed, "reopening the same record keeps its note draft");

    await page.act(async () => page.api().openPanel({ kind: "inbox" }));
    assert.ok(dialog(), "leaving the record asks before discarding its note");
    await page.act(async () => button(dialog()!, "Seguir editando").click());
    assert.equal(field()?.value, typed);

    await fill(page, noteSelector, stored, HTMLTextAreaElement);
    assert.equal(warnsOnReload(), false, "restoring the saved text clears the warning");
    await fill(page, noteSelector, typed, HTMLTextAreaElement);
    await page.act(async () => page.api().openPanel({ kind: "inbox" }));
    await page.act(async () => button(dialog()!, "Descartar cambios").click());
    await page.wait(() => page.frame().count === 0);
    await page.open(panel, () => field()?.value === stored);
    assert.equal(warnsOnReload(), false);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});

test("a closed original-note dialog keeps its text and warns before leaving the record", async () => {
  const page = await setup("ready", undefined, (fixture) => ({
    workspace: async () => ({ ...await fixture.workspace(), typed_notes_available: true }),
  }));
  const closeDraft = () => [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find((item) => item.textContent === "Cerrar");
  try {
    await page.wait(() => Boolean(page.api().records.workspace?.typed_notes_available));
    await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="receipt-more"]')!.click());
    await page.act(async () => button(page.host, "Agregar nota").click());
    await fill({ ...page, host: document }, '[role="dialog"] textarea', "Texto original de prueba", HTMLTextAreaElement);
    await page.act(async () => closeDraft()!.click());
    assert.equal(warnsOnReload(), true, "retained text still needs the record's unload warning");
    await page.act(async () => page.api().openPanel({ kind: "inbox" }));
    assert.ok(dialog());
    await page.act(async () => button(dialog()!, "Seguir editando").click());
    await page.act(async () => button(page.host, "Volver a abrir la nota conservada").click());
    assert.equal(document.querySelector<HTMLTextAreaElement>('[role="dialog"] textarea')?.value, "Texto original de prueba");
    await fill({ ...page, host: document }, '[role="dialog"] textarea', "", HTMLTextAreaElement);
    await page.act(async () => closeDraft()!.click());
    assert.equal(warnsOnReload(), false);
  } finally { await page.close(); }
});

test("a refused original-note save can still keep or discard the retained text", async () => {
  const page = await setup("ready", undefined, (fixture) => ({
    workspace: async () => ({ ...await fixture.workspace(), typed_notes_available: true }),
    captureNote: async () => { throw Object.assign(new Error("Test access refusal"), { status: 403 }); },
  }));
  const capture = () => document.querySelector('[role="dialog"]')!;
  const typed = "Texto que queda después del rechazo";
  try {
    await page.wait(() => Boolean(page.api().records.workspace?.typed_notes_available));
    await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="receipt-more"]')!.click());
    await page.act(async () => button(page.host, "Agregar nota").click());
    await fill({ ...page, host: document }, '[role="dialog"] textarea', typed, HTMLTextAreaElement);
    await page.act(async () => capture().querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
    await page.wait(() => Boolean(page.host.querySelector('[data-testid="receipt-load-error"]')));
    await page.act(async () => button(capture(), "Cerrar").click());
    await page.act(async () => page.api().openPanel({ kind: "inbox" }));
    assert.ok(dialog(), "the unavailable record can still ask before leaving");
    await page.act(async () => button(dialog()!, "Seguir editando").click());
    await page.act(async () => button(page.host, "Volver a abrir la nota conservada").click());
    assert.equal(capture().querySelector("textarea")?.value, typed);
    await page.act(async () => button(capture(), "Cerrar").click());
    await page.act(async () => page.api().openPanel({ kind: "inbox" }));
    await page.act(async () => button(dialog()!, "Descartar cambios").click());
    await page.wait(() => page.api().panel.kind === "inbox");
    assert.equal(warnsOnReload(), false);
  } finally { await page.close(); }
});

test("an incomplete document date stays through a tab switch and canceled navigation", async () => {
  const page = await setup("ready");
  const selector = '[data-testid="edit-occurred_on"] input';
  try {
    await page.openRow("occurred_on");
    assert.equal(warnsOnReload(), false);
    await fill(page, selector, "07/1");
    assert.equal(warnsOnReload(), true);
    for (const tab of ["detalles", "general"]) {
      await page.act(async () => page.host.querySelector<HTMLButtonElement>(`[data-tab="${tab}"]`)!.click());
      assert.equal(dialog(), null);
    }
    await page.act(async () => page.api().openPanel({ kind: "inbox" }));
    assert.ok(dialog());
    await page.act(async () => button(dialog()!, "Seguir editando").click());
    assert.equal(page.host.querySelector<HTMLInputElement>(selector)?.value, "07/1");
    await page.dismiss("occurred_on");
    assert.equal(warnsOnReload(), false);
  } finally { await page.close(); }
});

test("checking the current record waits for an open row edit", async () => {
  const page = await setup("ready", (dossier) => {
    dossier.approval_result = { status: "failed", code: "retry", reviewed_version: dossier.version };
  });
  const check = () => button(page.host, "Consultar registro actual");
  const selector = '[data-testid="edit-counterparty"] input';
  try {
    assert.equal(check().disabled, false);
    await page.openRow("counterparty");
    await fill(page, selector, "Ferretería de prueba");
    await page.act(async () => check().click());
    assert.equal(page.host.querySelector<HTMLInputElement>(selector)?.value, "Ferretería de prueba", "checking the server must not silently clear the draft");
    assert.equal(check().disabled, true);
    await page.dismiss("counterparty");
    assert.equal(check().disabled, false, "the check is available once the edit is dropped");
  } finally { await page.close(); }
});
