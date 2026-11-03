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
import { reportRequestSchema, type ReportRecord, type ReportRequest } from "@/lib/business-reports-api";
import { restoreReportLocation } from "@/lib/business-reporting-wire";
import { setChosenGrant } from "@/lib/business-grant";
import { createBusinessReportHttpFixture, fixtureId } from "./fixtures/business-report-http-fixture";
import spanish from "@/public/locales/es-419/common.json";
import { keepOwnListSearch } from "./fixtures/own-list-search";

await keepOwnListSearch();

let cleanup = async () => {};
const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });
async function mount(options: { readOnly?: boolean; large?: boolean; legacy?: boolean; initial?: ReportRequest; width?: number; role?: string; edit?: (records: ReportRecord[]) => void } = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width: options.width ?? 1440, height: 900 });
  const { createRoot } = await import("react-dom/client");
  const fixture = createBusinessReportHttpFixture(); options.edit?.(fixture.records); if (options.large) { fixture.records[0].gross_amount = "9007199254740993.01"; fixture.records[0].recorded_amount = "9007199254740993.01"; fixture.records[3].document_kind = "credit_note"; fixture.records[3].gross_amount = "20.00"; fixture.records[3].adjustment_effect = "known"; fixture.records[4].gross_amount = "-20.00"; fixture.records[4].document_kind = "credit_note"; fixture.records[4].adjustment_effect = "known"; } fixture.controls.readOnly = options.readOnly ?? false; fixture.controls.legacy = options.legacy ?? false;
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
  const context = { chosen: { space_id: fixtureId(3000), grant_id: fixtureId(3001), role: options.role ?? "owner", name: "Colmado sintético", capabilities: options.readOnly ? ["read"] : ["read", "prepare", "approve"], permissions: options.readOnly ? ["read"] : ["read", "prepare", "approve", "download", "export"] }, source, revision: 0, actions: { create: [] }, panel: { kind: "transactions" }, openPanel: () => undefined, records: { workspace: await source.workspace(), inbox: [] } } as unknown as BusinessContextValue;
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.appendChild(host); const root = createRoot(host);
  await act(async () => root.render(<StrictMode><I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><ConnectedBusinessReports initial={options.initial} scope={{ userId: "synthetic-person", businessId: fixtureId(3000), grantId: null }} /></BusinessContext.Provider></I18nextProvider></StrictMode>));
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

