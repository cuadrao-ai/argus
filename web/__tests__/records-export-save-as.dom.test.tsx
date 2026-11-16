import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { I18nextProvider } from "react-i18next";
import { mountConnectedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { translate } from "./support/i18n-instance";
import type { ReportRecord } from "@/lib/business-reports-api";

await keepOwnListSearch();

type Page = Awaited<ReturnType<typeof mount>>;
type PickerOptions = { suggestedName: string; id: string; types: { accept: Record<string, string[]> }[] };
type Picked = { options: PickerOptions; exportsBefore: number };

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
let unmountToasts = async () => {};
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => {
  delete (window as { showSaveFilePicker?: unknown }).showSaveFilePicker;
  await unmountToasts(); unmountToasts = async () => {};
  await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); (await import("@/components/business-app/foundation/toasts")).clearToasts(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz");
});
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

const panel = () => document.querySelector<HTMLElement>('[data-testid="records-export-panel"]');
const downloadButton = () => document.querySelector<HTMLButtonElement>('[data-testid="records-export-download"]');
const dialogText = () => document.querySelector('[role="dialog"]')?.textContent ?? "";
const alert = () => document.querySelector('[role="dialog"] [role="alert"]');
const exportCalls = (page: Page) => page.fixture.calls.filter((call) => call.path.endsWith("/reports/export")).length;
const tip = () => document.querySelector('[role="dialog"] section[aria-labelledby]');

/** Four purchases complete for the 606, so Formato DGII has lines to save. */
function fiscalBooks(rows: ReportRecord[]) {
  rows.filter((row) => row.family === "purchase").slice(0, 4).forEach((row) => { row.stage = "ready_for_export"; row.fiscal_data = "complete"; row.ready = true; row.missing = []; });
}

async function open(page: Page) {
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => /^Exportar \d+ registros?$/.test(downloadButton()?.textContent?.trim() ?? ""));
}

async function showToasts() {
  const { createRoot } = await import("react-dom/client");
  const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  const i18n = await translate("es-419");
  await act(async () => root.render(<I18nextProvider i18n={i18n}><ToastViewport /></I18nextProvider>));
  unmountToasts = async () => { await act(async () => root.unmount()); };
  return host;
}

/** A Chromium Save As window: it records what it was asked and when, and the bytes written into the chosen place. */
function chromiumPicker(page: Page, outcome: { cancel?: boolean; writeFails?: boolean } = {}) {
  const picked: Picked[] = [];
  const written: Blob[] = [];
  const aborted: number[] = [];
  let writables = 0;
  (window as unknown as { showSaveFilePicker: (options: PickerOptions) => Promise<unknown> }).showSaveFilePicker = async (options) => {
    picked.push({ options, exportsBefore: exportCalls(page) });
    if (outcome.cancel) throw new DOMException("The user aborted a request.", "AbortError");
    return {
      createWritable: async () => {
        writables += 1;
        const pending: Blob[] = [];
        return {
          write: async (blob: Blob) => { if (outcome.writeFails) throw new DOMException("The disk is full.", "QuotaExceededError"); pending.push(blob); },
          close: async () => { written.push(...pending); },
          abort: async () => { aborted.push(pending.length); },
        };
      },
    };
  };
  return { picked, written, aborted, writables: () => writables };
}

test("on Chromium the Save As window opens on the click, before the export request, with the server's name and one folder per type", async () => {
  const page = await mount({ edit: fiscalBooks });
  const save = chromiumPicker(page);
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => save.written.length === 1);
  await open(page);
  await page.click(page.button("CSV"));
  await page.click(downloadButton());
  await page.settle(() => save.written.length === 2);
  await open(page);
  await page.click(document.querySelector('[data-testid="records-export-mode-dgii"] input'));
  await page.click(downloadButton());
  await page.settle(() => save.written.length === 3);
  assert.deepEqual(save.picked.map(({ options, exportsBefore }, index) => ({ name: options.suggestedName, id: options.id, accept: Object.values(options.types[0].accept).flat(), firstRequest: exportsBefore === index })), [
    { name: "Compras todas las monedas.xlsx", id: "cuadrao-export-xlsx", accept: [".xlsx"], firstRequest: true },
    { name: "Compras todas las monedas.csv", id: "cuadrao-export-csv", accept: [".csv"], firstRequest: true },
    { name: "Compras 606.xlsx", id: "cuadrao-export-xlsx", accept: [".xlsx"], firstRequest: true },
  ]);
});

