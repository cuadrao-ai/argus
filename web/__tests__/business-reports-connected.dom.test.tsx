import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, setSystemTime, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, StrictMode } from "react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { Plus } from "lucide-react";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import BusinessReportsPanel, { ConnectedBusinessReports, reportFiltersForUi, reportFiltersFromUi } from "@/components/business-app/transacciones/BusinessReportsPanel";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { emptyPreviewFilters, validPreviewAmount } from "@/components/business-app/transacciones/records-filter-preview-model";
import { reportAnswerSchema, reportRequestSchema, type ReportAnswer, type ReportRecord, type ReportRequest, type RecordsCurrency } from "@/lib/business-reports-api";
import { restoreReportLocation } from "@/lib/business-reporting-wire";
import { setChosenGrant } from "@/lib/business-grant";
import { createBusinessReportHttpFixture, fixtureId } from "./fixtures/business-report-http-fixture";
import english from "@/public/locales/en/common.json";
import { recordedReportAnswer } from "./fixtures/recorded-report-answer";
import spanish from "@/public/locales/es-419/common.json";
import { keepOwnListSearch } from "./fixtures/own-list-search";

await keepOwnListSearch();

let cleanup = async () => {};
const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });
async function mount(options: { onAdd?: () => void; defaultCurrency?: RecordsCurrency; workspaceFailure?: "error" | "refused" | "missing_default"; viewRecipe?: ReportRequest; topLevel?: boolean; grantId?: string; workspaceGrant?: string | null; readOnly?: boolean; large?: boolean; legacy?: boolean; initial?: ReportRequest; width?: number; queryGate?: Promise<void>; queryAnswer?: (request: ReportRequest, answer: ReportAnswer) => ReportAnswer | Promise<ReportAnswer>; waitForAnswer?: boolean; language?: "es-419" | "en"; presentation?: typeof recordedReportAnswer.presentation; role?: string; edit?: (records: ReportRecord[]) => void; waiting?: number | null } = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width: options.width ?? 1440, height: 900 });
  const { createRoot } = await import("react-dom/client");
  const fixture = createBusinessReportHttpFixture(); for (const row of fixture.records) if (row.currency !== "DOP") { row.currency = "DOP"; row.recorded_currency = "DOP"; } if (options.presentation) fixture.controls.presentation = options.presentation; options.edit?.(fixture.records); if (options.large) { fixture.records[1].family = "purchase"; fixture.records[0].gross_amount = "9007199254740993.01"; fixture.records[0].recorded_amount = "9007199254740993.01"; fixture.records[3].family = "purchase"; fixture.records[3].document_kind = "credit_note"; fixture.records[3].gross_amount = "20.00"; fixture.records[3].adjustment_effect = "known"; fixture.records[4].gross_amount = "-20.00"; fixture.records[4].document_kind = "credit_note"; fixture.records[4].adjustment_effect = "known"; } fixture.controls.readOnly = options.readOnly ?? false; fixture.controls.legacy = options.legacy ?? false;
  if (options.viewRecipe) fixture.views.push({ id: fixtureId(3300), name: "Moneda guardada", recipe: { schema_version: options.viewRecipe.schema_version, filters: options.viewRecipe.filters, columns: options.viewRecipe.columns, sort: options.viewRecipe.sort, ...(options.viewRecipe.schema_version === 2 ? { page_size: options.viewRecipe.page_size } : {}) }, version: 1, created_at: "2026-11-07T00:00:00Z", updated_at: "2026-11-07T00:00:00Z" });
  const computedStyle = globalThis.getComputedStyle;
  if (options.width && options.width < 1024) globalThis.getComputedStyle = ((element: Element) => {
    const style = computedStyle(element);
    return new Proxy(style, { get(target, key) { if (key === 'getPropertyValue') return (name: string) => name === '--records-narrow' ? '1' : target.getPropertyValue(name); const value = Reflect.get(target, key); return typeof value === 'function' ? value.bind(target) : value; } });
  }) as typeof getComputedStyle;
  const originalFetch = globalThis.fetch; globalThis.fetch = (async (input, init) => {
    if (String(input).endsWith("/me")) return Response.json({ user: { id: "synthetic-person", language: "es-419" } });
    const query = String(input).endsWith("/reports/query");
    if (options.queryGate && query) await options.queryGate;
    const response = await fixture.request(input, init);
    return query && options.queryAnswer && response.ok ? Response.json(await options.queryAnswer(reportRequestSchema.parse(JSON.parse(String(init?.body))), reportAnswerSchema.parse(await response.json()))) : response;
  }) as typeof fetch;
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
  const downloads: Blob[] = []; URL.createObjectURL = (blob) => { downloads.push(blob as Blob); return "blob:synthetic"; }; URL.revokeObjectURL = () => undefined;
  setChosenGrant(options.grantId ?? null);
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const opened: unknown[] = [];
  const receiptActivity = options.waiting === undefined ? null : options.waiting === null ? null : { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: options.waiting, needs_attention_count: 0, ready_to_review_count: options.waiting };
  const context = { chosen: { space_id: fixtureId(3000), grant_id: fixtureId(3001), role: options.role ?? "owner", name: "Colmado sintético", capabilities: options.readOnly ? ["read"] : ["read", "prepare", "approve"], permissions: options.readOnly ? ["read"] : ["read", "prepare", "approve", "download", "export"] }, source, revision: 0, actions: { create: options.onAdd ? [{ id: "upload_receipt", label: "Agregar", icon: Plus, run: options.onAdd }] : [] }, panel: { kind: "transactions" }, openPanel: (panel: unknown) => { opened.push(panel); }, records: { workspace: { ...await source.workspace(), currency: "CAD", records_default_currency: options.defaultCurrency ?? "DOP" }, workspaceGrant: options.workspaceGrant === undefined ? options.grantId ?? null : options.workspaceGrant, inbox: [], receiptActivity } } as unknown as BusinessContextValue;
  const i18n = i18next.createInstance(); await i18n.init({ lng: options.language ?? "es-419", resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.appendChild(host); const root = createRoot(host);
  let reloads = 0;
  const render = () => root.render(<StrictMode><I18nextProvider i18n={i18n}><BusinessContext.Provider value={{ ...context }}>{options.topLevel ? <BusinessReportsPanel /> : <ConnectedBusinessReports defaultCurrency={context.records.workspace!.records_default_currency} initial={options.initial} scope={{ userId: "synthetic-person", businessId: fixtureId(3000), grantId: options.grantId ?? null }} />}</BusinessContext.Provider></I18nextProvider></StrictMode>);
  const rerender = () => act(async () => render());
  context.reload = () => {
    reloads += 1;
    void source.workspace().then((workspace) => { context.records.workspace = workspace; context.records.workspaceGrant = options.grantId ?? null; context.records.error = false; context.records.refused = false; render(); });
  };
  if (options.workspaceFailure) {
    if (options.workspaceFailure === "missing_default") Object.assign(context.records.workspace!, { records_default_currency: "CAD" });
    else { context.records.workspace = null; context.records.error = true; context.records.refused = options.workspaceFailure === "refused"; context.records.failureReference = "SYNTHETIC-REF"; }
  }
  await rerender();
  cleanup = async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; globalThis.getComputedStyle = computedStyle; URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; };
  const settle = async (predicate: () => boolean) => { for (let i = 0; i < 80; i++) { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); }); if (predicate()) return; } throw new Error(`Missing state ${document.body.textContent?.slice(-600)}`); };
  const click = async (element: Element | undefined | null) => { assert.ok(element); await act(async () => (element as HTMLElement).click()); };
  const button = (label: string) => [...document.querySelectorAll("button")].find((button) => button.textContent?.trim() === label || label === "Filtros" && button.textContent?.startsWith("Filtros") || button.getAttribute("aria-label") === label);
  const type = async (element: HTMLInputElement | HTMLTextAreaElement, value: string) => { await act(async () => { const prototype = element instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(element, value); element.dispatchEvent(new Event("input", { bubbles: true })); }); };
  if (options.waitForAnswer !== false) await settle(() => document.querySelector(`[data-report-schema="${options.legacy ? 1 : 2}"] [data-testid="records-count"]`) !== null);
  return { fixture, settle, click, button, type, downloads, opened, context, rerender, reloads: () => reloads };
}

