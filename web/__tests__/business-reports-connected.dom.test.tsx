import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, StrictMode } from "react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { ConnectedBusinessReports, reportFiltersForUi, reportFiltersFromUi } from "@/components/business-app/transacciones/BusinessReportsPanel";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { emptyPreviewFilters, validPreviewAmount } from "@/components/business-app/transacciones/records-filter-preview-model";
import { reportRequestSchema, type ReportRequest } from "@/lib/business-reports-api";
import { setChosenGrant } from "@/lib/business-grant";
import { createBusinessReportHttpFixture, fixtureId } from "./fixtures/business-report-http-fixture";
import spanish from "@/public/locales/es-419/common.json";

let cleanup = async () => {};
const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; window.history.replaceState(null, "", "/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });
async function mount(options: { readOnly?: boolean; large?: boolean; legacy?: boolean; initial?: ReportRequest; width?: number } = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width: options.width ?? 1440, height: 900 });
  const { createRoot } = await import("react-dom/client");
  const fixture = createBusinessReportHttpFixture(); if (options.large) { fixture.records[0].gross_amount = "9007199254740993.01"; fixture.records[0].recorded_amount = "9007199254740993.01"; fixture.records[3].document_kind = "credit_note"; fixture.records[3].gross_amount = "20.00"; fixture.records[3].adjustment_effect = "known"; fixture.records[4].gross_amount = "-20.00"; fixture.records[4].document_kind = "credit_note"; fixture.records[4].adjustment_effect = "known"; } fixture.controls.readOnly = options.readOnly ?? false; fixture.controls.legacy = options.legacy ?? false;
  const computedStyle = globalThis.getComputedStyle;
  if (options.width && options.width < 1024) globalThis.getComputedStyle = ((element: Element) => {
    const style = computedStyle(element);
    return new Proxy(style, { get(target, key) { if (key === 'getPropertyValue') return (name: string) => name === '--records-narrow' ? '1' : target.getPropertyValue(name); const value = Reflect.get(target, key); return typeof value === 'function' ? value.bind(target) : value; } });
  }) as typeof getComputedStyle;
  const originalFetch = globalThis.fetch; globalThis.fetch = fixture.request as typeof fetch;
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
  const downloads: Blob[] = []; URL.createObjectURL = (blob) => { downloads.push(blob as Blob); return "blob:synthetic"; }; URL.revokeObjectURL = () => undefined;
  setChosenGrant(null);
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const context = { chosen: { space_id: fixtureId(3000), grant_id: fixtureId(3001), role: "owner", name: "Colmado sintético", capabilities: options.readOnly ? ["read"] : ["read", "prepare", "approve"], permissions: options.readOnly ? ["read"] : ["read", "prepare", "approve", "download", "export"] }, source, revision: 0, actions: { create: [] }, panel: { kind: "transactions" }, openPanel: () => undefined, records: { workspace: await source.workspace(), inbox: [] } } as unknown as BusinessContextValue;
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.appendChild(host); const root = createRoot(host);
  await act(async () => root.render(<StrictMode><I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><ConnectedBusinessReports initial={options.initial} scope={{ userId: "synthetic-person", businessId: fixtureId(3000), grantId: null }} period={{ key: "all", from: "", to: null }} /></BusinessContext.Provider></I18nextProvider></StrictMode>));
  cleanup = async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; globalThis.getComputedStyle = computedStyle; URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; };
  const settle = async (predicate: () => boolean) => { for (let i = 0; i < 80; i++) { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); }); if (predicate()) return; } throw new Error(`Missing state ${document.body.textContent?.slice(-600)}`); };
  const click = async (element: Element | undefined | null) => { assert.ok(element); await act(async () => (element as HTMLElement).click()); };
  const button = (label: string) => [...document.querySelectorAll("button")].find((button) => button.textContent?.trim() === label || button.getAttribute("aria-label") === label);
  const type = async (element: HTMLInputElement | HTMLTextAreaElement, value: string) => { await act(async () => { const prototype = element instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(element, value); element.dispatchEvent(new Event("input", { bubbles: true })); }); };
  await settle(() => document.querySelector(`[data-report-schema="${options.legacy ? 1 : 2}"] [data-testid="records-count"]`) !== null);
  return { fixture, settle, click, button, type, downloads };
}

