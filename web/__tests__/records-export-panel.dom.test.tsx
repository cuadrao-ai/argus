import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { I18nextProvider } from "react-i18next";
import type { ReportRecord, ReportRequest } from "@/lib/business-reports-api";
import { mountConnectedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { translate } from "./support/i18n-instance";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); (await import("@/components/business-app/foundation/toasts")).clearToasts(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

type Page = Awaited<ReturnType<typeof mount>>;
type ExportBody = { report: ReportRequest; mode: string; columns?: string[]; currencies?: string; format: string };
const panel = () => document.querySelector<HTMLElement>('[data-testid="records-export-panel"]');
const downloadButton = () => document.querySelector<HTMLButtonElement>('[data-testid="records-export-download"]');
const previews = (page: Page) => page.fixture.calls.filter((call) => call.path.endsWith("/reports/export/preview"));
const exports = (page: Page) => page.fixture.calls.filter((call) => call.path.endsWith("/reports/export")).map((call) => call.body as ExportBody);
const dialogText = () => document.querySelector('[role="dialog"]')?.textContent ?? "";

async function open(page: Page) {
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => /^Exportar \d+ registros?$/.test(downloadButton()?.textContent?.trim() ?? "") || dialogText().includes("No hay registros"));
}

/** Purchases with a fiscal verdict: four complete pesos lines, three pending, and two in other currencies. */
function fiscalBooks(rows: ReportRecord[]) {
  const purchases = rows.filter((row) => row.family === "purchase");
  purchases.slice(0, 4).forEach((row) => { row.stage = "ready_for_export"; row.fiscal_data = "complete"; });
  purchases.slice(4, 7).forEach((row) => { row.stage = "needs_fiscal_data"; row.fiscal_data = "missing"; });
  purchases.slice(7, 9).forEach((row, index) => { row.stage = "needs_fiscal_data"; row.fiscal_data = "missing"; row.currency = index ? "EUR" : "USD"; });
}

test("Lo que ves exports the table's request, its columns and every currency, with the server's count", async () => {
  const page = await mount({ edit: fiscalBooks });
  await page.type(document.querySelector('input[type="search"]')!, "proveedor");
  await page.settle(() => document.querySelector('[data-testid="records-count"]')?.textContent?.includes("de 61") ?? false);
  await open(page);
  assert.match(dialogText(), /Exportar compras/);
  assert.match(dialogText(), /1 filtro · 63 registros · 3 monedas/);
  assert.equal(downloadButton()!.textContent!.trim(), "Exportar 63 registros");
  assert.match(dialogText(), /Columnas de tu tabla \(6\)/);
  const [sent] = previews(page).map((call) => call.body as { report: ReportRequest }).slice(-1);
  assert.equal(sent.report.filters.q, "proveedor");
  assert.deepEqual(sent.report.filters.currencies, ["DOP"]);
  await page.click(page.button("Solo DOP"));
  await page.settle(() => downloadButton()!.textContent!.trim() === "Exportar 61 registros");
  await page.click(page.button("Todas las monedas"));
  await page.click(page.button("CSV"));
  await page.click(downloadButton());
  await page.settle(() => page.downloads.length === 1);
  const [body] = exports(page);
  assert.deepEqual({ mode: body.mode, columns: body.columns, currencies: body.currencies, format: body.format }, { mode: "table", columns: ["counterparty", "date", "gross_amount", "stage", "note", "attachment"], currencies: "all", format: "csv" });
  assert.equal(body.report.filters.q, "proveedor");
  assert.equal(panel(), null, "the panel closes once the file is saved");
});

test("Editar chooses columns in the table's order inside the same panel, with Contraparte and Moneda locked", async () => {
  const page = await mount();
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-edit-columns"]'));
  await page.settle(() => document.querySelector('[data-testid="records-export-columns"]') !== null);
  assert.equal(document.querySelectorAll('[role="dialog"]').length, 1, "a sub-view, not a second modal");
  const boxes = () => [...document.querySelectorAll<HTMLInputElement>('[data-testid="records-export-columns"] input[type="checkbox"]')];
  const labels = () => [...document.querySelectorAll('[data-testid="records-export-columns"] label')].map((label) => label.textContent);
  assert.deepEqual(labels(), ["Contraparte", "NCF", "Fecha", "Monto", "Moneda", "ITBIS", "Estado", "Notas", "Adjunto", "Tipo de gasto", "Forma de pago", "Cuenta"]);
  assert.equal(boxes()[0].disabled, true);
  assert.equal(boxes()[4].checked && boxes()[4].disabled, true, "Moneda is locked on with every currency");
  await act(async () => boxes()[1].click());
  await act(async () => boxes()[7].click());
  await page.click(page.button("Listo"));
  await page.settle(() => /Columnas personalizadas \(6\)/.test(dialogText()));
  await page.click(document.querySelector('[data-testid="records-export-edit-columns"]'));
  await page.click(page.button("Usar las de mi tabla"));
  await page.click(page.button("Exportar compras"));
  await page.settle(() => /Columnas de tu tabla \(6\)/.test(dialogText()));
  await page.click(document.querySelector('[data-testid="records-export-edit-columns"]'));
  await act(async () => boxes()[1].click());
  await page.click(page.button("Listo"));
  await page.click(downloadButton());
  await page.settle(() => page.downloads.length === 1);
  assert.deepEqual(exports(page)[0].columns, ["counterparty", "fiscal_number", "date", "gross_amount", "stage", "note", "attachment"]);
});