test("connected pages, full count, accent search and filtered overview use real transport", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { record_families: ["sale"] } }) });
  assert.match(document.querySelector('[data-testid="records-count"]')!.textContent!, /63/);
  assert.equal(document.querySelectorAll("tbody tr").length, 25);
  assert.ok(page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).every((call) => (call.body as { filters: { period: unknown } }).filters.period && !(call.body as Record<string, unknown>).business_id));
  await page.click(document.querySelector('button[aria-label="Última página"]'));
  await page.settle(() => document.querySelector('[data-testid="records-pagination"]')?.getAttribute("data-page") === "3");
  assert.equal(document.querySelectorAll("tbody tr").length, 13);
  await page.type(document.querySelector('input[type="search"]')!, "pena");
  await page.settle(() => document.querySelector('[data-testid="records-count"]')?.textContent?.includes("1 de 1") ?? false);
  assert.match(document.querySelector('[data-testid="transacciones-records"]')!.textContent!, /José Peña/);
  assert.equal(document.querySelector('[data-overview-filter="fiscal"]')!.querySelector(".font-display")?.textContent, "0");
  assert.ok(page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).some((call) => (call.body as { filters: { q: string }; page: number }).filters.q === "pena" && (call.body as { page: number }).page === 1));
});

const overviewCards = () => [...document.querySelectorAll<HTMLButtonElement>('[data-testid="records-overview-preview"] [data-overview-filter]')];

test("Total stays static without requests, filters or navigation", async () => {
  const page = await mount();
  const calls = page.fixture.calls.length;
  const filters = structuredClone(sentFilters(page).at(-1));
  const address = window.location.href;
  const historyLength = window.history.length;
  const total = document.querySelector('[data-overview-card="total"]')!;
  assert.equal(total.tagName, "DIV");
  assert.equal(total.hasAttribute("tabindex"), false);
  assert.equal(total.getAttribute("role"), null);
  assert.equal(total.querySelector("button, [role=button], [tabindex], [aria-expanded], [aria-controls]"), null);
  assert.equal(total.querySelectorAll("svg").length, 1);
  await page.click(total);
  assert.equal(document.querySelector('[data-testid="records-results-summary"]'), null);
  assert.equal(page.fixture.calls.length, calls);
  assert.deepEqual(sentFilters(page).at(-1), filters);
  assert.equal(window.location.href, address);
  assert.equal(window.history.length, historyLength);
  assert.deepEqual(page.opened, []);
});

test("six cards show report scope and only fiscal applies its stage", async () => {
  const page = await mount({ edit: (rows) => rows.slice(3, 63).forEach((row) => { row.stage = "needs_fiscal_data"; }) });
  assert.deepEqual(overviewCards().map((card) => card.getAttribute("data-overview-filter")), ["fiscal"]);
  assert.equal(document.querySelectorAll("[data-overview-card]").length, 6);
  assert.match(document.querySelector('[data-overview-card="quantity"]')!.textContent!, /63/);
  const fiscal = overviewCards()[0]; assert.match(fiscal.textContent!, /Faltan datos fiscales/); assert.match(fiscal.textContent!, /30/);
  assert.doesNotMatch(document.querySelector('[data-testid="records-overview-preview"]')!.textContent!, /Listos para exportar|Ya exportados|Por aprobar|Por revisar/);
  const before = sentFilters(page).length;
  await page.click(fiscal); await page.settle(() => sentFilters(page).length > before);
  assert.deepEqual(sentFilters(page).at(-1)!.review_stages, ["needs_fiscal_data"]);
  assert.equal(document.querySelector('[data-overview-filter="fiscal"]')?.getAttribute("aria-pressed"), "true");
  assert.ok(document.querySelector('button[aria-label="Quitar filtro Revisión"]'));
  await page.click(fiscal);
  await page.settle(() => document.querySelector('[data-overview-filter="fiscal"]')?.getAttribute("aria-pressed") === "false");
  assert.deepEqual(sentFilters(page).at(-1)!.review_stages, []);
  await page.click(fiscal);
  await page.settle(() => document.querySelector('[data-overview-filter="fiscal"]')?.getAttribute("aria-pressed") === "true");
  await page.click(document.querySelector('button[aria-label="Quitar filtro Revisión"]'));
  await page.settle(() => document.querySelector('[data-overview-filter="fiscal"]')?.getAttribute("aria-pressed") === "false");
});

test("a server without the fiscal count leaves the action unknown", async () => {
  const page = await mount();
  page.fixture.controls.overview = { needs_review: 0, ready_for_export: 126 };
  await page.click(document.querySelector('[data-testid="records-refresh"]'));
  await page.settle(() => document.querySelector<HTMLButtonElement>('[data-overview-filter="fiscal"]')?.disabled === true);
  assert.equal(document.querySelector('[data-overview-filter="exported"]'), null);
});

test("the Bandeja line shows the receipt activity count the sidebar shows, opens the Bandeja, and hides at zero or unknown", async () => {
  const { inboxCount } = await import("@/components/business-app/inbox-count");
  const page = await mount({ waiting: 4 });
  const line = document.querySelector('[data-testid="records-bandeja-waiting"]')!;
  assert.equal(line.textContent, "4 recibos esperan en la Bandeja");
  assert.equal(inboxCount(page.context.records), 4);
  await page.click(line.querySelector("button"));
  assert.deepEqual(page.opened, [{ kind: "inbox" }]);
  await cleanup();
  await mount({ waiting: 1 });
  assert.equal(document.querySelector('[data-testid="records-bandeja-waiting"]')!.textContent, "1 recibo espera en la Bandeja");
  await cleanup();
  await mount({ waiting: 0 });
  assert.equal(document.querySelector('[data-testid="records-bandeja-waiting"]'), null);
  await cleanup();
  await mount({ waiting: null });
  assert.equal(document.querySelector('[data-testid="records-bandeja-waiting"]'), null);
});

test("Filtros Revisión offers the server's remaining stages and nothing about approval", async () => {
  const page = await mount();
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('[data-group="review"]'));
  const labels = [...document.querySelectorAll('[role="dialog"] label')].map((label) => label.textContent).filter((label) => label !== "Seleccionar todo");
  assert.deepEqual(labels, ["Faltan datos fiscales", "Listos para exportar", "Ya exportados", "Por revisar"]);
});