test("connected pages, full count, accent search and period-only overview use real transport", async () => {
  const page = await mount();
  assert.match(document.querySelector('[data-testid="records-count"]')!.textContent!, /126/);
  assert.equal(document.querySelectorAll("tbody tr").length, 25);
  assert.ok(page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).every((call) => (call.body as { filters: { period: unknown } }).filters.period && !(call.body as Record<string, unknown>).business_id));
  await page.click(document.querySelector('button[aria-label="Última página"]'));
  await page.settle(() => document.querySelector('[data-testid="records-pagination"]')?.getAttribute("data-page") === "6");
  assert.equal(document.querySelectorAll("tbody tr").length, 1);
  await page.type(document.querySelector('input[type="search"]')!, "pena");
  await page.settle(() => document.querySelector('[data-testid="records-count"]')?.textContent?.includes("1 de 1") ?? false);
  assert.match(document.querySelector('[data-testid="transacciones-records"]')!.textContent!, /José Peña/);
  assert.match(document.querySelector('[data-overview-filter="review"]')!.textContent!, /60/);
  assert.ok(page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).some((call) => (call.body as { filters: { q: string }; page: number }).filters.q === "pena" && (call.body as { page: number }).page === 1));
});

test("current notes preserve 500 code points and replay uncertain writes with one effect", async () => {
  const page = await mount(); page.fixture.controls.noteUncertain = true;
  await page.click(document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`));
  const field = document.querySelector("textarea")!;
  const valid = "🟢".repeat(500);
  await page.type(field, valid + "x");
  assert.equal(field.value, valid + "x"); assert.equal((page.button("Guardar") as HTMLButtonElement).disabled, true);
  await page.type(field, valid); assert.match(document.querySelector('[role="dialog"]')!.textContent!, /500\/500/);
  await page.click(page.button("Guardar"));
  await page.settle(() => document.querySelector('[role="alert"]')?.textContent?.includes("confirmar") ?? false);
  await page.click(page.button("Reintentar"));
  await page.settle(() => !document.querySelector("textarea"));
  const writes = page.fixture.calls.filter((call) => call.path.endsWith("/current-note"));
  assert.equal(writes.length, 2); assert.equal(writes[0].headers.get("Idempotency-Key"), writes[1].headers.get("Idempotency-Key"));
  assert.deepEqual(writes[0].body, writes[1].body); assert.equal(page.fixture.records[0].revision, 4); assert.equal(page.fixture.records[0].note, valid);
});

test("supporting files freeze the uncertain file before advancing and download by returned receipt identity", async () => {
  const page = await mount(); page.fixture.controls.fileUncertainAt = 1;
  await page.click(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  const files = [new File(["first new bytes"], "primero.pdf", { type: "application/pdf" }), new File(["second new bytes"], "segundo.pdf", { type: "application/pdf" })];
  await act(async () => { Object.defineProperty(input, "files", { configurable: true, value: files }); input.dispatchEvent(new Event("change", { bubbles: true })); });
  await page.settle(() => document.querySelectorAll("[data-local-files] li").length === 2);
  await page.click(page.button("Guardar"));
  await page.settle(() => document.querySelector('[role="alert"]')?.textContent?.includes("confirmar") ?? false);
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/supporting-files")).length, 1);
  await page.click(page.button("Reintentar"));
  await page.settle(() => !document.querySelector('[role="dialog"]'));
  const writes = page.fixture.calls.filter((call) => call.path.endsWith("/supporting-files"));
  assert.equal(writes.length, 3); assert.equal(writes[0].headers.get("Idempotency-Key"), writes[1].headers.get("Idempotency-Key"));
  assert.equal(writes[0].headers.get("X-Draft-Version"), "3"); assert.equal(writes[1].headers.get("X-Draft-Version"), "3"); assert.equal(writes[2].headers.get("X-Draft-Version"), "4");
  assert.equal(page.fixture.records[0].attachment_sources!.length, 3); assert.equal(page.fixture.records[0].gross_amount, "100.00");
  await page.click(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  await page.click(page.button("primero.pdf"));
  await page.settle(() => page.downloads.length > 0);
  const read = page.fixture.calls.find((call) => call.path.endsWith(`/receipts/${fixtureId(8001)}/source`));
  assert.ok(read); assert.equal(await page.downloads[0].text(), "first new bytes");
  assert.notEqual(page.fixture.records[0].attachment_sources![1].source_id, fixtureId(8001));
});

test("saved canonical filters preserve multiple currencies and both known families until explicit changes", () => {
  const filters = reportRequestSchema.parse({ filters: { currencies: ["CAD", "USD"], record_families: ["sale", "purchase"] } }).filters;
  const draft = reportFiltersForUi(filters);
  assert.deepEqual(reportFiltersFromUi(filters, { ...draft, category: ["transport"] }, "all").record_families, ["sale", "purchase"]);
  assert.deepEqual(reportFiltersFromUi(filters, draft, "all").currencies, ["CAD", "USD"]);
  assert.deepEqual(reportFiltersFromUi(filters, { ...draft, recordFamilies: undefined }, "gasto").record_families, ["purchase"]);
  assert.equal(validPreviewAmount({ currency: "", min: "1", max: "" }, ["CAD", "USD"]), false);
  assert.equal(validPreviewAmount({ currency: "", min: "", max: "" }, ["CAD", "USD"]), true);
  assert.deepEqual(emptyPreviewFilters().amount, { currency: "", min: "", max: "" });
});

test("a concurrent note edit keeps the losing text and uses the reviewed version only after explicit reload", async () => {
  const page = await mount();
  await page.click(document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`));
  await page.type(document.querySelector("textarea")!, "Mi borrador");
  page.fixture.records[0].revision = 5; page.fixture.records[0].note = "Nota de otra persona";
  await page.click(page.button("Guardar"));
  await page.settle(() => document.querySelector('[role="alert"]')?.textContent?.includes("registro cambió") ?? false);
  assert.equal(document.querySelector("textarea")!.value, "Mi borrador");
  await page.click(page.button("Recargar"));
  await page.settle(() => document.querySelector('[role="dialog"]')?.textContent?.includes("Nota de otra persona") ?? false);
  assert.equal(document.querySelector("textarea")!.value, "Mi borrador");
  await page.click(page.button("Guardar")); await page.settle(() => !document.querySelector("textarea"));
  const writes = page.fixture.calls.filter((call) => call.path.endsWith("/current-note"));
  assert.equal((writes[0].body as { expected_version: number }).expected_version, 3);
  assert.equal((writes[1].body as { expected_version: number }).expected_version, 5);
  assert.notEqual(writes[0].headers.get("Idempotency-Key"), writes[1].headers.get("Idempotency-Key"));
});