test("saved: the file is written to the chosen place and the toast says Guardado, with no button", async () => {
  const toasts = await showToasts();
  const page = await mount();
  const save = chromiumPicker(page);
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => save.written.length === 1);
  assert.equal(await save.written[0].text(), "Contraparte 1");
  assert.equal(page.downloads.length, 0, "no second copy in Descargas");
  assert.equal(panel(), null, "the dialog closes once the file is saved");
  await page.settle(() => toasts.textContent?.includes("Guardado") ?? false);
  assert.deepEqual([...toasts.querySelectorAll("button")].map((button) => button.getAttribute("aria-label")), ["Cerrar"], "no action, only the toast's own close");
});

test("cancel: the Save As window closes and nothing happens, with no error and no request", async () => {
  const page = await mount();
  const save = chromiumPicker(page, { cancel: true });
  await open(page);
  await page.click(downloadButton());
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
  assert.equal(save.picked.length, 1);
  assert.equal(exportCalls(page), 0);
  assert.equal(page.downloads.length, 0);
  assert.equal(alert(), null);
  assert.ok(panel(), "the dialog stays open");
  assert.equal(downloadButton()!.disabled, false);
});

test("a failed write discards the partial file and falls back to the download with the same bytes", async () => {
  const toasts = await showToasts();
  const page = await mount();
  const save = chromiumPicker(page, { writeFails: true });
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => page.downloads.length === 1);
  assert.deepEqual(save.aborted, [0], "the write is discarded, never committed");
  assert.equal(save.written.length, 0);
  assert.equal(await page.downloads[0].text(), "Contraparte 1");
  assert.equal(exportCalls(page), 1, "no second request");
  assert.match(toasts.textContent!, /Listo\. Revisa tus descargas/);
});

test("a failed build writes nothing and Reintentar asks the server again for the place already chosen", async () => {
  const toasts = await showToasts();
  const page = await mount();
  const save = chromiumPicker(page);
  page.fixture.controls.exportFails = true;
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => alert() !== null);
  assert.match(alert()!.textContent!, /No se pudo guardar el archivo\./);
  assert.equal(save.writables(), 0, "nothing is written");
  assert.equal(page.downloads.length, 0);
  page.fixture.controls.exportFails = false;
  await page.click(page.button("Reintentar"));
  await page.settle(() => save.written.length === 1);
  assert.equal(save.picked.length, 1, "the place is not asked again");
  assert.equal(exportCalls(page), 2);
  await page.settle(() => toasts.textContent?.includes("Guardado") ?? false);
});

test("where the browser has no Save As window, the export downloads as today", async () => {
  const toasts = await showToasts();
  const page = await mount();
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => page.downloads.length === 1);
  assert.match(toasts.textContent!, /Listo\. Revisa tus descargas/);
});

test("on a desktop browser without Save As, the tip shows once and stays dismissed", async () => {
  const page = await mount();
  await open(page);
  assert.ok(tip(), "the tip shows in the dialog");
  assert.match(tip()!.textContent!, /PENDIENTE COPY/);
  await page.click(tip()!.querySelector("button"));
  assert.equal(tip(), null);
  assert.deepEqual(page.guideRequests, ["POST /business/guide-cards/exportar-guardar/dismiss"]);
  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  await open(page);
  assert.equal(tip(), null, "a dismissed tip stays gone");
  assert.equal(page.guideRequests.length, 1);
});

test("the tip never shows with a Save As window, on a phone, or once dismissed", async () => {
  let page = await mount();
  chromiumPicker(page);
  await open(page);
  assert.ok(dialogText());
  assert.equal(tip(), null, "Chromium asks where to save on its own");
  await cleanup();
  delete (window as { showSaveFilePicker?: unknown }).showSaveFilePicker;
  document.body.innerHTML = "";
  page = await mount({ width: 390 });
  await open(page);
  assert.equal(tip(), null, "phones keep today's download with no tip");
  await cleanup();
  document.body.innerHTML = "";
  page = await mount({ dismissedGuides: ["exportar-guardar"] });
  await open(page);
  assert.equal(tip(), null);
});