test("saved notes stay on the row and the note editor is not offered", async () => {
  const page = await mount();
  const row = document.querySelector(`[data-record-key="draft:${fixtureId(1)}"]`)!;
  assert.match(row.textContent ?? "", /Nota 1/);
  assert.equal(document.querySelector("[data-record-note]"), null);
  assert.equal(document.querySelector("textarea"), null);
  assert.ok(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/current-note")).length, 0);
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
  assert.deepEqual(reportFiltersFromUi(filters, { ...draft, expense_type: ["02"] }, "all").record_families, ["sale", "purchase"]);
  assert.deepEqual(reportFiltersFromUi(filters, draft, "all").currencies, ["CAD", "USD"]);
  assert.deepEqual(reportFiltersFromUi(filters, { ...draft, recordFamilies: undefined }, "gasto").record_families, ["purchase"]);
  assert.equal(validPreviewAmount({ currency: "", min: "1", max: "" }, ["CAD", "USD"]), false);
  assert.equal(validPreviewAmount({ currency: "", min: "", max: "" }, ["CAD", "USD"]), true);
  assert.deepEqual(emptyPreviewFilters().amount, { currency: "", min: "", max: "" });
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

test("the toolbar Export holds 409 for explicit refresh and never exports an unseen changed set", async () => {
  const page = await mount(); page.fixture.controls.exportChanged = true;
  // Agregar lives in the top bar; the toolbar carries Export as its own button.
  assert.equal(document.querySelector('[data-testid="transacciones"] [data-testid="add-menu-header"]'), null);
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => document.querySelector('[role="alert"]')?.textContent?.includes("registros cambiaron") ?? false);
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/reports/export")).length, 1);
  assert.equal(page.downloads.length, 0);
  assert.match(document.body.textContent!, /No incluye archivos originales/);
  const before = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  await page.click(page.button("Actualizar"));
  await page.settle(() => page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length > before && document.querySelector('[data-testid="records-count"]') !== null);
  page.fixture.controls.exportChanged = false;
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => page.downloads.length === 1);
  const exports = page.fixture.calls.filter((call) => call.path.endsWith("/reports/export"));
  assert.equal(exports.length, 2); assert.equal((exports[0].body as { expected_fingerprint: string }).expected_fingerprint, "a".repeat(64));
});

test("a member with export and no Agregar keeps the Export button in place and focused, unavailable, while an export runs", async () => {
  const page = await mount({ role: "accountant" });
  const live = globalThis.fetch;
  let release: () => void = () => undefined;
  let exportStarted = false;
  let exportRequests = 0;
  const held = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/reports/export")) { exportStarted = true; exportRequests += 1; await held; }
    return live(input, init);
  }) as typeof fetch;
  const exportButton = () => document.querySelector<HTMLButtonElement>('[data-testid="records-export"]');
  assert.equal(document.querySelector('[data-testid="business-primary-upload"]'), null);
  assert.equal(document.querySelector('[data-testid="add-menu-header"]'), null, "the toolbar carries no Agregar");
  const unavailable = () => exportButton()?.getAttribute("aria-disabled") === "true";
  await page.settle(() => document.querySelector('[data-testid="records-count"]') !== null && exportButton() !== null && !unavailable());
  const before = exportButton()!;
  before.focus();
  await page.click(before);
  await page.settle(() => exportStarted && unavailable());
  assert.equal(exportButton(), before, "the button stays in place while the export runs");
  assert.equal(exportButton()!.disabled, false, "aria-disabled, not disabled, so focus stays");
  assert.equal(document.activeElement, before, "focus stays on Export while it runs");
  await page.click(exportButton());
  assert.equal(exportRequests, 1, "pressing the disabled button starts no second export");
  release();
  await page.settle(() => page.downloads.length === 1);
  assert.equal(exportButton(), before, "the button is still there after the download");
  await page.settle(() => !unavailable());
  assert.equal(unavailable(), false, "the export is live again");
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

const amounts = (card: Element) => [...card.querySelectorAll("[data-currency]")].map((row) => row.textContent);
const cards = () => [...document.querySelectorAll('[data-testid="records-results-summary"] [data-summary-part]')];

test("sales card one shows the server document totals per currency and later cards stay unavailable", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['sale'] } }) });
  const summary = document.querySelector('[data-testid="records-results-summary"]')!;
  assert.equal(summary.getAttribute('data-summary-kind'), 'venta');
  assert.equal(cards().length, 3);
  assert.deepEqual(amounts(cards()[0]), ['RD$6,200.00', 'US$100.00']);
  assert.match(cards()[0].textContent!, /Facturado/);
  for (const later of cards().slice(1)) { assert.equal(later.querySelectorAll('.cuadrao-amount').length, 0); assert.match(later.textContent!, /-/); }
  assert.equal(document.body.textContent?.includes('Cobros, pagos y saldos pendientes aún no están disponibles.'), true);
  assert.equal(summary.querySelectorAll('[data-summary-qualifier]').length, 1);
  assert.ok(cards()[0].querySelector('[data-summary-qualifier]'));
  assert.equal(cards()[0].querySelector('[data-summary-qualifier]')!.textContent, 'Incluye documentos por revisar o por aprobar.');
  assert.ok(page.fixture.calls.every((call) => !call.path.includes('/totals')));
});

test("the review qualifier hides under the ready-for-export filter and shows again when it is cleared", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['sale'] } }) });
  assert.ok(document.querySelector('[data-summary-qualifier]'));
  await page.click(document.querySelector('[data-overview-filter="export"]'));
  await page.settle(() => document.querySelector('[data-testid="records-count"]')?.textContent?.includes('0') ?? false);
  assert.deepEqual((page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).at(-1)!.body as { filters: { review_stages: string[] } }).filters.review_stages, ['ready_for_export']);
  assert.equal(document.querySelector('[data-summary-qualifier]'), null);
  await page.click(document.querySelector('[data-overview-filter="export"]'));
  await page.settle(() => document.querySelector('[data-summary-qualifier]') !== null);
});

test("the review qualifier stays when the filter keeps review stages beside ready for export", async () => {
  await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['sale'], review_stages: ['needs_review', 'ready_for_export'] } }) });
  assert.ok(document.querySelector('[data-summary-qualifier]'));
});