test("a saved view or address bar naming a stage the server no longer has reads as no stage filter", async () => {
  (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL(`http://localhost/biz?report=${encodeURIComponent(JSON.stringify({ filters: { review_stages: ["awaiting_approval", "exported"] } }))}&report_scope=synthetic-person:${fixtureId(3000)}`);
  const page = await mount();
  assert.ok(sentFilters(page).every((filters) => !filters.review_stages.includes("awaiting_approval" as never)), "no request carries the stale stage");
  assert.deepEqual(sentFilters(page)[0].review_stages, ["exported"]);
  assert.deepEqual(addressFilters().review_stages, ["exported"]);
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

test("canonical filters normalize legacy all families and keep one currency", () => {
  const filters = reportRequestSchema.parse({ filters: { currencies: ["USD"], record_families: ["sale", "purchase"] } }).filters;
  const draft = reportFiltersForUi(filters);
  assert.deepEqual(reportFiltersFromUi(filters, { ...draft, expense_type: ["02"] }, "gasto").record_families, ["purchase"]);
  assert.deepEqual(reportFiltersFromUi(filters, draft, "gasto").currencies, ["USD"]);
  assert.deepEqual(reportFiltersFromUi(filters, draft, "gasto").record_families, ["purchase"]);
  assert.equal(validPreviewAmount({ currency: "USD", min: "1", max: "" }), true);
  assert.deepEqual(emptyPreviewFilters("USD").amount, { currency: "USD", min: "", max: "" });
});

test("saved views persist only recipes, rename with versions, restore page one and delete", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { record_families: ["sale"] } }) });
  await page.click(document.querySelector('button[aria-label="Última página"]'));
  await page.settle(() => document.querySelector('[data-testid="records-pagination"]')?.getAttribute("data-page") === "3");
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


test("authoritative decimal text above the safe integer limit renders exactly beside unknown money in the selected currency", async () => {
  await mount({ large: true });
  const rows = [...document.querySelectorAll("tbody tr")];
  assert.equal(rows[0].querySelector('[data-col="monto"]')!.textContent, "9,007,199,254,740,993.01");
  assert.equal(rows[0].querySelector('[data-col="moneda"]')!.textContent, "RD$");
  assert.equal(rows[1].querySelector('[data-col="moneda"]')!.textContent, "RD$");
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
  const page = await mount({ legacy: true, initial: reportRequestSchema.parse({ schema_version: 1 }) });
  assert.equal(document.querySelector('[data-report-schema]')?.getAttribute('data-report-schema'), '1');
  assert.equal(document.querySelectorAll('tbody tr').length, 25);
  for (const card of document.querySelectorAll<HTMLButtonElement>('[data-overview-filter]')) assert.equal(card.disabled, true);
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).every((call) => (call.body as ReportRequest).schema_version === 1), true);
  assert.equal(document.querySelector('[data-testid="records-results-summary"]'), null);
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

test("a phone optional filter holds after its sheet closes, and back still undoes it", async () => {
  const page = await mount({ width: 390 });
  const before = sentFilters(page).length;
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('[role="dialog"] [data-group="attachment"]'));
  await page.click([...document.querySelectorAll<HTMLInputElement>('[role="dialog"] input[type="radio"]')].find((radio) => radio.parentElement?.textContent === "Sin documento"));
  await page.click(page.button("Aplicar"));
  await page.settle(() => document.querySelector('[role="dialog"]') === null && document.querySelector('[data-testid="records-count"]') !== null);
  await pause(200);
  assert.deepEqual(sentFilters(page).slice(before).map((filters) => filters.has_document), [false]);
  assert.equal(addressFilters().has_document, false);
  assert.match(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent ?? "", /Sin documento/);
  assert.equal(document.querySelector('[data-testid="records-results-summary"]'), null);
  await act(async () => window.history.back());
  await page.settle(() => sentFilters(page).at(-1)?.has_document === null);
  assert.deepEqual(sentFilters(page).at(-1)!.record_families, ["purchase"]);
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
  await mount({ edit: (records) => { Object.assign(records[0], { stage: "needs_fiscal_data", export_missing: "payment_method_missing", export_missing_several: false }); Object.assign(records[1], { family: "purchase", stage: "needs_fiscal_data", export_missing: "ncf_missing", export_missing_several: true }); } });
  const chip = (id: number) => document.querySelector(`[data-record-key="draft:${fixtureId(id)}"] td[data-col="estado"] [data-record-workflow="fiscal"]`)?.textContent;
  assert.equal(chip(1), "Falta la forma de pago");
  assert.equal(chip(2), "Faltan datos fiscales");
});

test("chosen purchase columns use the server's name, missing word and a dash for a sale", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, presentation: { ...recordedReportAnswer.presentation, hidden: ["funding", "payment_form"] } }) });
  const cell = (id: number, column: string) => document.querySelector(`[data-record-key="draft:${fixtureId(id)}"] td[data-col="${column}"]`);
  const headings = [...document.querySelectorAll("thead th")].map((node) => node.getAttribute("data-col"));
  assert.ok(!headings.includes("categoria") && headings.indexOf("tipo_gasto") === headings.indexOf("detalle") + 1, "Tipo de gasto sits where Categoría sat");
  assert.equal(document.querySelector('th[data-col="tipo_gasto"]')?.textContent, "Tipo de gasto");
  assert.equal(document.querySelector('th[data-col="forma_pago"]'), null, "Forma de pago starts hidden");
  assert.equal(cell(1, "tipo_gasto")?.textContent, "Falta");
  assert.equal(cell(3, "tipo_gasto")?.textContent, "Gastos por trabajos, suministros y servicios");
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  await page.click([...document.querySelectorAll('button[role="radio"]')].find((node) => node.textContent === "Columnas"));
  await page.click(document.querySelector('[data-column-setting="forma_pago"] label'));
  await page.settle(() => document.querySelector('th[data-col="forma_pago"]') !== null);
  assert.equal(document.querySelector('th[data-col="forma_pago"]')?.textContent, "Forma de pago");
  assert.equal(cell(1, "forma_pago")?.textContent, "Falta");
  assert.equal(cell(3, "forma_pago")?.textContent, "Efectivo");
  const request = restoreReportLocation(new URL(window.location.href).searchParams).request;
  assert.deepEqual(request.schema_version === 2 ? request.presentation?.hidden : null, ["funding"], "the chosen columns travel with the saved presentation");
  await page.click(document.querySelector('#records-type-venta'));
  await page.settle(() => cell(2, "tipo_gasto") !== null);
  assert.equal(cell(2, "tipo_gasto")?.querySelector(".sr-only")?.textContent, "No aplica");
  assert.equal(cell(2, "forma_pago")?.querySelector(".sr-only")?.textContent, "No aplica");
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

for (const family of ["purchase", "sale"] as const) test(`an empty ${family} search clears only the search`, async () => {
  const period = { kind: "custom", from_date: "2026-10-01", to_date: "2026-10-25" } as const;
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { record_families: [family], currencies: ["DOP"], period } }) });
  const search = document.querySelector<HTMLInputElement>('input[type="search"]')!;
  await page.type(search, "comercio inexistente");
  await page.settle(() => document.querySelector('[data-empty-kind]') !== null);
  const empty = document.querySelector('[data-empty-kind="no_results"]');
  assert.equal(empty?.querySelector("h3")?.textContent, "No hay resultados para esta búsqueda");
  assert.deepEqual([...empty!.querySelectorAll("button")].map((button) => button.textContent), ["Borrar búsqueda"]);
  await page.click(empty!.querySelector("button"));
  await page.settle(() => document.querySelectorAll("tbody tr").length === 25);
  const applied = sentFilters(page).at(-1)!;
  assert.equal(search.value, "");
  assert.equal(applied.q, "");
  assert.deepEqual(applied.record_families, [family]);
  assert.deepEqual(applied.currencies, ["DOP"]);
  assert.deepEqual(applied.period, period);
});

