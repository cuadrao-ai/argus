import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; });
const record = (kind: RecordRow["kind"], id = "exp-gas", hasProof: boolean | null = false): RecordRow => ({ id, kind, occurredOn: "2026-10-25", counterparty: "Sample", money: { amount: "-9007199254740993.01", currency: "DOP" }, categoryId: null, account: null, hasProof, marks: { personal: false, markedBy: null, fiscal: null }, opens: { kind: "expense", expenseId: id } });

async function mount(width = 1440, readOnly = false) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 844 });
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { RecordsAnnotationsPreview } = await import("@/components/business-app/transacciones/RecordsAnnotationsPreview");
  const { RecordsTable, RecordsNarrowList } = await import("@/components/business-app/transacciones/TransaccionesRecords");
  const { defaultRecordsPreferences } = await import("@/components/business-app/transacciones/records-view-preferences");
  const calls = { opens: 0, network: 0, urls: 0, revoked: [] as string[] };
  const originalFetch = globalThis.fetch;
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  globalThis.fetch = (() => { calls.network++; throw new Error("network_must_not_run"); }) as typeof fetch;
  URL.createObjectURL = () => `blob:fixture-${++calls.urls}`;
  URL.revokeObjectURL = (url) => { calls.revoked.push(url); };
  function Harness() {
    const [scope, setScope] = useState("fixture-space");
    const [filtered, setFiltered] = useState(false);
    const [narrow, setNarrow] = useState(width < 1024);
    const value = { chosen: { space_id: scope, capabilities: readOnly ? ["read"] : ["read", "prepare"] }, records: { workspace: { receipt_limits: { max_bytes: 100, media_types: ["application/pdf", "image/png"] } } }, panel: { kind: "transactions" }, openPanel: () => { calls.opens++; } } as unknown as BusinessContextValue;
    const records = filtered ? [record("venta")] : [record("gasto"), record("venta"), record("gasto", "unknown", null), record("gasto", "original", true)];
    return <BusinessContext.Provider value={value}><RecordsAnnotationsPreview><button onClick={() => setScope(scope === "fixture-space" ? "other" : "fixture-space")}>Business</button><button onClick={() => setFiltered(!filtered)}>Filter</button><button onClick={() => setNarrow(!narrow)}>Viewport</button>{narrow ? <RecordsNarrowList records={records} rowRef={() => {}} /> : <RecordsTable records={records} preferences={defaultRecordsPreferences()} density="normal" rowRef={() => {}} />}</RecordsAnnotationsPreview></BusinessContext.Provider>;
  }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; };
  const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === text)!;
  const click = (node: Element | null | undefined) => act(async () => { assert.ok(node); (node as HTMLElement).click(); });
  const key = (node: Element, key: string) => act(async () => { node.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })); });
  const type = (text: string) => act(async () => { const field = document.querySelector("textarea")!; Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, text); field.dispatchEvent(new Event("input", { bubbles: true })); });
  const note = (kind = "gasto") => host.querySelector(`[data-record-note="${kind}:exp-gas"]`)!;
  const attachment = (kind = "gasto") => host.querySelector(`[data-record-attachment="${kind}:exp-gas"]`)!;
  const choose = (file: File) => act(async () => { const input = document.querySelector<HTMLInputElement>('input[type="file"]')!; Object.defineProperty(input, "files", { value: [file], configurable: true }); input.dispatchEvent(new Event("change", { bubbles: true })); });
  return { act, host, button, click, key, type, note, attachment, choose, calls };
}

test("notes save explicitly, cancel discards, and Business/kind/filter/viewport changes keep the right current note", async () => {
  const page = await mount();
  await page.click(page.note()); await page.type("A current note"); await page.click(page.button("Cancelar"));
  await page.click(page.note()); assert.equal(document.querySelector("textarea")!.value, "");
  await page.type("  Keep this note  "); await page.click(page.button("Guardar"));
  assert.equal(page.note().textContent, "Keep this note"); assert.notEqual(page.note("venta").textContent, "Keep this note");
  await page.click(page.button("Filter")); await page.click(page.button("Filter")); assert.equal(page.note().textContent, "Keep this note");
  await page.click(page.button("Business")); assert.notEqual(page.note().textContent, "Keep this note");
  await page.click(page.button("Business")); assert.equal(page.note().textContent, "Keep this note");
  await page.click(page.button("Viewport")); assert.equal(page.host.querySelector("button button"), null);
  await page.click(page.note());
  assert.equal(document.querySelector("textarea")!.value, "Keep this note");
  await page.type("Discard on close"); await page.key(document.querySelector("textarea")!, "Escape");
  assert.equal(document.querySelector('[role="dialog"]'), null); assert.equal(page.calls.opens, 0); assert.equal(page.calls.network, 0);
});

test("note counter follows the draft and oversized paste saves only the 500-character limit", async () => {
  const page = await mount();
  await page.click(page.note());
  const field = document.querySelector("textarea")!;
  assert.equal(field.maxLength, 500);
  const counter = document.getElementById(field.getAttribute("aria-describedby")!)!;
  assert.equal(counter.textContent, "0/500");
  assert.equal(counter.getAttribute("aria-live"), null);
  await page.type("a".repeat(500) + "overflow");
  assert.equal(field.value, "a".repeat(500));
  assert.equal(counter.textContent, "500/500");
  await page.click(page.button("Guardar"));
  await page.click(page.note());
  assert.equal(document.querySelector("textarea")!.value, "a".repeat(500));
  assert.equal(page.calls.network, 0);
});