test("saved views persist only recipes, rename with versions, restore page one and delete", async () => {
  const page = await mount();
  await page.click(document.querySelector('button[aria-label="Última página"]'));
  await page.settle(() => document.querySelector('[data-testid="records-pagination"]')?.getAttribute("data-page") === "6");
  await page.click(page.button("Vistas")); await page.click(page.button("Guardar vista"));
  await page.type(document.querySelector('input[maxlength="120"]')!, "Mi vista"); await page.click(page.button("Guardar"));
  await page.settle(() => page.fixture.views.length === 1 && !document.querySelector('input[maxlength="120"]'));
  const saved = page.fixture.views[0].recipe as Record<string, unknown>;
  assert.equal(saved.schema_version, 2); assert.ok(saved.presentation); assert.equal(saved.page_size, 25); assert.equal(saved.page, undefined); assert.equal(saved.totals, undefined);
  await page.type(document.querySelector('input[type="search"]')!, "pena");
  await page.settle(() => document.querySelectorAll("tbody tr").length === 1);
  await page.click(page.button("Vistas")); await page.click(page.button("Mi vista"));
  await page.settle(() => document.querySelector('[data-testid="records-pagination"]')?.getAttribute("data-page") === "1" && document.querySelectorAll("tbody tr").length === 25);
  assert.equal(document.querySelector<HTMLInputElement>('input[type="search"]')!.value, "");
  await page.click(page.button("Vistas")); await page.click(page.button(spanish.common.rename));
  await page.type(document.querySelector('input[maxlength="120"]')!, "Mi vista nueva"); await page.click(page.button("Guardar"));
  await page.settle(() => page.fixture.views[0].version === 2);
  const update = page.fixture.calls.find((call) => call.method === "PATCH" && call.path.includes("report-views"));
  assert.equal((update!.body as { expected_version: number }).expected_version, 1);
  await page.click(page.button("Vistas")); await page.click(page.button(spanish.common.delete));
  await page.settle(() => page.fixture.views.length === 0);
});

