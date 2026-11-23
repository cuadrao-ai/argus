import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ComponentProps, ReactNode } from "react";
import type { BusinessDossier, BusinessDraftRevision, BusinessSupportingFile } from "@/lib/business-dossier";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { TEST_NOW } from "./test-clock";

type DetailsProps = ComponentProps<typeof import("@/components/business-app/dossier/DossierDetails").default>;

async function sample(overrides: Partial<BusinessDossier> = {}) {
  const accounts = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }] as const;
  return { ...await createDossierFixtures([...accounts]).dossier(dossierFixtureIds.ready), ...overrides };
}

function revision(dossier: BusinessDossier, version: number, extra: Partial<BusinessDraftRevision>): BusinessDraftRevision {
  return {
    ...dossier.history[0], before: dossier.facts, after: dossier.facts, source_ids: [],
    version, created_at: TEST_NOW.toISOString(), ...extra,
  };
}

function supporting(sourceId: string, extra: Partial<BusinessSupportingFile> = {}): BusinessSupportingFile {
  return {
    source_id: sourceId, receipt_id: `receipt-${sourceId}`, filename: `${sourceId}.pdf`,
    media_type: "application/pdf", size_bytes: 1024, state: "linked", purge_at: null,
    unlink_available: false, restore_available: false, ...extra,
  };
}

async function mount() {
  GlobalRegistrator.register({ url: "http://localhost" });
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: i18next } = await import("i18next");
  const { I18nextProvider } = await import("react-i18next");
  const { default: spanish } = await import("@/public/locales/es-419/common.json");
  const { default: Details } = await import("@/components/business-app/dossier/DossierDetails");
  const { default: History } = await import("@/components/business-app/ReceiptHistory");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = (node: ReactNode) => act(async () => root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>));
  const field = () => host.querySelector<HTMLTextAreaElement>("textarea[aria-label='Nota']");
  return {
    act, host,
    details: (props: Omit<DetailsProps, "origin">) => render(<Details origin={{}} {...props} />),
    history: (dossier: BusinessDossier, onRestore?: (sourceId: string) => Promise<void>) => render(<History history={dossier.history} sources={dossier.sources} accounts={[]} supportingFiles={dossier.supporting_files} onRestore={onRestore} />),
    button: (label: string, area: ParentNode = host) => [...area.querySelectorAll("button")].find((button) => (button.getAttribute("aria-label") ?? button.textContent?.trim()) === label),
    click: async (node?: HTMLButtonElement) => {
      assert.ok(node, "the action is available");
      await act(async () => node.click());
    },
    field,
    type: async (value: string) => {
      const input = field();
      assert.ok(input, "the note editor is open");
      await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    },
    key: async (key: string, options: KeyboardEventInit = {}) => {
      const input = field();
      assert.ok(input);
      await act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, ...options })));
    },
    close: async () => {
      await act(async () => root.unmount());
      host.remove();
      await GlobalRegistrator.unregister();
    },
  };
}

test("Nota opens the editor from its entry, counts characters, cancels with Escape, and saves server text with Ctrl+Enter", async () => {
  const dossier = await sample({ current_note: "Nota anterior", note_edit_available: true });
  const page = await mount();
  const saved: string[] = [];
  const onSaveNote = async (note: string) => { saved.push(note); };
  try {
    await page.details({ dossier, detailsCard: "note", onSaveNote });
    assert.equal(page.field()?.value, "Nota anterior");
    assert.equal(document.activeElement, page.field());
    await page.type("🧰 nuevo");
    assert.match(page.host.textContent ?? "", /7 \/ 500/);
    await page.key("Escape");
    assert.equal(page.field(), null);
    assert.deepEqual(saved, []);
    await page.click(page.button("Editar nota"));
    assert.equal(page.field()?.value, "Nota anterior");
    await page.type("  Confirmada  ");
    await page.key("Enter", { ctrlKey: true });
    assert.deepEqual(saved, ["  Confirmada  "]);
    assert.equal(page.field(), null);
    assert.match(page.host.textContent ?? "", /Nota anterior/);
    const changed = revision(dossier, 8, { before_current_note: "Nota anterior", after_current_note: "Confirmada", actor: { ...dossier.history[0].actor, shown_as: "name", display_name: "Lía Pérez" } });
    await page.details({ dossier: { ...dossier, current_note: "Confirmada", history: [changed, ...dossier.history] }, detailsCard: "note", onSaveNote });
    assert.match(page.host.textContent ?? "", /Editada hoy · Lía Pérez/);
    assert.match(page.host.textContent ?? "", /Confirmada/);
  } finally { await page.close(); }
});