test("the review qualifier hides when the server overview reports nothing to review or approve", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['sale'] } }) });
  page.fixture.controls.overview = { needs_review: 0, awaiting_approval: 0, ready_for_export: 126 };
  await page.click(document.querySelector('[data-testid="records-refresh"]'));
  await page.settle(() => document.querySelector('[data-summary-qualifier]') === null);
  assert.equal(cards()[0].querySelectorAll('.cuadrao-amount').length > 0, true);
  page.fixture.controls.overview = { needs_review: 0, awaiting_approval: 3, ready_for_export: 123 };
  await page.click(document.querySelector('[data-testid="records-refresh"]'));
  await page.settle(() => document.querySelector('[data-summary-qualifier]') !== null);
});

test("expense card one keeps an unknown currency unknown and never invents a code or zero", async () => {
  await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['purchase'] } }) });
  const [first, second] = [...cards()[0].querySelectorAll("[data-currency], .currencyRow, dd > div")];
  assert.match(cards()[0].textContent!, /Gastos/);
  assert.equal(first.textContent, 'RD$6,200.00');
  assert.match(second.textContent!, /^Sin moneda-/);
  assert.equal(cards()[0].querySelectorAll('.cuadrao-amount').length, 1);
  assert.doesNotMatch(cards()[0].textContent!, /(?<![\d,])0\.00/);
});

test("card one follows the same answer as rows and count when the search changes", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['sale'] } }) });
  assert.match(document.querySelector('[data-testid="records-count"]')!.textContent!, /63/);
  const before = page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length;
  await page.type(document.querySelector('input[type="search"]')!, 'pena');
  await page.settle(() => document.querySelector('[data-testid="records-count"]')?.textContent?.includes('1 de 1') ?? false);
  assert.deepEqual(amounts(cards()[0]), ['RD$100.00']);
  const queries = page.fixture.calls.filter((call) => call.path.endsWith('/reports/query'));
  assert.equal(queries.length - before, 1);
  assert.equal((queries.at(-1)!.body as { filters: { q: string } }).filters.q, 'pena');
});

test("card one shows unknown, not the previous query's totals, while the next query loads", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['sale'] } }) });
  assert.deepEqual(amounts(cards()[0]), ['RD$6,200.00', 'US$100.00']);
  const live = globalThis.fetch;
  let release!: () => void;
  let started = false;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => String(input).endsWith('/reports/query') ? (started = true, gate.then(() => live(input, init))) : live(input, init)) as typeof fetch;
  await page.type(document.querySelector('input[type="search"]')!, 'pena');
  await page.settle(() => started);
  assert.equal(cards()[0].querySelectorAll('.cuadrao-amount').length, 0);
  assert.doesNotMatch(cards()[0].textContent!, /6,200|100\.00/);
  release();
  await page.settle(() => cards()[0].querySelectorAll('.cuadrao-amount').length > 0);
  assert.deepEqual(amounts(cards()[0]), ['RD$100.00']);
  globalThis.fetch = live;
});

test("an incomplete server total shows unknown beside its labelled known part, never as final money", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: 'all' }, record_families: ['sale'] } }) });
  const row = page.fixture.records.find((record) => record.family === 'sale' && record.currency === 'DOP')!;
  row.gross_amount = null;
  await page.click(document.querySelector('[data-testid="records-refresh"]'));
  await page.settle(() => cards()[0]?.querySelector('[data-partial-known]') !== null);
  const dop = cards()[0].querySelector('[data-currency="DOP"]') ?? cards()[0].querySelector('dd > div')!;
  assert.equal([...dop.querySelectorAll('.cuadrao-amount')].filter((amount) => !amount.closest('[data-partial-known]')).length, 0);
  assert.match(dop.textContent!, /-/);
  assert.match(dop.textContent!, /Parcial: RD\$6,100\.00/);
  const known = dop.querySelector('[data-partial-known] .cuadrao-amount')!;
  assert.equal(known.textContent, 'RD$6,100.00');
  assert.ok(known.classList.contains('tabular-nums'));
  assert.equal(dop.querySelector('[data-partial-known]')!.textContent, 'Parcial: RD$6,100.00');
  assert.equal(cards()[0].querySelectorAll('.cuadrao-amount').length, 2);
});