for (const family of ["purchase", "sale"] as const) test(`an empty ${family} filter offers a table clear that keeps the scope and search`, async () => {
  const period = { kind: "custom", from_date: "2026-10-01", to_date: "2026-10-25" } as const;
  const page = await mount({
    initial: reportRequestSchema.parse({ schema_version: 2, filters: { record_families: [family], currencies: ["USD"], period, q: "Proveedor" } }),
    edit: (records) => { for (const row of records) { row.currency = "USD"; row.recorded_currency = "USD"; } },
  });
  const before = aboveTable();
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('[data-group="document"]'));
  await page.click([...document.querySelectorAll<HTMLInputElement>('[role="dialog"] input[type="checkbox"]')].find((box) => box.parentElement?.textContent === "Nota de crédito"));
  await page.click(page.button("Aplicar"));
  await page.settle(() => document.querySelector('[data-empty-kind="filtered"]') !== null);
  const empty = document.querySelector('[data-empty-kind="filtered"]')!;
  assert.equal(empty.querySelector("h3")?.textContent, "No hay registros con estos filtros");
  assert.equal(empty.querySelector("p")?.textContent, "Prueba con otros filtros o limpia los actuales.");
  assert.equal(empty.querySelector("img")?.getAttribute("src"), "/brand/records-search.webp");
  assert.deepEqual([...empty.querySelectorAll("button")].map((button) => button.textContent), ["Limpiar filtros"]);
  assert.deepEqual(aboveTable(), before, "nothing above the table moved");
  assert.deepEqual(sentFilters(page).slice(-2).map((filters) => [filters.q, filters.document_kinds]), [["", ["credit_note"]], ["", []]]);
  await page.click(empty.querySelector("button"));
  await page.settle(() => document.querySelectorAll("tbody tr").length === 25);
  assert.deepEqual(aboveTable(), before);
  const applied = sentFilters(page).at(-1)!;
  assert.deepEqual(applied.document_kinds, []);
  assert.deepEqual(applied.record_families, [family]);
  assert.deepEqual(applied.currencies, ["USD"]);
  assert.deepEqual(applied.period, period);
  assert.equal(applied.q, "Proveedor");
});

for (const family of ["purchase", "sale"] as const) test(`empty ${family} selection has priority even with search and optional filters`, async () => {
  const initial = reportRequestSchema.parse({
    schema_version: 2,
    filters: { record_families: [family], currencies: ["USD"], q: "Proveedor", document_kinds: ["credit_note"], period: { kind: "latest_month" } },
  });
  const page = await mount({
    initial,
    edit: (records) => {
      for (const row of records) if (row.family !== family) { row.currency = "USD"; row.recorded_currency = "USD"; }
    },
    onAdd: () => assert.fail("an empty selection has no add action"),
    waitForAnswer: false,
  });
  const empty = () => document.querySelector('[data-testid="transacciones-records-empty"]');
  await page.settle(() => document.querySelector('[data-empty-kind]') !== null);
  assert.equal(empty()?.querySelector("h3")?.textContent, family === "purchase" ? "No hay compras en esta selección" : "No hay ventas en esta selección");
  assert.equal(empty()?.querySelector("img")?.getAttribute("src"), "/brand/records-document.webp");
  assert.equal(empty()?.querySelectorAll("button").length, 0);
  const probeFilters = sentFilters(page).slice(-2);
  assert.deepEqual(probeFilters.map((filters) => [filters.q, filters.document_kinds]), [["", ["credit_note"]], ["", []]]);
  for (const filters of probeFilters) {
    assert.deepEqual(filters.record_families, [family]);
    assert.deepEqual(filters.currencies, ["USD"]);
    assert.deepEqual(filters.period, { kind: "custom", from_date: "2026-10-01", to_date: "2026-10-31" });
  }
  assert.deepEqual(addressFilters(), initial.filters, "the probe does not change the URL");
});

for (const family of ["purchase", "sale"] as const) test(`empty ${family} results offer search clear when optional filters still match rows`, async () => {
  const period = { kind: "custom", from_date: "2026-10-01", to_date: "2026-10-25" } as const;
  const initial = reportRequestSchema.parse({ schema_version: 2, filters: { record_families: [family], currencies: ["DOP"], period, q: "comercio inexistente", document_kinds: ["credit_note"] } });
  const page = await mount({
    initial,
    edit: (records) => { records.find((row) => row.family === family && row.report_date === "2026-10-20")!.document_kind = "credit_note"; },
    waitForAnswer: false,
  });
  await page.settle(() => document.querySelector('[data-empty-kind]') !== null);
  const empty = document.querySelector('[data-empty-kind="no_results"]');
  assert.equal(empty?.querySelector("h3")?.textContent, "No hay resultados para esta búsqueda");
  assert.equal(empty?.querySelector("img")?.getAttribute("src"), "/brand/records-search.webp");
  assert.deepEqual([...empty!.querySelectorAll("button")].map((button) => button.textContent), ["Borrar búsqueda"]);
  const cleared = { ...initial.filters, q: "" };
  assert.deepEqual(sentFilters(page), [initial.filters, cleared], "one optional-only read proves this is a search empty");
  await page.click(empty!.querySelector("button"));
  await page.settle(() => document.querySelectorAll("tbody tr").length === 1);
  assert.deepEqual(sentFilters(page).at(-1), cleared);
  assert.deepEqual(addressFilters(), cleared);
});

test("a pending or failed empty-selection read leaves the table loading or retryable", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  let fail = true;
  const page = await mount({
    initial: reportRequestSchema.parse({ schema_version: 2, filters: { q: "comercio inexistente" } }),
    queryAnswer: async (request, answer) => {
      if (!request.filters.q && fail) {
        await gate;
        throw new Error("Unavailable");
      }
      return answer;
    },
    waitForAnswer: false,
  });
  try {
    await page.settle(() => sentFilters(page).some((filters) => !filters.q));
    assert.ok(document.querySelector('[data-testid="transacciones-loading"]'));
    assert.equal(document.querySelector('[data-empty-kind]'), null);
  } finally {
    release();
  }
  await page.settle(() => document.querySelector('[role="alert"]') !== null);
  assert.equal(document.querySelector('[data-empty-kind="no_results"]'), null);
  fail = false;
  await page.click(document.querySelector('[role="alert"] button'));
  await page.settle(() => document.querySelector('[data-empty-kind="no_results"] button')?.textContent === "Borrar búsqueda");
});

test("a refused empty-selection read clears report context and keeps the server reference", async () => {
  const page = await mount({
    initial: reportRequestSchema.parse({ schema_version: 2, filters: { q: "comercio inexistente", period: { kind: "latest_month" } } }),
    queryAnswer: (request, answer) => {
      if (!request.filters.q) throw Object.assign(new Error("Refused"), { status: 403, code: "permission_denied", requestId: "PROBE-REF" });
      return answer;
    },
    waitForAnswer: false,
  });
  await page.settle(() => document.querySelector('[role="alert"]') !== null);
  const alert = document.querySelector('[role="alert"]');
  assert.match(alert?.textContent ?? "", /PROBE-REF/);
  assert.equal(alert?.querySelector('[data-testid="error-reference"]')?.getAttribute("title"), "PROBE-REF");
  assert.equal(page.button("Actualizar"), undefined);
  assert.equal(page.button("Octubre de 2026"), undefined);
  assert.equal(document.querySelector('[data-empty-kind]'), null);
});