test("the existing export menu holds 409 for explicit refresh and never exports an unseen changed set", async () => {
  const page = await mount(); page.fixture.controls.exportChanged = true;
  await page.click(document.querySelector('[data-testid="add-menu-more"]'));
  await page.click(page.button(spanish.business.overview.export_records));
  await page.settle(() => document.querySelector('[role="alert"]')?.textContent?.includes("registros cambiaron") ?? false);
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/reports/export")).length, 1);
  assert.equal(page.downloads.length, 0);
  assert.match(document.body.textContent!, /No incluye archivos originales/);
  const before = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  await page.click(page.button("Actualizar"));
  await page.settle(() => page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length > before && document.querySelector('[data-testid="records-count"]') !== null);
  page.fixture.controls.exportChanged = false;
  await page.click(document.querySelector('[data-testid="add-menu-more"]')); await page.click(page.button(spanish.business.overview.export_records));
  await page.settle(() => page.downloads.length === 1);
  const exports = page.fixture.calls.filter((call) => call.path.endsWith("/reports/export"));
  assert.equal(exports.length, 2); assert.equal((exports[0].body as { expected_fingerprint: string }).expected_fingerprint, "a".repeat(64));
});

test("a member with export and no Agregar keeps the menu trigger and its focus while an export runs", async () => {
  const page = await mount();
  const live = globalThis.fetch;
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/reports/export")) await held;
    return live(input, init);
  }) as typeof fetch;
  const trigger = () => document.querySelector<HTMLButtonElement>('[data-testid="add-menu-more"]');
  assert.equal(document.querySelector('[data-testid="business-primary-upload"]'), null);
  await page.click(trigger());
  await page.click(page.button(spanish.business.overview.export_records));
  assert.ok(trigger(), "the trigger stays while the export runs");
  assert.equal(document.activeElement, trigger(), "focus returns to the trigger and stays");
  release();
  await page.settle(() => page.downloads.length === 1);
  assert.ok(trigger(), "the trigger is still there after the download");
});

test("viewer metadata never grants append or source bytes, and unavailable originals stay linked", async () => {
  const page = await mount({ readOnly: true });
  await page.click(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  assert.equal((page.button("Original sintético.pdf") as HTMLButtonElement).disabled, true);
  assert.equal(document.querySelector('input[type="file"]'), null);
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/source")).length, 0);
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /Original sintético/);
});