test("desktop shows a refresh control that reloads the query and holds a busy state until it answers", async () => {
  const page = await mount();
  const control = () => document.querySelector<HTMLButtonElement>('[data-testid="records-refresh"]')!;
  assert.ok(control());
  assert.equal(control().getAttribute('aria-label'), 'Actualizar registros');
  assert.equal(control().disabled, false);
  const live = globalThis.fetch;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => String(input).endsWith('/reports/query') ? gate.then(() => live(input, init)) : live(input, init)) as typeof fetch;
  const before = page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length;
  await page.click(control());
  assert.equal(control().disabled, true);
  assert.equal(control().getAttribute('aria-busy'), 'true');
  await page.click(control());
  release();
  await page.settle(() => !control().disabled);
  assert.equal(control().getAttribute('aria-busy'), 'false');
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length - before, 1);
  globalThis.fetch = live;
});

test("the phone keeps the pull gesture and gets no toolbar refresh control", async () => {
  await mount({ width: 390 });
  assert.equal(document.querySelector('[data-testid="records-refresh"]'), null);
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

test("phone rows and their attachment editor preserve an authoritative negative decimal", async () => {
  const page = await mount({ large: true, width: 390 });
  const row = document.querySelector(`[data-record-key="draft:${fixtureId(5)}"]`)!;
  assert.match(row.textContent!, /-RD\$ 20\.00/);
  await page.click(row.querySelector(`[data-record-attachment="draft:${fixtureId(5)}"]`));
  await page.settle(() => document.querySelector('[role="dialog"]') !== null);
  assert.match(document.querySelector('[role="dialog"]')!.textContent!, /-RD\$ 20\.00/);
});

for (const denied of ['supporting', 'source'] as const) test(`${denied} access refusal clears the cached report and closes the editor`, async () => {
  const page = await mount();
  await page.click(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  page.fixture.controls.reportForbidden = true;
  if (denied === 'supporting') {
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    await act(async () => { Object.defineProperty(input, 'files', { configurable: true, value: [new File(['synthetic'], 'apoyo.pdf', { type: 'application/pdf' })] }); input.dispatchEvent(new Event('change', { bubbles: true })); });
    await page.settle(() => document.querySelector('[data-local-files] li') !== null);
  }
  page.fixture.controls.readOnly = true;
  await page.click(page.button(denied === 'source' ? 'Original sintético.pdf' : 'Guardar'));
  await page.settle(() => document.querySelector('[data-testid="records-count"]') === null && document.querySelector('[role="dialog"]') === null);
  assert.equal(document.querySelectorAll('[data-record-key]').length, 0);
  assert.equal(document.body.textContent?.includes('Proveedor 1'), false);
  assert.equal(document.body.textContent?.includes(spanish.business.transactions.reporting.access_unavailable), true);
});


const sentFilters = (page: Awaited<ReturnType<typeof mount>>) => page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).map((call) => (call.body as ReportRequest).filters);
const addressFilters = () => restoreReportLocation(new URL(window.location.href).searchParams).request.filters;
const pause = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });

test("a phone Filtros choice holds after its sheet closes, and back still undoes it", async () => {
  const page = await mount({ width: 390 });
  const before = sentFilters(page).length;
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('[role="dialog"] [data-group="record"]'));
  await page.click([...document.querySelectorAll<HTMLInputElement>('[role="dialog"] input[type="radio"]')].find((radio) => radio.parentElement?.textContent === "Venta"));
  await page.click(page.button("Aplicar"));
  await page.settle(() => document.querySelector('[role="dialog"]') === null && document.querySelector('[data-testid="records-count"]') !== null);
  await pause(200);
  assert.deepEqual(sentFilters(page).slice(before).map((filters) => filters.record_families), [["sale"]]);
  assert.deepEqual(addressFilters().record_families, ["sale"]);
  assert.match(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent ?? "", /Venta/);
  assert.ok(document.querySelector('[data-testid="records-results-summary"]'));
  await act(async () => window.history.back());
  await page.settle(() => document.querySelector('[data-testid="records-preview-filter-chips"]') === null);
  assert.deepEqual(sentFilters(page).at(-1)!.record_families, []);
});

test("Registros opens on the server's latest month and names it", async () => {
  const page = await mount({ edit: (records) => { for (const row of records) if (row.report_date) row.report_date = "2026-08-14"; } });
  assert.ok(sentFilters(page).length > 0);
  assert.ok(sentFilters(page).every((filters) => filters.period.kind === "latest_month"));
  assert.ok(page.button("Agosto de 2026"), "the period control names the month the server answered with");
});