test("a late empty-selection read cannot replace the current tab's empty state", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({
    initial: reportRequestSchema.parse({ schema_version: 2, filters: { q: "comercio inexistente" } }),
    edit: (records) => { for (const row of records) if (row.family === "purchase") { row.currency = "USD"; row.recorded_currency = "USD"; } },
    queryAnswer: async (request, answer) => {
      if (!request.filters.q && request.filters.record_families[0] === "purchase") await gate;
      return answer;
    },
    waitForAnswer: false,
  });
  try {
    await page.settle(() => sentFilters(page).some((filters) => !filters.q && filters.record_families[0] === "purchase"));
    await page.click(document.querySelector("#records-type-venta"));
    await page.settle(() => document.querySelector('[data-empty-kind="no_results"] button')?.textContent === "Borrar búsqueda");
  } finally {
    await act(async () => release());
  }
  assert.equal(document.querySelector("#records-type-venta")?.getAttribute("aria-selected"), "true");
  assert.equal(document.querySelector('[data-empty-kind="no_results"] button')?.textContent, "Borrar búsqueda");
  assert.equal(document.querySelector('[data-testid="transacciones-records-empty"]'), null);
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

test("an old categories filter from a saved view or URL is dropped, never sent, and never hides rows without a pill", async () => {
  const stale = reportRequestSchema.parse({});
  assert.deepEqual(reportFiltersFromUi({ ...stale.filters, categories: ["transport"] }, reportFiltersForUi({ ...stale.filters, currencies: ["DOP"] }), "gasto").categories, []);
  (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL(`http://localhost/biz?report=${encodeURIComponent(JSON.stringify({ filters: { categories: ["transport"] } }))}&report_scope=synthetic-person:${fixtureId(3000)}`);
  const page = await mount();
  assert.ok(sentFilters(page).every((filters) => filters.categories.length === 0), "no request carries the stale filter");
  assert.equal(document.querySelectorAll("tbody tr").length, 25);
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent, "");
  assert.equal(document.querySelector("[data-empty-kind]"), null);
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

const pressed = () => [...document.querySelectorAll('[aria-label="Períodos rápidos"] button[aria-pressed="true"]')].map((node) => node.textContent);
const fields = () => [...document.querySelectorAll<HTMLInputElement>('[data-testid="range-picker"] input')].map((input) => input.value);

test("Registros opens its picker on the current period, on Personalizado only when no preset matches", async () => {
  // An open sheet spends its history entry with back() on a timer after unmount. Resetting the address before
  // that lands lets back() put the previous report's address in front of the next mount.
  const reopen = async () => {
    const spent = new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
    await cleanup();
    await act(async () => { await spent; });
    (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz");
  };
  const month = await mount({ width: 390, initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: "this_month" } } }) });
  await month.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  assert.deepEqual(pressed(), ["Este mes"]);
  assert.equal(fields()[0], "01/10/2026");
  await reopen();
  const latest = await mount({ width: 390, edit: (records) => { for (const row of records) if (row.report_date) row.report_date = "2026-08-14"; } });
  await latest.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  assert.deepEqual(pressed(), ["Personalizado"]);
  assert.deepEqual(fields(), ["01/08/2026", "31/08/2026"]);
  await reopen();
  const all = await mount({ width: 390, initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: "all" } } }) });
  await all.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  assert.deepEqual(pressed(), ["Todas las fechas"]);
  assert.deepEqual(fields(), ["", ""]);
});

test("at an hour when the UTC day and the Santo Domingo day differ, the picker opens on the month the page shows", async () => {
  setSystemTime(new Date("2026-11-01T01:00:00Z"));
  const localMonth = new Date().getMonth() + 1;
  const expected = ({ 10: ["01/10/2026", "31/10/2026"], 11: ["01/11/2026", "30/11/2026"] } as Record<number, string[]>)[localMonth];
  assert.ok(expected, "October 31 in Santo Domingo, November 1 in UTC");
  const page = await mount({ width: 390, initial: reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: "this_month" } } }) });
  await page.click(document.querySelector('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]'));
  assert.deepEqual(pressed(), ["Este mes"]);
  assert.deepEqual(fields(), expected);
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

const renderedColumnKeys = () => [...document.querySelectorAll("thead th")].map((node) => node.getAttribute("data-col"));
for (const language of ["es-419", "en"] as const) test(`server defaults show eight columns and all optional columns remain available in ${language}`, async () => {
  const page = await mount({ language });
  assert.deepEqual(renderedColumnKeys(), ["contraparte", "fecha", "monto", "moneda", "detalle", "estado", "notas", "comprobante"]);
  assert.ok(page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).every((call) => !Object.hasOwn(call.body as object, "presentation")), "fresh V1 and V2 requests leave defaults to the server");
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  for (const [key, label] of language === "en" ? [["tipo_gasto", "Expense type"], ["forma_pago", "Payment method"], ["cuenta", "Account"]] : [["tipo_gasto", "Tipo de gasto"], ["forma_pago", "Forma de pago"], ["cuenta", "Cuenta"]]) {
    const row = document.querySelector(`[data-column-setting="${key}"]`);
    assert.ok(row?.textContent?.includes(label));
    assert.equal(row?.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked, false);
  }
});

test("server layout changes render, saved views retain the effective layout, and Restore asks for fresh defaults", async () => {
  const chosen: typeof recordedReportAnswer.presentation = { ...recordedReportAnswer.presentation, order: ["counterparty", ...recordedReportAnswer.presentation.order.slice(1).reverse()], hidden: [], density: 40 as const };
  const page = await mount({ presentation: chosen });
  assert.deepEqual(renderedColumnKeys(), ["contraparte", "cuenta", "comprobante", "notas", "estado", "forma_pago", "tipo_gasto", "detalle", "moneda", "monto", "fecha"]);
  assert.equal(document.querySelector("table")?.getAttribute("data-density"), "compacto");
  await page.click(page.button("Vistas")); await page.click(page.button("Guardar vista"));
  await page.type(document.querySelector('input[maxlength="120"]')!, "Mi diseño"); await page.click(page.button("Guardar"));
  await page.settle(() => page.fixture.views.length === 1 && !document.querySelector('input[maxlength="120"]'));
  assert.deepEqual((page.fixture.views[0].recipe as { presentation: unknown }).presentation, chosen);
  const fresh = { ...recordedReportAnswer.presentation, hidden: ["attachment" as const, "funding" as const], density: 56 as const };
  page.fixture.controls.presentation = fresh;
  await page.click(document.querySelector('[data-testid="records-refresh"]'));
  await page.settle(() => !renderedColumnKeys().includes("comprobante"));
  await page.click(page.button("Vistas")); await page.click(page.button("Mi diseño"));
  await page.settle(() => renderedColumnKeys()[1] === "cuenta");
  assert.deepEqual((page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).at(-1)!.body as { presentation: unknown }).presentation, chosen);
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  await page.click(page.button("Restaurar valores iniciales"));
  await page.settle(() => !renderedColumnKeys().includes("comprobante") && document.querySelector("table")?.getAttribute("data-density") === "amplio");
  const restored = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).at(-1)!.body as object;
  assert.equal(Object.hasOwn(restored, "presentation"), false);
  assert.ok(renderedColumnKeys().includes("tipo_gasto") && renderedColumnKeys().includes("forma_pago"), "Restore uses the new server layout, not the preview fixture");
});

for (const outcome of ["ready", "failed"] as const) test(`Restore cannot save a stale custom layout while pending or ${outcome}`, async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, presentation: { ...recordedReportAnswer.presentation, hidden: [], density: 40 } }) });
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = (async (input, init) => {
    if (String(input).endsWith("/reports/query")) {
      await gate;
      if (outcome === "failed") return new Response("{}", { status: 503 });
    }
    return page.fixture.request(input, init);
  }) as typeof fetch;
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  await page.click(page.button("Restaurar valores iniciales"));
  await page.click(page.button("Vistas"));
  try {
    assert.equal(page.button("Guardar vista")?.disabled, true, "saving must await the server's restored layout");
  } finally { await act(async () => release()); }
  if (outcome === "failed") {
    await page.settle(() => document.querySelector('[role="alert"]') !== null);
    assert.equal(page.button("Guardar vista")?.disabled, true, "failed Restore has no new layout to save");
  } else {
    await page.settle(() => page.button("Guardar vista")?.disabled === false);
  }
  assert.equal(page.fixture.views.length, 0);
});