test("authoritative decimal text above the safe integer limit renders exactly beside mixed and unknown money", async () => {
  await mount({ large: true });
  const rows = [...document.querySelectorAll("tbody tr")];
  assert.equal(rows[0].querySelector('[data-col="monto"]')!.textContent, "9,007,199,254,740,993.01");
  assert.equal(rows[0].querySelector('[data-col="moneda"]')!.textContent, "RD$");
  assert.equal(rows[1].querySelector('[data-col="moneda"]')!.textContent, "US$");
  assert.match(rows[2].querySelector('[data-col="monto"]')!.textContent!, /-/);
  assert.equal(rows[3].querySelector('[data-col="monto"]')!.textContent, "20.00");
  assert.equal(rows[4].querySelector('[data-col="monto"]')!.textContent, "-20.00");
});

test("an unavailable original keeps its filename and linked evidence distinct from a missing attachment", async () => {
  const page = await mount();
  page.fixture.storage.delete(fixtureId(700));
  await page.click(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  await page.click(page.button("Original sintético.pdf"));
  await page.settle(() => document.querySelector('[role="alert"]') !== null);
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /Original sintético.pdf/);
  assert.equal(page.downloads.length, 0);
  assert.equal(page.fixture.records[0].has_document, true);
  assert.equal(page.fixture.records[0].attachment_sources![0].receipt_id, fixtureId(700));
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith(`/receipts/${fixtureId(500)}/source`)).length, 0);
});

test("older v1 servers keep query usable and leave unsupported overview unavailable", async () => {
  const page = await mount({ legacy: true });
  assert.equal(document.querySelector('[data-report-schema]')?.getAttribute('data-report-schema'), '1');
  assert.equal(document.querySelectorAll('tbody tr').length, 25);
  for (const card of document.querySelectorAll<HTMLButtonElement>('[data-overview-filter]')) assert.equal(card.disabled, true);
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).every((call) => (call.body as ReportRequest).schema_version === 1), true);
  assert.equal(document.querySelector('[data-testid="records-results-summary"]'), null);
});

test("automatic sales cards stay unknown even if every matching row has a binary paid status", async () => {
  await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['sale'] } }) });
  const summary = document.querySelector('[data-testid="records-results-summary"]')!;
  assert.equal(summary.getAttribute('data-summary-kind'), 'venta');
  assert.equal(summary.querySelectorAll('[data-summary-part]').length, 3);
  assert.equal(summary.querySelectorAll('.cuadrao-amount').length, 0);
  assert.equal(document.body.textContent?.includes('Monto no disponible.'), true);
});

test("view conflicts keep the unsaved name and require current version readback before another save", async () => {
  const page = await mount();
  await page.click(page.button('Vistas')); await page.click(page.button('Guardar vista'));
  await page.type(document.querySelector('input[maxlength="120"]')!, 'Vista inicial'); await page.click(page.button('Guardar'));
  await page.settle(() => page.fixture.views.length === 1 && !document.querySelector('input[maxlength="120"]'));
  await page.click(page.button('Vistas')); await page.click(page.button(spanish.common.rename));
  await page.type(document.querySelector('input[maxlength="120"]')!, 'Mi nombre pendiente');
  page.fixture.views[0].version = 5;
  await page.click(page.button('Guardar')); await page.settle(() => document.querySelector('[role="alert"]')?.textContent?.includes('vista cambió') ?? false);
  assert.equal(document.querySelector<HTMLInputElement>('input[maxlength="120"]')!.value, 'Mi nombre pendiente');
  assert.equal(page.fixture.views[0].name, 'Vista inicial');
  await page.click(page.button('Actualizar'));
  await page.settle(() => page.fixture.calls.filter((call) => call.path.endsWith('/report-views') && call.method === 'GET').length >= 2);
  await page.click(page.button('Guardar')); await page.settle(() => page.fixture.views[0].version === 6);
  const writes = page.fixture.calls.filter((call) => call.method === 'PATCH');
  assert.equal((writes[0].body as { expected_version: number }).expected_version, 1);
  assert.equal((writes[1].body as { expected_version: number }).expected_version, 5);
  assert.notEqual(writes[0].headers.get('Idempotency-Key'), writes[1].headers.get('Idempotency-Key'));
});

