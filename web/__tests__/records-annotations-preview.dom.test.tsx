import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";

const previewEnv = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
beforeAll(() => {
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); for (const [key, value] of Object.entries(previewEnv)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } });
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
  const { RecordsAnnotationsPreview, useRecordPreviewSearch } = await import("@/components/business-app/transacciones/RecordsAnnotationsPreview");
  const { RecordsTable, RecordsNarrowList } = await import("@/components/business-app/transacciones/TransaccionesRecords");
  const { defaultRecordsPreferences } = await import("@/components/business-app/transacciones/records-view-preferences");
  const calls = { opens: 0, network: 0, urls: 0, revoked: [] as string[] };
  const originalFetch = globalThis.fetch;
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  globalThis.fetch = (() => { calls.network++; throw new Error("network_must_not_run"); }) as typeof fetch;
  URL.createObjectURL = () => `blob:fixture-${++calls.urls}`;
  URL.revokeObjectURL = (url) => { calls.revoked.push(url); };
  function SearchProbe() {
    const matches = useRecordPreviewSearch();
    return <output data-testid="note-search">{String(matches(record("gasto"), "Keep this note"))}</output>;
  }
  function Harness() {
    const [scope, setScope] = useState("fixture-space");
    const [prepare, setPrepare] = useState(!readOnly);
    const [read, setRead] = useState(true);
    const [filtered, setFiltered] = useState(false);
    const [narrow, setNarrow] = useState(width < 1024);
    const value = { chosen: { space_id: scope, capabilities: read ? prepare ? ["read", "prepare"] : ["read"] : [] }, records: { workspace: { receipt_limits: { max_bytes: 100, media_types: ["application/pdf", "image/png"] } } }, panel: { kind: "transactions" }, openPanel: () => { calls.opens++; } } as unknown as BusinessContextValue;
    const records = filtered ? [record("venta")] : [record("gasto"), record("venta"), record("gasto", "unknown", null), record("gasto", "original", true), { ...record("gasto", "unavailable", true), opens: null }];
    return <BusinessContext.Provider value={value}><RecordsAnnotationsPreview><SearchProbe /><button onClick={() => setScope(scope === "fixture-space" ? "other" : "fixture-space")}>Business</button><button onClick={() => setPrepare(!prepare)}>Permission</button><button onClick={() => setRead(!read)}>Read</button><button onClick={() => setFiltered(!filtered)}>Filter</button><button onClick={() => setNarrow(!narrow)}>Viewport</button>{narrow ? <RecordsNarrowList records={records} rowRef={() => {}} /> : <RecordsTable records={records} preferences={defaultRecordsPreferences()} density="normal" rowRef={() => {}} />}</RecordsAnnotationsPreview></BusinessContext.Provider>;
  }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; };
  const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === text)!;
  const click = (node: Element | null | undefined) => act(async () => { assert.ok(node); (node as HTMLElement).click(); });
  const key = (node: Element, key: string) => act(async () => { node.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })); });
  const attachment = (kind = "gasto") => host.querySelector(`[data-record-attachment="${kind}:exp-gas"]`)!;
  const choose = async (...files: File[]) => {
    await act(async () => { const input = document.querySelector<HTMLInputElement>('input[type="file"]')!; Object.defineProperty(input, "files", { value: files, configurable: true }); input.dispatchEvent(new Event("change", { bubbles: true })); });
    for (let attempt = 0; attempt < 30 && document.querySelector<HTMLInputElement>('input[type="file"]')?.disabled; attempt++) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)); });
    assert.equal(document.querySelector<HTMLInputElement>('input[type="file"]')?.disabled, false);
  };
  return { act, host, button, click, key, attachment, choose, calls };
}

test("the records table keeps the note column and does not offer a note editor", async () => {
  const page = await mount();
  const notes = page.host.querySelector('[data-record-key="gasto:exp-gas"] [data-col="notas"]')!;
  assert.ok(notes);
  assert.equal(notes.querySelector("button"), null);
  assert.equal(page.host.querySelector("[data-record-note]"), null);
  assert.equal(document.querySelector("textarea"), null);
  assert.ok(page.attachment());
  assert.equal(page.calls.network, 0);
});