test("a period the person chose stays chosen when Registros opens again", async () => {
  const first = await mount({ width: 390 });
  await first.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  await first.click(first.button("Mes pasado"));
  await first.click(first.button("Confirmar período"));
  await first.settle(() => addressFilters().period.kind === "last_month");
  const address = window.location.href;
  await cleanup();
  (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL(address);
  const again = await mount({ width: 390 });
  assert.ok(sentFilters(again).every((filters) => filters.period.kind === "last_month"));
  assert.equal(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]')?.textContent, "Mes pasado");
});

test("the Estado chip names the one missing fact on the live panel", async () => {
  await mount({ edit: (records) => { Object.assign(records[0], { stage: "needs_fiscal_data", export_missing: "payment_method_missing", export_missing_several: false }); Object.assign(records[1], { stage: "needs_fiscal_data", export_missing: "ncf_missing", export_missing_several: true }); } });
  const chip = (id: number) => document.querySelector(`[data-record-key="draft:${fixtureId(id)}"] td[data-col="estado"] [data-record-workflow="fiscal"]`)?.textContent;
  assert.equal(chip(1), "Falta la forma de pago");
  assert.equal(chip(2), "Faltan datos fiscales");
});

test("Tipo de gasto takes Categoría's slot with the server's name, Bandeja's missing word and a dash for a sale", async () => {
  const page = await mount();
  const cell = (id: number, column: string) => document.querySelector(`[data-record-key="draft:${fixtureId(id)}"] td[data-col="${column}"]`);
  const headings = [...document.querySelectorAll("thead th")].map((node) => node.getAttribute("data-col"));
  assert.ok(!headings.includes("categoria") && headings.indexOf("tipo_gasto") === headings.indexOf("detalle") + 1, "Tipo de gasto sits where Categoría sat");
  assert.equal(document.querySelector('th[data-col="tipo_gasto"]')?.textContent, "Tipo de gasto");
  assert.equal(document.querySelector('th[data-col="forma_pago"]'), null, "Forma de pago starts hidden");
  assert.equal(cell(1, "tipo_gasto")?.textContent, "Falta");
  assert.equal(cell(3, "tipo_gasto")?.textContent, "Gastos por trabajos, suministros y servicios");
  assert.equal(cell(2, "tipo_gasto")?.querySelector(".sr-only")?.textContent, "No aplica");
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  await page.click([...document.querySelectorAll('button[role="radio"]')].find((node) => node.textContent === "Columnas"));
  await page.click(document.querySelector('[data-column-setting="forma_pago"] label'));
  await page.settle(() => document.querySelector('th[data-col="forma_pago"]') !== null);
  assert.equal(document.querySelector('th[data-col="forma_pago"]')?.textContent, "Forma de pago");
  assert.equal(cell(1, "forma_pago")?.textContent, "Falta");
  assert.equal(cell(3, "forma_pago")?.textContent, "Efectivo");
  const request = restoreReportLocation(new URL(window.location.href).searchParams).request;
  assert.deepEqual(request.schema_version === 2 ? request.presentation.hidden : null, ["funding"], "the chosen columns travel with the saved presentation");
});

test("Filtros offers Tipo de gasto from the server's catalogue plus Falta, and sends expense_types", async () => {
  const page = await mount();
  const before = sentFilters(page).length;
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('[data-group="expense_type"]'));
  const labels = [...document.querySelectorAll('[role="dialog"] label')].map((label) => label.textContent).filter((label) => label !== "Seleccionar todo");
  assert.deepEqual(labels, ["Gastos por trabajos, suministros y servicios", "Falta"]);
  await page.click([...document.querySelectorAll<HTMLInputElement>('[role="dialog"] input[type="checkbox"]')].find((box) => box.parentElement?.textContent === "Falta"));
  await page.click(page.button("Aplicar"));
  await page.settle(() => sentFilters(page).length > before);
  assert.deepEqual(sentFilters(page).at(-1)!.expense_types, ["missing"]);
  assert.match(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent ?? "", /Tipo de gasto · Falta/);
  // 21 of the 126 fixture rows are purchases still missing their tipo de gasto.
  await page.settle(() => document.querySelectorAll("tbody tr").length === 21);
  assert.ok([...document.querySelectorAll('tbody tr td[data-col="tipo_gasto"]')].every((node) => node.textContent === "Falta"));
});

