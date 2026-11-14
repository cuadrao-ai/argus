import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { I18nextProvider } from "react-i18next";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import DgiiRegistryTag from "@/components/business-app/DgiiRegistryTag";
import { reportFiltersSchema, reportRequestSchema, type ReportRecord, type ReportRequest } from "@/lib/business-reports-api";
import { openRecordsExport, useRecordsExportRequested } from "@/components/business-app/transacciones/records-export-request";
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
const noticeSentence = (notice: Element | null) => {
  const paragraph = notice?.querySelector("p")?.cloneNode(true);
  if (!(paragraph instanceof HTMLElement)) return undefined;
  paragraph.querySelector("button")?.remove();
  return paragraph.textContent?.trim();
};
const summary = () => document.querySelector('[data-testid="records-export-summary"]')?.textContent;

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
  assert.match(dialogText(), /Columnas de tu tabla \(8\)/);
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
  assert.deepEqual({ mode: body.mode, columns: body.columns, currencies: body.currencies, format: body.format }, { mode: "table", columns: ["counterparty", "date", "net_amount", "itbis_amount", "gross_amount", "currency", "stage", "note", "attachment"], currencies: "all", format: "csv" });
  assert.equal(body.report.filters.q, "proveedor");
  assert.equal(panel(), null, "the panel closes once the file is saved");
});

test("on desktop Exportar is a centered dialog with only the agreed pieces, never the side drawer", async () => {
  const page = await mount();
  await open(page);
  const dialog = document.querySelector('[data-testid="records-export-dialog"]')!;
  assert.equal(dialog.getAttribute("role"), "dialog");
  assert.equal(dialog.getAttribute("aria-modal"), "true");
  assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
  const text = dialog.textContent!;
  for (const gone of ["Qué exportar", "Monedas", "Revisando"]) assert.equal(text.includes(gone), false, gone);
  assert.equal(dialog.querySelectorAll("h3").length, 0, "no section labels");
  assert.equal(document.querySelectorAll('[data-testid="records-export-summary"]').length, 1);
  await page.click(document.querySelector('[data-testid="records-export-edit-columns"]'));
  assert.equal(document.querySelectorAll('[role="dialog"]').length, 1, "the column choice stays in the same dialog");
  assert.match(document.querySelector('[data-testid="records-export-back"]')!.textContent!, /Exportar compras/);
  await page.click(document.querySelector('[data-testid="records-export-back"]'));
  assert.ok(document.querySelector('[data-testid="records-export-mode-table"]'));
});

test("on a phone Exportar is the shared bottom sheet", async () => {
  const page = await mount({ width: 390 });
  await open(page);
  assert.equal(document.querySelector('[data-testid="records-export-dialog"]'), null);
  assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
  assert.ok(document.querySelector('[role="dialog"][data-snap]')?.querySelector('[data-testid="records-export-panel"]'));
});