test("local files add without replacing, preserve existing evidence, isolate records and discard cancelled additions", async () => {
  const page = await mount(); await page.click(page.attachment());
  assert.equal(document.querySelector<HTMLInputElement>('input[type="file"]')!.multiple, true);
  assert.equal(page.button("Guardar"), undefined, "files do not offer a durable Save action");
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /no se han subido ni vinculado/i);
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /documentos recibidos aún no está disponible/);
  assert.equal(page.button("Cancelar"), undefined);
  assert.equal(page.button("Conservar").disabled, true);
  await page.choose(new File(["first"], "record.pdf", { type: "application/pdf" }), new File(["second"], "other.pdf", { type: "application/pdf" }));
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 2);
  await page.choose(new File(["first"], "renamed.pdf", { type: "application/pdf" }));
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 2);
  assert.match(document.querySelector('[role="status"]')!.textContent!, /ya está/);
  await page.click(page.button("Conservar"));
  assert.equal(page.attachment().getAttribute("data-local-attachment-count"), "2");
  assert.equal(page.calls.revoked.length, 2);
  await page.click(page.attachment("venta")); assert.equal(document.querySelectorAll('[data-local-files] > li').length, 0);
  await page.click(document.querySelector('[role="dialog"] button[aria-label="Cerrar"]')); await page.click(page.attachment());
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 2);
  await page.choose(new File(["third"], "discard.pdf", { type: "application/pdf" }));
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 3);
  await page.click(document.querySelector('[role="dialog"] button[aria-label="Cerrar"]')); await page.click(page.attachment());
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 2);
  assert.doesNotMatch(document.querySelector('[data-local-files]')!.textContent!, /discard.pdf/);
  await page.click(document.querySelector('[role="dialog"] button[aria-label="Cerrar"]')); await page.click(page.button("Business")); await page.click(page.attachment());
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 0);
  await page.click(document.querySelector('[role="dialog"] button[aria-label="Cerrar"]')); await page.click(page.button("Business"));
  await page.click(page.host.querySelector('[data-record-attachment="gasto:original"]'));
  assert.ok(page.button("Abrir adjunto vinculado"));
  await page.choose(new File(["local"], "support.pdf", { type: "application/pdf" }));
  await page.click(page.button("Conservar"));
  await page.click(page.host.querySelector('[data-record-attachment="gasto:original"]'));
  assert.ok(page.button("Abrir adjunto vinculado"));
  assert.match(document.querySelector('[data-local-files]')!.textContent!, /support.pdf/);
  await page.click(page.button("Abrir adjunto vinculado"));
  assert.equal(page.calls.opens, 1); assert.equal(page.calls.network, 0);
});

test("attachment keyboard actions do not open the dossier, and the note column has no editor", async () => {
  const page = await mount();
  assert.equal(page.host.querySelector("[data-record-note]"), null);
  assert.equal(document.querySelector("textarea"), null);
  await page.key(page.attachment(), "Enter"); assert.equal(page.calls.opens, 0);
  const row = page.host.querySelector('[data-record-key="gasto:exp-gas"]')!;
  assert.equal(row.querySelector('[data-col="fecha"]')!.textContent, "25 oct 2026");
  assert.equal(row.querySelector('[data-col="monto"]')!.textContent, "9,007,199,254,740,993.01");
  assert.ok(row.querySelector('[data-col="monto"] .cuadrao-amount'));
  assert.equal(row.querySelector('[data-col="moneda"]')!.textContent, "RD$");
  assert.equal(row.querySelector('[data-record-workflow]')!.textContent, "Por revisar");
  assert.equal(page.host.querySelector('[data-record-key="gasto:unknown"] [data-record-attachment]'), null);
  await page.click(page.host.querySelector('[data-record-attachment="gasto:original"]'));
  await page.click(page.button("Abrir adjunto vinculado"));
  assert.equal(document.querySelector('[role="dialog"]'), null); assert.equal(page.calls.opens, 1);
  await page.key(row, "Enter"); assert.equal(page.calls.opens, 2);
});

test("read-only rows offer no note editor or add-attachment control", async () => {
  const page = await mount(1440, true);
  assert.equal(page.host.querySelector('[data-record-note]'), null);
  assert.equal(page.host.querySelector('[data-record-attachment="gasto:exp-gas"]'), null);
  assert.equal(page.calls.network, 0);
});

test("phone rows keep the attachment control and do not offer a note entry", async () => {
  const page = await mount(390);
  assert.equal(page.host.querySelector("[data-record-note]"), null);
  assert.equal(document.querySelector("textarea"), null);
  assert.ok(page.attachment());
  await page.click(page.attachment());
  assert.ok(document.querySelector('[role="dialog"]'));
  assert.equal(document.querySelector("textarea"), null);
  assert.equal(page.calls.opens, 0);
  assert.equal(page.host.querySelector("button button"), null);
});