test("Filtros offers only the document kinds a row can carry, and each one finds its records", async () => {
  const { REPORT_DOCUMENT_KINDS, reportRecordSchema } = await import("@/lib/business-reports-api");
  assert.deepEqual([...REPORT_DOCUMENT_KINDS], ["credit_note", "unknown"]);
  const page = await mount({ edit: (records) => { records[4].document_kind = "credit_note"; records[6].document_kind = "credit_note"; } });
  for (const kind of REPORT_DOCUMENT_KINDS) assert.ok(reportRecordSchema.shape.document_kind.options.includes(kind), `${kind} is a contract kind`);
  const before = sentFilters(page).length;
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('[data-group="document"]'));
  const labels = [...document.querySelectorAll('[role="dialog"] label')].map((label) => label.textContent).filter((label) => label !== "Seleccionar todo");
  assert.deepEqual(labels, ["Nota de crédito", "sin dato"]);
  await page.click([...document.querySelectorAll<HTMLInputElement>('[role="dialog"] input[type="checkbox"]')].find((box) => box.parentElement?.textContent === "Nota de crédito"));
  await page.click(page.button("Aplicar"));
  await page.settle(() => sentFilters(page).length > before);
  assert.deepEqual(sentFilters(page).at(-1)!.document_kinds, ["credit_note"]);
  await page.settle(() => document.querySelectorAll("tbody tr").length === 2);
  assert.deepEqual([...document.querySelectorAll("tbody tr")].map((row) => row.getAttribute("data-record-key")), [`draft:${fixtureId(5)}`, `draft:${fixtureId(7)}`]);
});

const aboveTable = () => { const section = document.querySelector('[data-testid="transacciones"]')!; const nodes = [...section.children]; const end = nodes.findIndex((node) => node.querySelector('[data-testid="transacciones-records"], [data-empty-kind]')); return nodes.slice(0, end).map((node) => `${node.tagName}:${node.getAttribute("data-testid") ?? node.getAttribute("role") ?? ""}`); };

test("a filter with no rows shows one title, keeps the pill row as the only clear action, and moves nothing above the table", async () => {
  const page = await mount({ edit: (records) => { for (const row of records) row.dgii_606 = null; } });
  const before = aboveTable();
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('[data-group="expense_type"]'));
  await page.click([...document.querySelectorAll<HTMLInputElement>('[role="dialog"] input[type="checkbox"]')].find((box) => box.parentElement?.textContent === "Falta"));
  await page.click(page.button("Aplicar"));
  await page.settle(() => document.querySelector('[data-empty-kind]') !== null);
  const empty = document.querySelector('[data-empty-kind="filtered"]')!;
  assert.equal(empty.querySelector("h3")?.textContent, "No hay registros con estos filtros");
  assert.equal(empty.querySelector("p"), null, "no body line");
  assert.equal(empty.querySelector("button"), null, "no second clear action");
  assert.doesNotMatch(document.body.textContent ?? "", /Cada gasto y cada venta que apruebas/);
  const clears = [...document.querySelectorAll("button")].filter((node) => node.textContent === "Limpiar filtros");
  assert.equal(clears.length, 1); assert.ok(document.querySelector('[data-testid="records-preview-filter-chips"]')!.contains(clears[0]), "the pill row's Limpiar filtros is the one");
  assert.deepEqual(aboveTable(), before, "nothing above the table moved");
  await page.click(clears[0]);
  await page.settle(() => document.querySelectorAll("tbody tr").length === 25);
  assert.deepEqual(aboveTable(), before);
});

test("a Registros with nothing in the period keeps its first-run message and the Bandeja line, with no clear action", async () => {
  await mount({ edit: (records) => { records.splice(0); } });
  const empty = document.querySelector('[data-empty-kind="first_run"]')!;
  assert.equal(empty.querySelector("h3")?.textContent, "Aquí verás tus gastos y ventas");
  assert.equal(empty.querySelector("p")?.textContent, "Cada gasto y cada venta que apruebas en la Bandeja aparece aquí en su fecha.");
  assert.equal([...document.querySelectorAll("button")].filter((node) => node.textContent === "Limpiar filtros").length, 0);
  assert.equal(document.querySelector('[data-empty-kind="filtered"]'), null);
});