test("closing the mounted scope aborts a late annotation result without refreshing another screen", async () => {
  const page = await mount();
  const request = globalThis.fetch;
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = (async (input, init) => {
    const response = await request(input, init);
    if (String(input).endsWith('/current-note')) await held;
    return response;
  }) as typeof fetch;
  await page.click(document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`));
  await page.type(document.querySelector('textarea')!, 'Respuesta que llegó tarde');
  await page.click(page.button('Guardar'));
  await page.settle(() => page.fixture.calls.some((call) => call.path.endsWith('/current-note')));
  const queries = page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length;
  await cleanup(); cleanup = async () => {};
  await act(async () => { release(); await Promise.resolve(); await Promise.resolve(); });
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length, queries);
  assert.equal(document.querySelector('textarea'), null);
});


test("phone rows and their attachment editor preserve an authoritative negative decimal", async () => {
  const page = await mount({ large: true, width: 390 });
  const row = document.querySelector(`[data-record-key="draft:${fixtureId(5)}"]`)!;
  assert.match(row.textContent!, /-RD\$ 20\.00/);
  await page.click(row.querySelector(`[data-record-attachment="draft:${fixtureId(5)}"]`));
  await page.settle(() => document.querySelector('[role="dialog"]') !== null);
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /-RD\$ 20\.00/);
});

for (const denied of ['note', 'supporting', 'dossier', 'source'] as const) test(`${denied} access refusal clears the cached report and closes the editor`, async () => {
  const page = await mount();
  await page.click(document.querySelector(`[data-record-${denied === 'source' || denied === 'supporting' ? 'attachment' : 'note'}="draft:${fixtureId(1)}"]`));
  page.fixture.controls.reportForbidden = true;
  if (denied === 'dossier') {
    page.fixture.records[0].revision++;
    await page.click(page.button('Guardar'));
    await page.settle(() => page.button('Recargar') !== undefined);
    const request = globalThis.fetch;
    globalThis.fetch = (async (input, init) => String(input).endsWith('/dossier') ? Response.json({ code: 'permission_denied' }, { status: 403 }) : request(input, init)) as typeof fetch;
    await page.click(page.button('Recargar'));
  } else {
    if (denied === 'supporting') {
      const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
      await act(async () => { Object.defineProperty(input, 'files', { configurable: true, value: [new File(['synthetic'], 'apoyo.pdf', { type: 'application/pdf' })] }); input.dispatchEvent(new Event('change', { bubbles: true })); });
      await page.settle(() => document.querySelector('[data-local-files] li') !== null);
    }
    page.fixture.controls.readOnly = true;
    await page.click(page.button(denied === 'source' ? 'Original sintético.pdf' : 'Guardar'));
  }
  await page.settle(() => document.querySelector('[data-testid="records-count"]') === null && document.querySelector('[role="dialog"]') === null);
  assert.equal(document.querySelectorAll('[data-record-key]').length, 0);
  assert.equal(document.body.textContent?.includes('Proveedor 1'), false);
  assert.equal(document.body.textContent?.includes(spanish.business.transactions.reporting.access_unavailable), true);
});


test("an action refusal re-reads current authority and keeps a still-authorized viewer able to read", async () => {
  const page = await mount();
  await page.click(document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`));
  page.fixture.controls.readOnly = true;
  const queries = page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length;
  await page.click(page.button('Guardar'));
  await page.settle(() => document.querySelector('[role="dialog"]') === null && document.querySelector('[data-testid="records-count"]') !== null && page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length > queries);
  assert.equal(document.querySelector('[data-record-note]'), null);
  await page.click(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  assert.equal(document.querySelector('input[type="file"]'), null);
  assert.equal((page.button('Original sintético.pdf') as HTMLButtonElement).disabled, true);
});