test("attachment names accept ordinary PDF/PNG files and reject path separators and control characters", async () => {
  const page = await mount(); await page.click(page.attachment());
  for (const name of ["bad/name.pdf", "bad\\name.pdf", "bad\u0000name.pdf", "bad\u001fname.pdf"]) {
    await page.choose(new File(["data"], name, { type: "application/pdf" }));
    assert.match(document.querySelector('[role="alert"]')!.textContent!, /nombre de archivo/);
    assert.equal(page.button("Conservar").disabled, true);
  }
  for (const [name, type] of [["record.pdf", "application/pdf"], ["receipt.pdf", "application/pdf"], ["receipt.png", "image/png"]]) {
    await page.choose(new File([name], name, { type }));
    assert.equal(document.querySelector('[role="alert"]'), null, name);
    assert.equal(page.button("Conservar").disabled, false, name);
    assert.ok(document.querySelector('[role="dialog"]')!.textContent!.includes(name));
  }
  await page.click(page.button("Conservar"));
  assert.equal(page.calls.opens, 0); assert.equal(page.calls.network, 0);
});


test("linked but unavailable evidence stays distinct from an empty record and reader permissions protect local files", async () => {
  const page = await mount();
  await page.click(page.host.querySelector('[data-record-attachment="gasto:unavailable"]'));
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /tiene un adjunto vinculado, pero no se puede abrir/);
  assert.doesNotMatch(document.querySelector('[role="dialog"]')!.textContent!, /Sin adjuntos vinculados/);
  assert.equal(page.button("Abrir adjunto vinculado"), undefined);
  await page.click(document.querySelector('[role="dialog"] button[aria-label="Cerrar"]')); await page.click(page.attachment());
  await page.choose(new File(["reader"], "reader.pdf", { type: "application/pdf" }));
  await page.click(page.button("Conservar")); await page.click(page.button("Permission"));
  await page.click(page.attachment());
  assert.match(document.querySelector('[data-local-files]')!.textContent!, /reader.pdf/);
  assert.equal(document.querySelector('input[type="file"]'), null);
  assert.equal(page.button("Conservar"), undefined);
  assert.equal(page.calls.network, 0);
});

test("non-preview mode retains direct durable evidence reads and exposes no local-file editor", async () => {
  const previous = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  try {
    const page = await mount();
    assert.equal(page.attachment(), null);
    await page.click(page.host.querySelector('[data-record-attachment="gasto:original"]'));
    assert.equal(page.calls.opens, 1);
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(page.calls.network, 0);
  } finally { process.env.NEXT_PUBLIC_MOCK_AUTH = previous; }
});


test("phone attachment sheet starts full and keeps several selected files locally", async () => {
  const page = await mount(390);
  await page.click(page.attachment());
  assert.equal(document.querySelector('[role="dialog"]')?.getAttribute("data-snap"), "full");
  await page.choose(new File(["phone first"], "first.pdf", { type: "application/pdf" }), new File(["phone second"], "second.pdf", { type: "application/pdf" }));
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 2);
  await page.click(page.button("Conservar"));
  await page.click(page.attachment());
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 2);
  assert.equal(page.calls.opens, 0); assert.equal(page.calls.network, 0);
});

test("unknown attachment presence is not treated as missing and revoked read hides local evidence", async () => {
  const page = await mount();
  const unknown = page.host.querySelector('[data-record-key="gasto:unknown"] [data-col="comprobante"]')!;
  assert.ok(unknown);
  assert.equal(unknown.querySelector("button"), null);
  assert.doesNotMatch(unknown.textContent!, /Sin adjuntos vinculados/);
  await page.click(page.attachment());
  await page.choose(new File(["private"], "private.pdf", { type: "application/pdf" }));
  await page.click(page.button("Conservar"));
  await page.click(page.attachment());
  assert.match(document.querySelector('[data-local-files]')!.textContent!, /private.pdf/);
  await page.click(page.button("Read"));
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(page.host.querySelector('[data-record-attachment]'), null);
  assert.equal(page.host.querySelector('[data-record-note]'), null);
  assert.equal(page.calls.network, 0);
});


test("attachment drop and paste append local evidence without network writes", async () => {
  const page = await mount(); await page.click(page.attachment());
  const transfer = async (kind: "drop" | "paste", file: File) => {
    const event = new Event(kind, { bubbles: true, cancelable: true });
    Object.defineProperty(event, kind === "drop" ? "dataTransfer" : "clipboardData", { value: { files: [file] } });
    await page.act(async () => { document.querySelector(kind === "drop" ? '[data-testid="records-evidence-drop-zone"]' : '[role="dialog"] button')!.dispatchEvent(event); });
    for (let attempt = 0; attempt < 30 && document.querySelector<HTMLInputElement>('input[type="file"]')?.disabled; attempt++) await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)); });
    assert.equal(event.defaultPrevented, true);
  };
  await transfer("drop", new File(["drop"], "dropped.pdf", { type: "application/pdf" }));
  await transfer("paste", new File(["paste"], "pasted.pdf", { type: "application/pdf" }));
  assert.equal(document.querySelectorAll('[data-local-files] > li').length, 2);
  assert.ok(page.button("Conservar").className.includes("w-full"));
  assert.equal(page.calls.network, 0);
});