test("a fresh connected table waits for server columns and offers no layout before the answer", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ queryGate: gate, waitForAnswer: false });
  try {
    assert.equal(document.querySelector("th[data-col]"), null);
    assert.equal(document.querySelector('[data-testid="transacciones-view-options"]'), null);
    assert.equal(document.querySelector("[data-column-setting]"), null);
    await page.settle(() => document.querySelector('[data-testid="fullscreen-loading"]') !== null);
  } finally { await act(async () => release()); }
  await page.settle(() => document.querySelector('th[data-col="moneda"]') !== null);
});

const fiscalCard = () => document.querySelector<HTMLButtonElement>('[data-overview-filter="fiscal"]')!;
const fiscalCount = () => fiscalCard().querySelector(".font-display")?.textContent;
const fiscalRecords = (rows: ReportRecord[]) => rows.forEach((row, index) => { row.stage = index < 60 ? "needs_fiscal_data" : "ready_for_export"; });

test("Fiscal narrows all pages then restores mixed statuses while preserving search edits", async () => {
  const prior = ["needs_fiscal_data", "ready_for_export"];
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { review_stages: prior, currencies: ["DOP"], record_families: ["purchase"] } }), edit: fiscalRecords });
  assert.equal(fiscalCount(), "30");
  assert.equal(fiscalCard().getAttribute("aria-pressed"), "false");
  await page.click(fiscalCard());
  await page.settle(() => sentFilters(page).at(-1)?.review_stages.length === 1 && !fiscalCard().disabled);
  assert.deepEqual(sentFilters(page).at(-1)!.review_stages, ["needs_fiscal_data"]);
  assert.match(document.querySelector('[data-testid="records-count"]')!.textContent!, /30/);
  assert.equal(document.querySelectorAll("tbody tr").length, 25);
  await page.type(document.querySelector('input[type="search"]')!, "Proveedor 11");
  await page.settle(() => sentFilters(page).at(-1)?.q === "Proveedor 11" && !fiscalCard().disabled);
  await page.click(fiscalCard());
  await page.settle(() => sentFilters(page).at(-1)?.review_stages.length === 2);
  assert.deepEqual(sentFilters(page).at(-1)!.review_stages, prior);
  assert.equal(sentFilters(page).at(-1)!.q, "Proveedor 11");
  assert.deepEqual(sentFilters(page).at(-1)!.currencies, ["DOP"]);
  assert.deepEqual(sentFilters(page).at(-1)!.record_families, ["purchase"]);
});

test("Fiscal cannot replace an incompatible status filter with more rows", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { review_stages: ["ready_for_export"] } }), edit: fiscalRecords });
  assert.equal(fiscalCount(), "0");
  assert.equal(fiscalCard().disabled, true);
  const before = sentFilters(page).length;
  await page.click(fiscalCard());
  assert.equal(sentFilters(page).length, before);
});

test("clearing the status chip discards Fiscal's saved status selection", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { review_stages: ["needs_fiscal_data", "ready_for_export"] } }), edit: fiscalRecords });
  await page.click(fiscalCard());
  await page.settle(() => fiscalCard().getAttribute("aria-pressed") === "true" && !fiscalCard().disabled);
  await page.click(document.querySelector('button[aria-label="Quitar filtro Revisión"]'));
  await page.settle(() => sentFilters(page).at(-1)?.review_stages.length === 0 && !fiscalCard().disabled);
  await page.click(fiscalCard());
  await page.settle(() => fiscalCard().getAttribute("aria-pressed") === "true" && !fiscalCard().disabled);
  await page.click(fiscalCard());
  await page.settle(() => sentFilters(page).at(-1)?.review_stages.length === 0);
});

test("a failed filtered request hides the prior Fiscal count", async () => {
  const page = await mount({ edit: fiscalRecords });
  assert.equal(fiscalCount(), "30");
  page.fixture.controls.reportUnavailable = true;
  await page.type(document.querySelector('input[type="search"]')!, "no matches");
  await page.settle(() => document.querySelector('[role="alert"]') !== null);
  assert.notEqual(fiscalCount(), "30");
  assert.equal(fiscalCount(), "-sin dato");
  assert.equal(fiscalCard().disabled, true);
});

test("an active empty Fiscal result can be cleared without losing a new search", async () => {
  const page = await mount({ edit: fiscalRecords });
  await page.click(fiscalCard());
  await page.settle(() => fiscalCard().getAttribute("aria-pressed") === "true" && !fiscalCard().disabled);
  await page.type(document.querySelector('input[type="search"]')!, "no matches");
  await page.settle(() => fiscalCount() === "0");
  assert.equal(fiscalCard().disabled, false);
  const before = sentFilters(page).length;
  await page.click(fiscalCard());
  await page.settle(() => sentFilters(page).length > before);
  assert.deepEqual(sentFilters(page)[before].review_stages, []);
  assert.equal(sentFilters(page)[before].q, "no matches");
  assert.equal(addressFilters().q, "no matches");
});

test("history restoring the same Fiscal stage discards the old toggle snapshot", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { review_stages: ["needs_fiscal_data", "ready_for_export"] } }), edit: fiscalRecords });
  await page.click(fiscalCard());
  await page.settle(() => fiscalCard().getAttribute("aria-pressed") === "true" && !fiscalCard().disabled);
  const before = sentFilters(page).length;
  await act(async () => window.dispatchEvent(new PopStateEvent("popstate")));
  await page.settle(() => sentFilters(page).length > before && !fiscalCard().disabled);
  await page.click(fiscalCard());
  await page.settle(() => sentFilters(page).at(-1)?.review_stages.length === 0);
});

test("manual status edits replace the remembered Fiscal selection", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { review_stages: ["needs_fiscal_data", "needs_review"] } }), edit: fiscalRecords });
  await page.click(fiscalCard());
  await page.settle(() => fiscalCard().getAttribute("aria-pressed") === "true" && !fiscalCard().disabled);
  await page.click([...document.querySelectorAll("button")].find((button) => button.textContent?.startsWith("Filtros")));
  await page.click(document.querySelector('[data-group="review"]'));
  await page.click([...document.querySelectorAll<HTMLInputElement>('[role="dialog"] input[type="checkbox"]')].find((box) => box.parentElement?.textContent === "Listos para exportar"));
  await page.click(page.button("Aplicar"));
  await page.settle(() => sentFilters(page).at(-1)?.review_stages.includes("ready_for_export") === true && !fiscalCard().disabled);
  assert.equal(fiscalCard().getAttribute("aria-pressed"), "false");
  await page.click(fiscalCard());
  await page.settle(() => fiscalCard().getAttribute("aria-pressed") === "true" && !fiscalCard().disabled);
  await page.click(fiscalCard());
  await page.settle(() => sentFilters(page).at(-1)?.review_stages.length === 2);
  assert.deepEqual(sentFilters(page).at(-1)!.review_stages, ["needs_fiscal_data", "ready_for_export"]);
});

test("selecting a saved Fiscal view discards the prior status snapshot", async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { review_stages: ["needs_fiscal_data", "ready_for_export"] } }), edit: fiscalRecords });
  await page.click(fiscalCard());
  await page.settle(() => fiscalCard().getAttribute("aria-pressed") === "true" && !fiscalCard().disabled);
  await page.click(page.button("Vistas"));
  await page.click(page.button("Guardar vista"));
  await page.type(document.querySelector('input[maxlength="120"]')!, "Fiscales");
  await page.click(page.button("Guardar"));
  await page.settle(() => page.fixture.views.length === 1 && !document.querySelector('input[maxlength="120"]'));
  await page.click(page.button("Vistas"));
  await page.click(page.button("Fiscales"));
  await page.settle(() => !fiscalCard().disabled);
  await page.click(fiscalCard());
  await page.settle(() => sentFilters(page).at(-1)?.review_stages.length === 0);
});