test("a record that left the view says so in a toast, never in a line above the table", async () => {
  const { useToasts, clearToasts } = await import("@/components/business-app/foundation/toasts");
  clearToasts();
  (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL(`http://localhost/biz?report_row=draft:${fixtureId(999)}&report_scope=synthetic-person:${fixtureId(3000)}`);
  const page = await mount();
  function Probe() { return <output data-testid="toast-probe">{useToasts().map((toast) => `${toast.kind}:${toast.text}:${toast.action ? "action" : "no-action"}`).join("|")}</output>; }
  const { createRoot } = await import("react-dom/client");
  const host = document.createElement("div"); document.body.appendChild(host); const root = createRoot(host);
  await act(async () => root.render(<Probe />));
  await page.settle(() => (document.querySelector('[data-testid="toast-probe"]')?.textContent ?? "").includes("Este registro no está disponible."));
  assert.equal(document.querySelector('[data-testid="toast-probe"]')!.textContent, "info:Este registro no está disponible.:no-action");
  assert.equal([...document.querySelectorAll('[data-testid="transacciones"] [role="status"]')].filter((node) => /no está disponible/.test(node.textContent ?? "")).length, 0);
  assert.doesNotMatch(document.querySelector('[data-testid="transacciones"]')!.textContent ?? "", /no está disponible/);
  await act(async () => root.unmount());
});

test("a phone period preset holds after its sheet closes", async () => {
  const page = await mount({ width: 390, initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: "this_month" } } }) });
  const before = sentFilters(page).length;
  await page.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  await page.click(page.button("Todas las fechas"));
  await page.click(page.button("Confirmar período"));
  await page.settle(() => document.querySelector('[role="dialog"]') === null && document.querySelector('[data-testid="records-count"]') !== null);
  await pause(200);
  assert.deepEqual(sentFilters(page).slice(before).map((filters) => filters.period), [{ kind: "all" }]);
  assert.deepEqual(addressFilters().period, { kind: "all" });
});

for (const [preset, kind] of [["Este mes", "this_month"], ["Este año", "this_year"], ["Mes pasado", "last_month"]] as const) test(`${preset} in the one preset list asks the server for ${kind}`, async () => {
  const page = await mount({ width: 390 });
  const before = sentFilters(page).length;
  await page.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  await page.click(page.button(preset));
  assert.equal(sentFilters(page).length, before, "choosing a preset only selects dates");
  await page.click(page.button("Confirmar período"));
  await page.settle(() => addressFilters().period.kind === kind && document.querySelector('[role="dialog"]') === null && document.querySelector('[data-testid="records-count"]') !== null);
  await pause(200);
  assert.deepEqual(sentFilters(page).slice(before).map((filters) => filters.period), [{ kind }]);
  const label = { this_month: "Este mes", this_year: String(new Date().getFullYear()), last_month: "Mes pasado" }[kind];
  assert.equal(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]')?.textContent, label, "the button names the whole period, not its dates");
});

test("Registros opens its picker on the current period, on Personalizado only when no preset matches", async () => {
  const resetAddress = () => (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz");
  const month = await mount({ width: 390, initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: "this_month" } } }) });
  await month.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  const pressed = () => [...document.querySelectorAll('[aria-label="Períodos rápidos"] button[aria-pressed="true"]')].map((node) => node.textContent);
  const fields = () => [...document.querySelectorAll<HTMLInputElement>('[data-testid="range-picker"] input')].map((input) => input.value);
  assert.deepEqual(pressed(), ["Este mes"]);
  assert.equal(fields()[0], "01/10/2026");
  await cleanup(); resetAddress();
  const latest = await mount({ width: 390, edit: (records) => { for (const row of records) if (row.report_date) row.report_date = "2026-08-14"; } });
  await latest.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  assert.deepEqual(pressed(), ["Personalizado"]);
  assert.deepEqual(fields(), ["01/08/2026", "31/08/2026"]);
  await cleanup(); resetAddress();
  const all = await mount({ width: 390, initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: "all" } } }) });
  await all.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  assert.deepEqual(pressed(), ["Todas las fechas"]);
  assert.deepEqual(fields(), ["", ""]);
});

test("closing the phone Filtros sheet without a choice sends no query", async () => {
  const page = await mount({ width: 390 });
  const before = sentFilters(page).length;
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('[role="dialog"] button[aria-label="Cerrar"]'));
  await page.settle(() => document.querySelector('[role="dialog"]') === null);
  await pause(200);
  assert.equal(sentFilters(page).length, before);
});