test("Exportar registros from search opens Registros and its export dialog, not the period ZIP", async () => {
  const opened: unknown[] = [];
  let requested = false;
  const { createRoot } = await import("react-dom/client");
  const probe = createRoot(document.body.appendChild(document.createElement("div")));
  function Probe() { requested = useRecordsExportRequested(); return null; }
  await act(async () => probe.render(<Probe />));
  const page = await mount();
  await act(async () => openRecordsExport((panel) => opened.push(panel)));
  assert.deepEqual(opened, [{ kind: "transactions" }]);
  await page.settle(() => /^Exportar \d+ registros?$/.test(downloadButton()?.textContent?.trim() ?? ""));
  assert.ok(document.querySelector('[data-testid="records-export-dialog"]'));
  assert.equal(requested, false, "the request is used once");
  await act(async () => probe.unmount());
  // The workspace hands search this action, never the period ZIP panel.
  const workspace = readFileSync(new URL("../components/business-app/BusinessWorkspace.tsx", import.meta.url), "utf8");
  assert.match(workspace, /useBusinessSearch\(\{[\s\S]*?openExport: exportRegistros,/);
  assert.match(workspace, /const exportRegistros = useCallback\(\(\) => openRecordsExport\(openPanel\)/);
});

test("Editar chooses columns in the table's order inside the same panel, with Contraparte and Moneda locked", async () => {
  const page = await mount();
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-edit-columns"]'));
  await page.settle(() => document.querySelector('[data-testid="records-export-columns"]') !== null);
  assert.equal(document.querySelectorAll('[role="dialog"]').length, 1, "a sub-view, not a second modal");
  const boxes = () => [...document.querySelectorAll<HTMLInputElement>('[data-testid="records-export-columns"] input[type="checkbox"]')];
  const labels = () => [...document.querySelectorAll('[data-testid="records-export-columns"] label')].map((label) => label.textContent);
  assert.deepEqual(labels(), ["Contraparte", "NCF", "Fecha", "Monto sin ITBIS", "ITBIS", "Total", "Moneda", "Estado", "Notas", "Adjunto", "Tipo de gasto", "Forma de pago", "Cuenta"]);
  assert.equal(boxes()[0].disabled, true);
  assert.equal(boxes()[6].checked && boxes()[6].disabled, true, "Moneda is locked on with every currency");
  await act(async () => boxes()[1].click());
  await act(async () => boxes()[8].click());
  await page.click(page.button("Listo"));
  await page.settle(() => /Columnas personalizadas \(8\)/.test(dialogText()));
  await page.click(document.querySelector('[data-testid="records-export-edit-columns"]'));
  await page.click(page.button("Usar las de mi tabla"));
  await page.click(page.button("Exportar compras"));
  await page.settle(() => /Columnas de tu tabla \(8\)/.test(dialogText()));
  await page.click(document.querySelector('[data-testid="records-export-edit-columns"]'));
  await act(async () => boxes()[1].click());
  await page.click(page.button("Listo"));
  await page.click(downloadButton());
  await page.settle(() => page.downloads.length === 1);
  assert.deepEqual(exports(page)[0].columns, ["counterparty", "fiscal_number", "date", "net_amount", "itbis_amount", "gross_amount", "currency", "stage", "note", "attachment"]);
});

test("Formato DGII counts only tab and period, shows the server's notices and Revisar applies the fiscal filter", async () => {
  const page = await mount({ edit: fiscalBooks });
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
  await page.settle(() => downloadButton()!.textContent!.trim() === "Exportar 4 registros");
  assert.match(dialogText(), /La DGII define las columnas\. Solo en pesos\./);
  assert.match(summary()!, /^Octubre de 2026 · 4 listas · 5 pendientes$/, "the summary counts what the notices hold back");
  assert.match(dialogText(), /3 compras tienen datos fiscales pendientes y no se incluyen\./);
  assert.match(dialogText(), /2 compras en EUR y USD necesitan tasa y no se incluyen\./);
  const notices = document.querySelector('[data-testid="records-export-notices"]')!;
  assert.ok(document.querySelector('[data-testid="records-export-mode-dgii"]')!.contains(notices));
  assert.equal(notices.children.length, 2);
  assert.equal(notices.querySelectorAll(".lucide-circle-minus").length, 2);
  assert.equal(page.button("Revisar")!.closest("label"), null);
  assert.equal(document.querySelector('[data-testid="records-export-dgii"]')!.textContent, "La DGII define las columnas. Solo en pesos.");
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

test("Formato DGII says every record is ready only when the server holds none back", async () => {
  const page = await mount({ edit: (rows) => rows.filter((row) => row.family === "purchase").forEach((row) => { row.stage = "ready_for_export"; row.fiscal_data = "complete"; row.currency = "DOP"; }) });
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
  await page.settle(() => downloadButton()!.textContent!.trim() === "Exportar 63 registros");
  assert.match(summary()!, /^Octubre de 2026 · todas las compras listas · 63 registros$/);
  assert.doesNotMatch(dialogText(), /no se incluyen?\./);
  assert.equal(document.querySelector('[data-testid="records-export-notices"]'), null);
});

test("before the server counts, the button names no number and cannot start", async () => {
  const page = await mount();
  const live = globalThis.fetch;
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/reports/export/preview")) await held;
    return live(input, init);
  }) as typeof fetch;
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => downloadButton() !== null);
  assert.deepEqual([downloadButton()!.textContent!.trim(), downloadButton()!.disabled], ["Exportar", true]);
  release();
  await page.settle(() => downloadButton()!.textContent!.trim() === "Exportar 63 registros");
});

test("Revisar from the DGII notice leaves only tab, period, the form's currency and Faltan datos, so the list holds the notice's count", async () => {
  const initial = reportRequestSchema.parse({ schema_version: 2, filters: { record_families: ["purchase"], currencies: ["DOP"], counterparties: ["101001577"], q: "proveedor", has_document: true } });
  const page = await mount({ edit: fiscalBooks, initial });
  // The server names the form's currency; a non-default one proves Revisar uses it, not the screen's default.
  page.fixture.controls.dgiiCurrency = "EUR";
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
  await page.settle(() => page.button("Revisar") !== undefined);
  const notice = Number(/(\d+) compras? tienen? datos fiscales pendientes/.exec(dialogText())![1]);
  await page.click(page.button("Revisar"));
  await page.settle(() => panel() === null && document.querySelector('[data-overview-filter="fiscal"]')?.getAttribute("aria-pressed") === "true" && document.querySelector('[data-testid="records-count"]') !== null);
  const last = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).at(-1)!.body as ReportRequest;
  assert.deepEqual(last.filters, reportFiltersSchema.parse({ period: initial.filters.period, record_families: ["purchase"], currencies: ["EUR"], fiscal_data: "missing" }));
  assert.ok(document.querySelector('button[aria-label="Moneda: EUR"]'), "the screen switches to the form's currency");
  assert.match(document.querySelector('[data-testid="records-count"]')!.textContent!, new RegExp(`de ${notice} registros?`));
  assert.equal(notice, 1);
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


for (const language of ["es-419", "en"] as const) {
  test(`606 keeps server RNC warnings inside the option with a bounded supplier toggle in ${language}`, async () => {
    const page = await mount({ edit: fiscalBooks, language, width: language === "en" ? 390 : 1440 });
    page.fixture.controls.rncSuppliers = [
      { name: "Suplidor registrado", rnc: "101001577", estado: "SUSPENDIDO", status: "rnc_inactive", record_count: 2 },
      { name: "Proveedor sin registro", rnc: "101010632", estado: "SUSPENDIDO", status: "rnc_unverified", record_count: 1 },
      { name: "Proveedor cancelado", rnc: "101010633", estado: "DADO DE BAJA", status: "rnc_inactive", record_count: 1 },
      ...Array.from({ length: 24 }, (_, index) => ({ name: `Proveedor ${index}`, rnc: `1310000${String(index).padStart(2, "0")}`, estado: "ANULADO", status: "rnc_inactive" as const, record_count: 1 })),
    ];
    await page.click(document.querySelector('[data-testid="records-export"]'));
    await page.settle(() => downloadButton() !== null && !downloadButton()!.disabled);
    assert.equal(document.querySelector('[data-testid="records-export-notices"]'), null);
    await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
    const option = document.querySelector('[data-testid="records-export-mode-dgii"]')!;
    const notice = option.querySelector('[data-testid="records-export-rnc-notice"]')!;
    assert.ok(notice, "the RNC notice is inside the 606 option");
    const notices = option.querySelector('[data-testid="records-export-notices"]')!;
    const toggle = notice.querySelector<HTMLButtonElement>("button")!;
    assert.equal(notices.children.length, 3, "RNC, pending fiscal data, and pending rates share one list");
    assert.equal(notices.querySelectorAll("h3").length, 0);
    assert.ok(notice.querySelector(".lucide-triangle-alert"));
    assert.equal(toggle.closest("label"), null);
    assert.ok(toggle.closest("p"), "the sentence and action share one paragraph");
    for (const link of [toggle, page.button(language === "es-419" ? "Revisar" : "Review")!]) {
      assert.ok(link.classList.contains("inline"));
      assert.ok(link.classList.contains("text-[14px]"));
      assert.equal(link.classList.contains("min-h-11"), false);
    }
    assert.equal(notice.querySelector(".lucide-triangle-alert")?.classList.contains("mt-3.5"), false);
    assert.equal(toggle.textContent, language === "es-419" ? "Ver proveedores" : "View suppliers");
    assert.equal(toggle.getAttribute("aria-expanded"), "false");
    const list = document.getElementById(toggle.getAttribute("aria-controls")!)!;
    assert.ok(list, "the toggle points to its supplier list");
    assert.equal(list.tabIndex, 0);
    assert.equal(list.getAttribute("aria-label"), language === "es-419" ? "Ver proveedores" : "View suppliers");
    assert.equal(list.hidden, true);
    assert.equal(noticeSentence(notice), language === "es-419"
      ? "27 proveedores con RNC no activo o sin verificar"
      : "27 suppliers with an inactive or unverified RNC");
    assert.ok(notice.textContent?.includes(language === "es-419" ? "La DGII puede rechazar sus líneas." : "The DGII may reject their lines."));
    await page.click(toggle);
    assert.equal(toggle.getAttribute("aria-expanded"), "true");
    assert.equal(toggle.textContent, language === "es-419" ? "Ocultar" : "Hide");
    assert.equal(list.hidden, false);
    assert.ok(list.classList.contains("max-h-[132px]"));
    assert.ok(list.classList.contains("overflow-y-auto"));
    assert.ok(list.classList.contains("border"));
    assert.equal(list.children.length, 27);
    assert.deepEqual([...list.children].slice(0, 3).map((item) => ({
      name: item.firstElementChild?.firstElementChild?.textContent,
      status: item.firstElementChild?.lastElementChild?.textContent,
      rnc: item.lastElementChild?.textContent,
    })), [
      { name: "Suplidor registrado", status: language === "es-419" ? "No activo" : "Not active", rnc: "101001577" },
      { name: "Proveedor sin registro", status: language === "es-419" ? "Sin verificar" : "Not verified", rnc: "101010632" },
      { name: "Proveedor cancelado", status: language === "es-419" ? "No activo" : "Not active", rnc: "101010633" },
    ]);
    for (const item of list.children) {
      assert.ok(item.firstElementChild?.classList.contains("justify-between"));
      assert.ok(item.firstElementChild?.lastElementChild?.firstElementChild?.classList.contains("rounded-full"));
      assert.ok(item.firstElementChild?.lastElementChild?.firstElementChild?.classList.contains("text-[12px]"));
      assert.ok(item.lastElementChild?.classList.contains("font-mono"));
    }
    assert.doesNotMatch(list.textContent!, /SUSPENDIDO|DADO DE BAJA|ANULADO/);
    const i18n = await translate(language);
    for (const [index, status] of (["inactive", "unverified", "inactive"] as const).entries()) {
      const tag = renderToStaticMarkup(<I18nextProvider i18n={i18n}><DgiiRegistryTag status={status} /></I18nextProvider>);
      assert.equal(list.children[index].firstElementChild?.lastElementChild?.innerHTML, tag);
    }
    assert.ok(list.children[0].firstElementChild?.lastElementChild?.firstElementChild?.classList.contains("bg-[#F6EBD4]"));
    assert.ok(list.children[1].firstElementChild?.lastElementChild?.firstElementChild?.classList.contains("bg-[#EDECE6]"));
    assert.equal(downloadButton()!.disabled, false);
    await page.click(toggle);
    assert.equal(list.hidden, true);
    await page.click(downloadButton());
    await page.settle(() => page.downloads.length === 1);
  });

  test(`one RNC supplier uses the singular notice in ${language}`, async () => {
    const page = await mount({ language, edit: (rows) => rows.filter((row) => row.family === "purchase").forEach((row) => { row.stage = "ready_for_export"; row.fiscal_data = "complete"; row.currency = "DOP"; }) });
    page.fixture.controls.rncSuppliers = [
      { name: "Suplidor registrado", rnc: "101001577", estado: "SUSPENDIDO", status: "rnc_inactive", record_count: 2 },
    ];
    await page.click(document.querySelector('[data-testid="records-export"]'));
    await page.settle(() => downloadButton() !== null && !downloadButton()!.disabled);
    await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
    const notice = document.querySelector('[data-testid="records-export-rnc-notice"]');
    assert.equal(document.querySelector('[data-testid="records-export-notices"]')?.children.length, 1);
    assert.equal(noticeSentence(notice), language === "es-419"
      ? "1 proveedor con RNC no activo o sin verificar"
      : "1 supplier with an inactive or unverified RNC");
    assert.equal(downloadButton()!.disabled, false);
  });
}

test("zero RNC warnings hide the notice in DGII mode", async () => {
  const page = await mount({ edit: fiscalBooks });
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
  assert.equal(document.querySelector('[data-testid="records-export-rnc-notice"]'), null);
});

test("607 keeps pending notices below the options", async () => {
  const initial = reportRequestSchema.parse({ schema_version: 2, filters: { record_families: ["sale"], currencies: ["DOP"] } });
  const page = await mount({ initial, edit: (rows) => rows.filter((row) => row.family === "sale").slice(0, 1).forEach((row) => { row.fiscal_data = "missing"; row.stage = "needs_fiscal_data"; }) });
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
  assert.match(dialogText(), /Formato DGII 607/);
  assert.equal(document.querySelector('[data-testid="records-export-notices"]'), null);
  const notice = document.querySelector('[data-testid="records-export-dgii"]')!;
  assert.match(notice.textContent!, /1 venta tiene datos fiscales pendientes y no se incluye\./);
  assert.ok(notice.contains(page.button("Revisar")!));
  assert.ok(page.button("Revisar")!.classList.contains("min-h-11"), "607 keeps its existing review button");
  assert.equal(document.querySelector('[data-testid="records-export-mode-dgii"]')!.contains(page.button("Revisar")!), false);
});

test("Registros renders distinct server net, ITBIS and Total columns and its card uses only the net total", async () => {
  const page = await mount({ queryAnswer: (_, answer) => ({
    ...answer,
    items: answer.items.map((row) => ({ ...row, net_amount: "80.00", net_amount_source: "read", itbis_amount: "18.00", gross_amount: "100.00" })),
    totals: [
      { currency: "DOP", kind: "expense", basis: "document_family_amount", matching_count: 1, known_amount_minor: 10000, unknown_count: 0, unsupported_count: 0, complete: true, amount_minor: 10000, known_amount: "100.00", amount: "100.00" },
      { currency: "DOP", kind: "expense", basis: "document_net_family_amount", matching_count: 1, known_amount_minor: 8000, unknown_count: 0, unsupported_count: 0, complete: true, amount_minor: 8000, known_amount: "80.00", amount: "80.00" },
    ],
  }) });
  const headings = [...document.querySelectorAll('thead th[data-col]')].map((cell) => cell.getAttribute("data-col"));
  const index = headings.indexOf("net_amount");
  assert.deepEqual(headings.slice(index, index + 3), ["net_amount", "itbis_amount", "gross_amount"]);
  assert.equal(document.querySelector('th[data-col="net_amount"]')?.textContent, "Monto sin ITBIS");
  assert.equal(document.querySelector('th[data-col="gross_amount"]')?.textContent, "Total");
  const row = document.querySelector("tbody tr")!;
  for (const [key, value] of [["net_amount", "80.00"], ["itbis_amount", "18.00"], ["gross_amount", "100.00"]]) {
    const cell = row.querySelector(`[data-col="${key}"]`)!;
    assert.equal(cell.textContent, value);
    assert.ok(cell.classList.contains("text-right"));
    assert.ok(cell.classList.contains("tabular-nums"));
    assert.ok(cell.querySelector(".cuadrao-amount"));
  }
  const card = document.querySelector('[data-overview-card="total"]')!;
  assert.match(card.textContent!, /Compras sin ITBIS/);
  assert.equal(card.querySelector(".cuadrao-amount")?.getAttribute("aria-label"), "DOP 80.00");
  assert.equal(card.querySelector("button"), null);
  await open(page);
  assert.match(dialogText(), /Columnas de tu tabla \(8\)/);
});