test("A 500 keeps the note draft available to retry and leaves persisted text unchanged on cancel", async () => {
  const dossier = await sample({ current_note: "Guardada", note_edit_available: true });
  const page = await mount();
  try {
    await page.details({ dossier, onSaveNote: async () => { throw Object.assign(new Error("failed"), { status: 500 }); } });
    await page.click(page.button("Editar nota"));
    const entered = "🧰".repeat(501);
    await page.type(entered);
    assert.equal(page.field()?.value, "🧰".repeat(500));
    await page.click(page.button("Guardar"));
    assert.equal(page.field()?.value, "🧰".repeat(500));
    assert.match(page.host.querySelector('[role="alert"]')?.textContent ?? "", /guardar la nota/i);
    await page.click(page.button("Cancelar"));
    assert.equal(page.field(), null);
    assert.match(page.host.textContent ?? "", /Guardada/);
  } finally { await page.close(); }
});

test("A stale note save shows the new server note alongside the user's draft", async () => {
  const dossier = await sample({ current_note: "Anterior", note_edit_available: true });
  const page = await mount();
  try {
    const onSaveNote = async () => { throw Object.assign(new Error("conflict"), { status: 409, code: "stale_version" }); };
    await page.details({ dossier, detailsCard: "note", onSaveNote });
    await page.type("Mi edición");
    await page.key("Enter", { metaKey: true });
    await page.details({ dossier: { ...dossier, current_note: "Edición de otra persona" }, detailsCard: "note", onSaveNote });
    assert.equal(page.field()?.value, "Mi edición");
    assert.match(page.host.querySelector('[role="alert"]')?.textContent ?? "", /Edición de otra persona/);
    assert.equal(page.button("Guardar")?.disabled, false);
  } finally { await page.close(); }
});

test("Detalles follows server note, add and remove permissions and only lists linked files", async () => {
  const a = supporting("a", { unlink_available: true });
  const b = supporting("b");
  const dossier = await sample({ current_note: null, note_edit_available: false, supporting_files: [a, b, supporting("quitado", { state: "unlinked" })] });
  const page = await mount();
  const changes: string[] = [];
  try {
    await page.details({ dossier, detailsCard: "note", onSaveNote: async () => {}, onAppend: async () => {}, onViewFile: (id) => { changes.push(`view-${id}`); }, onUnlink: async (id) => { changes.push(`unlink-${id}`); } });
    assert.match(page.host.textContent ?? "", /Sin nota\./);
    assert.equal(page.field(), null);
    assert.equal(page.button("Editar nota"), undefined);
    assert.equal(page.button("Agregar archivo"), undefined);
    assert.doesNotMatch(page.host.textContent ?? "", /quitado\.pdf/);
    assert.equal(page.button("Quitar b.pdf"), undefined);
    await page.click(page.button("Ver b.pdf"));
    await page.click(page.button("Quitar a.pdf"));
    assert.deepEqual(changes, ["view-b", "unlink-a"]);
    await page.details({ dossier, onUnlink: async () => {} });
    assert.equal(page.button("Ver b.pdf"), undefined);
  } finally { await page.close(); }
});