const currencyCardCases = [
  { currency: "DOP", count: 31, fiscal: 7, total: "3456.78", totalMinor: 345678, last: "3426.78", values: [["itbis", "456.78", 45678], ["goods", "2000.00", 200000], ["services", "1000.00", 100000]], shown: ["DOP 3,456.78", "DOP 456.78", "DOP 2,000.00", "DOP 1,000.00"] },
  { currency: "USD", count: 27, fiscal: 4, total: "876.54", totalMinor: 87654, last: "850.54", values: [["itbis", "76.54", 7654], ["goods", "500.00", 50000], ["services", "300.00", 30000]], shown: ["USD 876.54", "USD 76.54", "USD 500.00", "USD 300.00"] },
] as const;
const shelfMoney = () => ["total", "itbis", "goods", "services"].map((metric) => document.querySelector(`[data-overview-card="${metric}"] .cuadrao-amount`)?.getAttribute("aria-label") ?? null);
function currencyCardAnswer(request: ReportRequest, answer: ReportAnswer): ReportAnswer {
  const value = currencyCardCases.find(({ currency }) => request.filters.currencies.length === 1 && request.filters.currencies[0] === currency);
  if (!value) return answer;
  const count = request.filters.q === "absent" ? 0 : value.count;
  const family = request.filters.record_families[0];
  const kind = family === "sale" ? "income" : "expense";
  const row = createBusinessReportHttpFixture().records[0];
  return { ...answer, matching_count: count, page_count: count ? 2 : 0,
    items: count ? Array.from({ length: request.page === 1 ? 25 : count - 25 }, (_, index) => {
      const position = (request.page - 1) * 25 + index;
      return { ...row, row_id: `draft:${fixtureId(200 + position)}`, draft_id: fixtureId(200 + position), linked_activity_ids: [], report_date: "2026-10-20", family, money_kind: kind, counterparty: `Proveedor ${position + 1}`, counterparty_key: "101001577", currency: value.currency, gross_amount: position === count - 1 ? value.last : "1.00", stage: position < value.fiscal ? "needs_fiscal_data" : "ready_for_export", funding_key: "cash", fiscal_classification: "B01", dgii_606: { expense_type: { code: "02", label: "Suministros" }, payment_form: null } };
    }) : [],
    totals: count ? [{ currency: value.currency, kind, basis: "document_family_amount", matching_count: count, complete: true, unknown_count: 0, unsupported_count: 0, amount: value.total, known_amount: value.total, amount_minor: value.totalMinor, known_amount_minor: value.totalMinor }] : [],
    fiscal_totals: count ? value.values.filter(([basis]) => family === "purchase" || basis === "itbis").map(([basis, amount, minor]) => ({ currency: value.currency, kind, basis, applicable_count: count, populated_count: count, complete: true, unknown_count: 0, unsupported_count: 0, amount, known_amount: amount, amount_minor: minor, known_amount_minor: minor })) : [],
    overview: { needs_review: 0, needs_fiscal_data: count ? value.fiscal : 0, ready_for_export: count ? count - value.fiscal : 0 },
  };
}

for (const family of ["purchase", "sale"] as const) for (const sample of currencyCardCases) test(`${family} ${sample.currency} keeps static cards and table together across pages and Clear`, async () => {
  const initial = reportRequestSchema.parse({ schema_version: 2, filters: { q: "Proveedor", period: { kind: "all" }, record_families: [family], has_document: true, counterparties: ["101001577"], expense_types: ["02"], funding_sources: ["cash"], document_kinds: ["unknown"], fiscal_classifications: ["B01"] } });
  const page = await mount({ initial, queryAnswer: currencyCardAnswer });
  await page.click(document.querySelector('button[aria-label^="Moneda:"]'));
  await page.click(page.button(sample.currency));
  await page.settle(() => fiscalCount() === String(sample.fiscal));
  assert.deepEqual(sentFilters(page).at(-1), { ...initial.filters, currencies: [sample.currency] });
  assert.deepEqual(shelfMoney(), family === "purchase" ? [...sample.shown] : [sample.shown[0], sample.shown[1], null, null]);
  assert.equal(document.querySelector('[data-overview-card="quantity"] .font-display')?.textContent, String(sample.count));
  assert.equal(document.querySelectorAll("tbody tr").length, 25);
  assert.ok([...document.querySelectorAll('tbody td[data-col="detalle"]')].every((cell) => cell.textContent === (family === "sale" ? "Venta" : "Compra")));
  assert.equal(document.querySelector('[data-overview-card="total"] button'), null);
  assert.equal(document.querySelector('[data-testid="records-results-summary"]'), null);
  assert.deepEqual([...document.querySelectorAll('tbody td[data-col="monto"]')].map((cell) => cell.textContent), Array(25).fill("1.00"));
  await page.click(document.querySelector('button[aria-label="Última página"]'));
  await page.settle(() => document.querySelector('[data-testid="records-pagination"]')?.getAttribute("data-page") === "2");
  assert.equal(document.querySelectorAll("tbody tr").length, sample.count - 25);
  assert.deepEqual(shelfMoney(), family === "purchase" ? [...sample.shown] : [sample.shown[0], sample.shown[1], null, null]);
  assert.equal(document.querySelector('[data-overview-card="quantity"] .font-display')?.textContent, String(sample.count));
  assert.equal(fiscalCount(), String(sample.fiscal));
  assert.equal(document.querySelector('button[aria-label="Quitar filtro Moneda"]'), null);
  await page.click(page.button("Limpiar filtros"));
  await page.settle(() => sentFilters(page).at(-1)?.q === "Proveedor" && sentFilters(page).at(-1)?.has_document === null && document.querySelector('[data-testid="records-pagination"]')?.getAttribute("data-page") === "1");
  assert.deepEqual(sentFilters(page).at(-1)!.currencies, [sample.currency]);
  assert.deepEqual(sentFilters(page).at(-1)!.record_families, [family]);
});

test("a currency-filtered six-card answer clears old figures while loading and shows an empty result honestly", async () => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, filters: { currencies: ["DOP"], record_families: ["purchase"] } }), queryAnswer: async (request, answer) => { if (request.filters.q === "absent") await gate; return currencyCardAnswer(request, answer); } });
  assert.deepEqual(shelfMoney(), ["DOP 3,456.78", "DOP 456.78", "DOP 2,000.00", "DOP 1,000.00"]);
  try {
    await page.type(document.querySelector('input[type="search"]')!, "absent");
    assert.equal(document.querySelector('[data-testid="records-overview-preview"]')?.getAttribute("aria-busy"), "true");
    assert.deepEqual(shelfMoney(), [null, null, null, null]);
    assert.equal(document.querySelector('[data-overview-card="quantity"] .font-display')?.textContent, "");
    assert.equal(fiscalCount(), "");
  } finally { await act(async () => release()); }
  await page.settle(() => document.querySelector('[data-empty-kind="no_results"]') !== null);
  assert.deepEqual(shelfMoney(), [null, null, null, null]);
  for (const metric of ["total", "itbis", "goods", "services"]) assert.match(document.querySelector(`[data-overview-card="${metric}"]`)!.textContent!, /-sin dato/);
  assert.equal(document.querySelector('[data-overview-card="quantity"] .font-display')?.textContent, "0");
  assert.equal(fiscalCount(), "0");
  assert.equal(fiscalCard().disabled, true);
});

test("phone Registros keeps its export button and existing report handler", async () => {
  const page = await mount({ width: 390 });
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => page.downloads.length === 1);
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/reports/export")).length, 1);
});