test("Formato DGII counts only tab and period, shows the server's notices and Revisar applies the fiscal filter", async () => {
  const page = await mount({ edit: fiscalBooks });
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
  await page.settle(() => downloadButton()!.textContent!.trim() === "Exportar 4 registros");
  assert.match(dialogText(), /La DGII define las columnas\. Solo en pesos\./);
  assert.match(dialogText(), /todas las compras listas/);
  assert.match(dialogText(), /3 compras tienen datos fiscales pendientes y no se incluyen\./);
  assert.match(dialogText(), /2 compras en EUR y USD necesitan tasa y no se incluyen\./);
  assert.equal(document.querySelector('[data-testid="records-export-currencies"]'), null);
  assert.equal(document.querySelector('[data-testid="records-export-edit-columns"]'), null);
  await page.click(downloadButton());
  await page.settle(() => page.downloads.length === 1);
  assert.deepEqual(Object.keys(exports(page)[0]).sort(), ["format", "mode", "report"]);
  assert.equal(exports(page)[0].mode, "dgii");
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
  await page.settle(() => page.button("Revisar") !== undefined);
  const queries = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  await page.click(page.button("Revisar"));
  await page.settle(() => page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length > queries);
  assert.equal(panel(), null);
  const last = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).at(-1)!.body as ReportRequest;
  assert.equal(last.filters.fiscal_data, "missing");
  assert.equal(document.querySelector('[data-overview-filter="fiscal"]')?.getAttribute("aria-pressed"), "true");
});

test("no records disables the export and sends no request", async () => {
  const page = await mount({ edit: (rows) => rows.forEach((row) => { row.family = "sale"; }) });
  await open(page);
  assert.match(dialogText(), /No hay registros para exportar en esta selección\./);
  assert.equal(downloadButton()!.disabled, true);
  await page.click(downloadButton());
  assert.equal(exports(page).length, 0);
});

test("a double click prepares one file, and closing while preparing cancels it", async () => {
  const page = await mount();
  const live = globalThis.fetch;
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/reports/export")) await held;
    return live(input, init);
  }) as typeof fetch;
  await open(page);
  await act(async () => { downloadButton()!.click(); downloadButton()!.click(); });
  await page.settle(() => downloadButton()!.textContent!.trim() === "Preparando…");
  assert.equal(downloadButton()!.disabled, true);
  await page.click(downloadButton());
  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  release();
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/reports/export")).length, 1);
  assert.equal(page.downloads.length, 0, "no download arrives after the panel closed");
});

test("Descargar de nuevo saves the same file without another request", async () => {
  const page = await mount();
  const { createRoot } = await import("react-dom/client");
  const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
  const host = document.body.appendChild(document.createElement("div"));
  const toasts = createRoot(host);
  const i18n = await translate("es-419");
  await act(async () => toasts.render(<I18nextProvider i18n={i18n}><ToastViewport /></I18nextProvider>));
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => page.downloads.length === 1);
  assert.match(document.body.textContent!, /Listo\. Revisa tus descargas/);
  await page.click(page.button("Descargar de nuevo"));
  assert.equal(page.downloads.length, 2);
  assert.equal(page.downloads[1], page.downloads[0]);
  assert.equal(exports(page).length, 1);
  await act(async () => toasts.unmount());
});

test("a failed file keeps the choices and offers Reintentar with the server's reference", async () => {
  const page = await mount();
  page.fixture.controls.exportFails = true;
  await open(page);
  await page.click(page.button("CSV"));
  await page.click(downloadButton());
  await page.settle(() => document.querySelector('[role="dialog"] [role="alert"]') !== null);
  assert.match(document.querySelector('[role="dialog"] [role="alert"]')!.textContent!, /No pudimos preparar el archivo\. Inténtalo de nuevo\./);
  page.fixture.controls.exportFails = false;
  await page.click(page.button("Reintentar"));
  await page.settle(() => page.downloads.length === 1);
  assert.deepEqual(exports(page).map((body) => body.format), ["csv", "csv"]);
});