test("Agregar archivo passes the selected file and the server's cap hides the chooser", async () => {
  const dossier = await sample({ supporting_append_available: true, supporting_files: [], supporting_file_limit: 3 });
  const page = await mount();
  const files: File[] = [];
  const onAppend = async (file: File) => { files.push(file); };
  try {
    await page.details({ dossier, detailsCard: "support", onAppend });
    const add = page.button("Agregar archivo");
    assert.ok(add);
    assert.equal(document.activeElement, add);
    assert.match(page.host.textContent ?? "", /Sin archivos de respaldo\./);
    const input = page.host.querySelector('input[type="file"]');
    assert.ok(input);
    const file = new File(["synthetic"], "prueba.pdf", { type: "application/pdf" });
    Object.defineProperty(input, "files", { value: [file] });
    await page.act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
    assert.deepEqual(files, [file]);
    await page.details({ dossier: { ...dossier, supporting_limit_reached: true, supporting_append_available: false }, onAppend });
    assert.equal(page.button("Agregar archivo"), undefined);
    assert.equal(page.host.querySelector('input[type="file"]'), null);
    assert.match(page.host.textContent ?? "", /Hasta 3 archivos\. Quita uno para agregar otro\./);
  } finally { await page.close(); }
});

test("Retry after an uncertain append uses the same selected File", async () => {
  const dossier = await sample({ supporting_append_available: true, supporting_files: [] });
  const page = await mount();
  const sent: File[] = [];
  try {
    const onAppend = async (file: File) => {
      sent.push(file);
      if (sent.length === 1) throw Object.assign(new Error("unconfirmed"), { status: 500 });
    };
    await page.details({ dossier, onAppend });
    const input = page.host.querySelector('input[type="file"]');
    assert.ok(input);
    const file = new File(["synthetic"], "respaldo.pdf", { type: "application/pdf" });
    Object.defineProperty(input, "files", { value: [file] });
    await page.act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
    assert.match(page.host.querySelector('[role="alert"]')?.textContent ?? "", /agregar el archivo/i);
    await page.click(page.button("Reintentar"));
    assert.equal(sent.length, 2);
    assert.strictEqual(sent[0], file);
    assert.strictEqual(sent[1], sent[0]);
    assert.equal(page.host.querySelector('[role="alert"]'), null);
  } finally { await page.close(); }
});

test("Historial shows saved note diffs and one restore action for the most recent unlink", async () => {
  const file = supporting("evidencia", { state: "unlinked", purge_at: "2026-11-07T12:00:00Z", restore_available: true });
  const dossier = await sample({ supporting_files: [file] });
  const supportChange = (version: number, supporting_change: BusinessDraftRevision["supporting_change"]) =>
    revision(dossier, version, { supporting_change, supporting_filename: file.filename, source_ids: [file.source_id] });
  const history = [
    supportChange(3, "appended"), supportChange(4, "unlinked"), supportChange(5, "restored"), supportChange(6, "unlinked"),
    revision(dossier, 7, { before_current_note: "Primera", after_current_note: "Segunda" }),
  ];
  const page = await mount();
  const restored: string[] = [];
  try {
    await page.history({ ...dossier, history }, async (id) => { restored.push(id); });
    const note = page.host.querySelector('[data-testid="history-current-note"]');
    assert.equal(note?.querySelector("del")?.textContent, "Primera");
    assert.equal(note?.querySelector("ins")?.textContent, "Segunda");
    const text = page.host.textContent ?? "";
    assert.match(text, /Archivo agregado/);
    assert.match(text, /Archivo restaurado/);
    assert.equal(text.match(/Archivo quitado/g)?.length, 2);
    assert.equal(page.host.querySelectorAll(`time[datetime="${file.purge_at}"]`).length, 1);
    await page.click(page.button("Restaurar"));
    assert.deepEqual(restored, [file.source_id]);
    await page.history({ ...dossier, history, supporting_files: [{ ...file, restore_available: false }] }, async () => {});
    assert.equal(page.button("Restaurar"), undefined);
    assert.match(page.host.querySelector(`time[datetime="${file.purge_at}"]`)?.textContent ?? "", /^Se borra el /);
  } finally { await page.close(); }
});