test("the first report request uses the server Registros default even when the Business currency differs", async () => {
  const page = await mount({ defaultCurrency: "USD", edit: (rows) => rows.forEach((row) => { row.currency = "USD"; }) });
  assert.equal(page.context.records.workspace!.currency, "CAD");
  assert.ok(sentFilters(page).length > 0);
  assert.ok(sentFilters(page).every((filters) => JSON.stringify(filters.currencies) === '["USD"]'));
  assert.ok(document.querySelector('button[aria-label="Moneda: USD"]'));
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => page.downloads.length === 1);
  const exported = page.fixture.calls.find((call) => call.path.endsWith("/reports/export"))!.body as { report: ReportRequest };
  assert.deepEqual(exported.report.filters.currencies, ["USD"]);
});

for (const currencies of [[], ["DOP", "USD"], ["CAD"]]) test(`entry replaces unsupported currency scope ${JSON.stringify(currencies)} with the server default and clears bounds`, async () => {
  const page = await mount({ defaultCurrency: "USD", initial: reportRequestSchema.parse({ filters: { currencies, amount_min: "100", amount_max: "200" } }) });
  assert.ok(sentFilters(page).every((filters) => filters.currencies.length === 1 && filters.currencies[0] === "USD" && filters.amount_min === null && filters.amount_max === null));
});

test("a valid URL currency wins over the server default and keeps its explicit amount bounds", async () => {
  const report = reportRequestSchema.parse({ schema_version: 2, filters: { currencies: ["EUR"], amount_min: "10", amount_max: "200" } });
  const params = new URLSearchParams({ report: JSON.stringify(report), report_scope: `synthetic-person:${fixtureId(3000)}` });
  (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL(`http://localhost/biz?${params}`);
  const page = await mount({ defaultCurrency: "USD" });
  assert.ok(sentFilters(page).every((filters) => JSON.stringify(filters.currencies) === '["EUR"]'));
  assert.deepEqual(sentFilters(page)[0], report.filters);
  assert.deepEqual(addressFilters(), report.filters);
});

test("the connected entry waits for the current grant workspace before sending any report query", async () => {
  const page = await mount({ topLevel: true, defaultCurrency: "USD", grantId: fixtureId(3100), workspaceGrant: fixtureId(3101), waitForAnswer: false });
  await pause(30);
  assert.equal(sentFilters(page).length, 0);
  page.context.records.workspaceGrant = fixtureId(3100);
  await page.rerender();
  await page.settle(() => sentFilters(page).length > 0);
  assert.ok(sentFilters(page).every((filters) => JSON.stringify(filters.currencies) === '["USD"]'));
});


for (const currencies of [["EUR"], []]) test(`applying a view keeps a supported singleton or uses the server default for ${JSON.stringify(currencies)}`, async () => {
  const page = await mount({ defaultCurrency: "USD", viewRecipe: reportRequestSchema.parse({ schema_version: 2, filters: { currencies, amount_min: "10", amount_max: "200" } }) });
  const before = sentFilters(page).length;
  await page.click(page.button("Vistas"));
  await page.click(page.button("Moneda guardada"));
  await page.settle(() => sentFilters(page).length > before);
  const filters = sentFilters(page)[before];
  assert.deepEqual(filters.currencies, [currencies[0] ?? "USD"]);
  assert.equal(filters.amount_min, currencies.length ? "10" : null);
  assert.equal(filters.amount_max, currencies.length ? "200" : null);
  assert.deepEqual((page.fixture.views[0].recipe as { filters: { currencies: string[] } }).filters.currencies, currencies, "applying does not migrate the stored recipe");
});

test("history restoration sends one currency and keeps the URL currency's amount bounds", async () => {
  const page = await mount({ defaultCurrency: "USD" });
  const restored = reportRequestSchema.parse({ schema_version: 2, filters: { currencies: ["EUR"], amount_min: "10" } });
  const params = new URLSearchParams({ report: JSON.stringify(restored), report_scope: `synthetic-person:${fixtureId(3000)}` });
  const before = sentFilters(page).length;
  await act(async () => { window.history.pushState(null, "", `?${params}`); window.dispatchEvent(new PopStateEvent("popstate")); });
  await page.settle(() => sentFilters(page).length > before);
  assert.deepEqual(sentFilters(page)[before], restored.filters);
  const unrestricted = { ...restored, filters: { ...restored.filters, currencies: [] } };
  params.set("report", JSON.stringify(unrestricted));
  await act(async () => { window.history.pushState(null, "", `?${params}`); window.dispatchEvent(new PopStateEvent("popstate")); });
  await page.settle(() => sentFilters(page).at(-1)?.currencies[0] === "USD");
  assert.equal(sentFilters(page).at(-1)!.amount_min, null);
  assert.ok(sentFilters(page).every((filters) => filters.currencies.length === 1));
});


for (const workspaceFailure of ["error", "missing_default"] as const) test(`a settled workspace ${workspaceFailure} shows retry and recovers before the first report query`, async () => {
  const page = await mount({ topLevel: true, workspaceFailure, waitForAnswer: false });
  await page.settle(() => page.button("Reintentar") !== undefined);
  assert.equal(sentFilters(page).length, 0);
  if (workspaceFailure === "error") assert.match(document.body.textContent!, /SYNTHETIC-REF/);
  await page.click(page.button("Reintentar"));
  await page.settle(() => sentFilters(page).length > 0);
  assert.equal(page.reloads(), 1);
  assert.ok(sentFilters(page).every((filters) => JSON.stringify(filters.currencies) === '["DOP"]'));
});

test("a refused workspace shows its reference and no retry or report query", async () => {
  const page = await mount({ topLevel: true, workspaceFailure: "refused", waitForAnswer: false });
  await page.settle(() => document.querySelector('[data-empty-kind="error"]') !== null);
  assert.match(document.body.textContent!, /SYNTHETIC-REF/);
  assert.equal(page.button("Reintentar"), undefined);
  assert.equal(sentFilters(page).length, 0);
});


for (const width of [1440, 390]) test(`type tabs share filters and clearing on Ventas preserves USD and period at ${width}px`, async () => {
  const period = { kind: "custom", from_date: "2026-10-01", to_date: "2026-10-25" } as const;
  const page = await mount({ width, defaultCurrency: "USD", initial: reportRequestSchema.parse({ schema_version: 2, filters: { currencies: ["USD"], period, has_document: false, amount_min: "10" } }) });
  assert.equal(document.querySelector('#records-type-gasto')?.getAttribute("aria-selected"), "true");
  const beforeSale = sentFilters(page).length;
  await page.click(document.querySelector('#records-type-venta'));
  await page.settle(() => sentFilters(page).length > beforeSale);
  const sale = sentFilters(page)[beforeSale];
  assert.deepEqual(sale.record_families, ["sale"]);
  assert.equal(sale.has_document, false);
  assert.equal(sale.amount_min, "10");
  const beforeClear = sentFilters(page).length;
  await page.click(page.button("Limpiar filtros"));
  await page.settle(() => sentFilters(page).length > beforeClear);
  const filters = sentFilters(page)[beforeClear];
  assert.equal(filters.has_document, null);
  assert.deepEqual(filters.record_families, ["sale"]);
  assert.deepEqual(filters.currencies, ["USD"]);
  assert.deepEqual(filters.period, period);
  assert.equal(filters.amount_min, null);
  assert.equal(document.querySelector('#records-type-venta')?.getAttribute("aria-selected"), "true");
  assert.equal([...document.querySelectorAll('button')].find(node => node.textContent?.startsWith("Filtros"))?.textContent, "Filtros");
  await page.click(document.querySelector('#records-type-gasto'));
  await page.settle(() => sentFilters(page).at(-1)?.record_families[0] === "purchase");
  assert.equal(sentFilters(page).at(-1)?.has_document, null);
});