test("attachment selection validates files and saves only to the chosen record without uploading", async () => {
  const page = await mount(); await page.click(page.attachment());
  await page.choose(new File(["data"], "bad.exe", { type: "application/octet-stream" }));
  assert.match(document.querySelector('[role="alert"]')!.textContent!, /tipo de archivo/);
  assert.equal(page.button("Guardar").disabled, true);
  await page.choose(new File(["x".repeat(101)], "large.pdf", { type: "application/pdf" }));
  assert.match(document.querySelector('[role="alert"]')!.textContent!, /tamaño/);
  await page.choose(new File(["data"], "record.pdf", { type: "application/pdf" }));
  assert.equal(document.querySelector('[role="alert"]'), null); assert.equal(page.button("Guardar").disabled, false);
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /record.pdf/);
  await page.click(page.button("Guardar")); assert.deepEqual(page.calls.revoked, ["blob:fixture-1"]);
  await page.click(page.attachment("venta")); assert.doesNotMatch(document.querySelector('[role="dialog"]')!.textContent!, /record.pdf/);
  await page.click(page.button("Cancelar")); await page.click(page.attachment());
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /record.pdf/);
  await page.choose(new File(["new"], "discard.pdf", { type: "application/pdf" })); await page.click(page.button("Cancelar"));
  await page.click(page.attachment()); assert.match(document.querySelector('[role="dialog"]')!.textContent!, /record.pdf/); assert.doesNotMatch(document.querySelector('[role="dialog"]')!.textContent!, /discard.pdf/);
  assert.equal(page.calls.opens, 0); assert.equal(page.calls.network, 0);
});

test("note and attachment keyboard actions do not open the dossier, dates/money/status have distinct cells", async () => {
  const page = await mount();
  await page.key(page.note(), "Enter"); assert.equal(page.calls.opens, 0);
  await page.key(page.attachment(), "Enter"); assert.equal(page.calls.opens, 0);
  await page.click(page.note()); await page.type("Keep"); await page.click(page.button("Guardar"));
  const row = page.host.querySelector('[data-record-key="gasto:exp-gas"]')!;
  assert.equal(row.querySelector('[data-col="fecha"]')!.textContent, "25 oct 2026");
  assert.equal(row.querySelector('[data-col="monto"]')!.textContent, "9,007,199,254,740,993.01");
  assert.ok(row.querySelector('[data-col="monto"] .cuadrao-amount'));
  assert.equal(row.querySelector('[data-col="moneda"]')!.textContent, "RD$");
  assert.equal(row.querySelector('[data-record-workflow]')!.textContent, "Por revisar");
  assert.equal(page.host.querySelector('[data-record-key="gasto:unknown"] [data-record-attachment]'), null);
  await page.click(page.host.querySelector('[data-record-attachment="gasto:original"]'));
  assert.equal(document.querySelector('[role="dialog"]'), null); assert.equal(page.calls.opens, 1);
  await page.key(row, "Enter"); assert.equal(page.calls.opens, 2);
});

test("read-only rows offer no note editor or add-attachment control", async () => {
  const page = await mount(1440, true);
  assert.equal(page.host.querySelector('[data-record-note]'), null);
  assert.equal(page.host.querySelector('[data-record-attachment="gasto:exp-gas"]'), null);
  assert.equal(page.calls.network, 0);
});

test("phone record actions open the shared sheet and keep targets separate from record opening", async () => {
  const page = await mount(390);
  await page.click(page.note());
  assert.ok(document.querySelector('[role="dialog"]'));
  assert.notEqual(document.activeElement?.tagName, "TEXTAREA");
  await page.type("Phone note"); await page.click(page.button("Guardar"));
  await page.click(page.note());
  assert.equal(document.querySelector("textarea")!.value, "Phone note");
  await page.click(page.button("Cancelar")); assert.equal(page.calls.opens, 0); assert.equal(page.host.querySelector("button button"), null);
});

test("attachment names accept ordinary PDF/PNG files and reject path separators and control characters", async () => {
  const page = await mount(); await page.click(page.attachment());
  for (const name of ["bad/name.pdf", "bad\\name.pdf", "bad\u0000name.pdf", "bad\u001fname.pdf"]) {
    await page.choose(new File(["data"], name, { type: "application/pdf" }));
    assert.match(document.querySelector('[role="alert"]')!.textContent!, /nombre de archivo/);
    assert.equal(page.button("Guardar").disabled, true);
  }
  for (const [name, type] of [["record.pdf", "application/pdf"], ["receipt.pdf", "application/pdf"], ["receipt.png", "image/png"]]) {
    await page.choose(new File(["data"], name, { type }));
    assert.equal(document.querySelector('[role="alert"]'), null, name);
    assert.equal(page.button("Guardar").disabled, false, name);
    assert.ok(document.querySelector('[role="dialog"]')!.textContent!.includes(name));
  }
  await page.click(page.button("Guardar"));
  assert.equal(page.calls.opens, 0); assert.equal(page.calls.network, 0);
});
