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

/**
 * A Chromium Save As window: it records what it was asked and when, the bytes
 * written into the chosen place, and each chosen file removed again. Like
 * Chromium, picking a new place makes the file at once, empty; picking an
 * `existing` file and confirming Replace keeps its bytes until a write lands.
 */
function chromiumPicker(page: Page, outcome: { cancel?: boolean; writeFails?: boolean; writeGate?: Promise<void>; remove?: "missing" | "fails"; existing?: string; getFile?: "missing" | "fails" } = {}) {
  const picked: Picked[] = [];
  const written: Blob[] = [];
  const aborted: number[] = [];
  const removed: string[] = [];
  let writables = 0;
  (window as unknown as { showSaveFilePicker: (options: PickerOptions) => Promise<unknown> }).showSaveFilePicker = async (options) => {
    picked.push({ options, exportsBefore: exportCalls(page) });
    if (outcome.cancel) throw new DOMException("The user aborted a request.", "AbortError");
    let contents = new Blob([outcome.existing ?? ""]);
    const remove = async () => {
      removed.push(options.suggestedName);
      if (outcome.remove === "fails") throw new DOMException("No permission.", "NotAllowedError");
    };
    const getFile = async () => {
      if (outcome.getFile === "fails") throw new DOMException("The file could not be read.", "NotReadableError");
      return new File([contents], options.suggestedName);
    };
    return {
      ...(outcome.remove === "missing" ? {} : { remove }),
      ...(outcome.getFile === "missing" ? {} : { getFile }),
      createWritable: async () => {
        writables += 1;
        const pending: Blob[] = [];
        return {
          write: async (blob: Blob) => { await outcome.writeGate; if (outcome.writeFails) throw new DOMException("The disk is full.", "QuotaExceededError"); pending.push(blob); },
          close: async () => { written.push(...pending); contents = new Blob(pending); },
          abort: async () => { aborted.push(pending.length); },
        };
      },
    };
  };
  return { picked, written, aborted, removed, writables: () => writables };
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
  assert.deepEqual(save.removed, [], "a saved file is never removed");
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
  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  assert.deepEqual(save.removed, [], "a cancelled window made no file, so nothing is removed");
});

test("a failed write discards the partial file, removes the empty one, and falls back to the download with the same bytes", async () => {
  const toasts = await showToasts();
  const page = await mount();
  const save = chromiumPicker(page, { writeFails: true });
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => page.downloads.length === 1);
  assert.deepEqual(save.aborted, [0], "the write is discarded, never committed");
  assert.equal(save.written.length, 0);
  assert.deepEqual(save.removed, ["Compras todas las monedas.xlsx"], "the empty file goes; the download is the copy");
  assert.equal(await page.downloads[0].text(), "Contraparte 1");
  assert.equal(exportCalls(page), 1, "no second request");
  assert.match(toasts.textContent!, /Listo\. Revisa tus descargas/);
});

test.each([
  { result: "fails", writeFails: true, existing: "" },
  { result: "fails while replacing an existing file", writeFails: true, existing: "last month's 606" },
  { result: "succeeds", writeFails: false, existing: "" },
])("closing mid-write stays silent when the write $result", async ({ writeFails, existing }) => {
  let release = () => {};
  const writeGate = new Promise<void>((resolve) => { release = resolve; });
  const toasts = await showToasts();
  const page = await mount();
  const save = chromiumPicker(page, { writeFails, existing, writeGate });
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => save.writables() === 1);
  assert.equal(save.written.length, 0, "the write is still pending");
  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  await open(page);
  const reopened = panel();
  await act(async () => release());
  if (writeFails) assert.deepEqual(save.removed, existing ? [] : ["Compras todas las monedas.xlsx"], "only an empty file is discarded");
  assert.equal(page.downloads.length, 0, "a closed export never starts a download");
  assert.equal(toasts.textContent, "", "a closed export never shows a toast");
  assert.equal(panel(), reopened, "the old run cannot close the reopened dialog");
  assert.equal(downloadButton()!.disabled, false, "the old run cannot change the new dialog's state");
  assert.equal(alert(), null);
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
  assert.deepEqual(save.removed, [], "the file Reintentar wrote stays");
});

test("a failed build, then closing the export, removes the empty file Save As made", async () => {
  const page = await mount();
  const save = chromiumPicker(page);
  page.fixture.controls.exportFails = true;
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => alert() !== null);
  assert.deepEqual(save.removed, [], "the place stays while Reintentar can still write to it");
  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  await page.settle(() => save.removed.length === 1);
  assert.deepEqual(save.removed, ["Compras todas las monedas.xlsx"]);
  assert.equal(save.writables(), 0);
  assert.equal(page.downloads.length, 0);
});

test("a failed build, then closing the export, never removes an existing file the person chose to replace", async () => {
  const page = await mount();
  const save = chromiumPicker(page, { existing: "last month's 606" });
  page.fixture.controls.exportFails = true;
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => alert() !== null);
  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
  assert.deepEqual(save.removed, [], "a file with bytes in it is the person's, never removed");
  assert.equal(save.writables(), 0);
});

test("where the chosen file cannot be read, closing after a failed build keeps it and still closes cleanly", async () => {
  for (const getFile of ["missing", "fails"] as const) {
    const page = await mount();
    const save = chromiumPicker(page, { getFile });
    page.fixture.controls.exportFails = true;
    await open(page);
    await page.click(downloadButton());
    await page.settle(() => alert() !== null);
    await page.click(page.button("Cerrar"));
    await page.settle(() => panel() === null);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
    assert.deepEqual(save.removed, [], `getFile ${getFile}: an unread file is never removed`);
    assert.equal(alert(), null);
    assert.equal(page.downloads.length, 0);
    await cleanup();
    document.body.innerHTML = "";
  }
});

test("after a failed build, choosing another file removes the first place's empty file", async () => {
  const page = await mount();
  const save = chromiumPicker(page);
  page.fixture.controls.exportFails = true;
  await open(page);
  await page.click(downloadButton());
  await page.settle(() => alert() !== null);
  page.fixture.controls.exportFails = false;
  await page.click(page.button("CSV"));
  await page.click(downloadButton());
  await page.settle(() => save.written.length === 1);
  assert.deepEqual(save.picked.map(({ options }) => options.suggestedName), ["Compras todas las monedas.xlsx", "Compras todas las monedas.csv"]);
  assert.deepEqual(save.removed, ["Compras todas las monedas.xlsx"], "only the abandoned place goes; the saved CSV stays");
});

test("where a handle has no remove(), or removing fails, closing after a failed build still closes cleanly", async () => {
  for (const remove of ["missing", "fails"] as const) {
    const page = await mount();
    const save = chromiumPicker(page, { remove });
    page.fixture.controls.exportFails = true;
    await open(page);
    await page.click(downloadButton());
    await page.settle(() => alert() !== null);
    await page.click(page.button("Cerrar"));
    await page.settle(() => panel() === null);
    assert.deepEqual(save.removed, remove === "fails" ? ["Compras todas las monedas.xlsx"] : []);
    assert.equal(page.downloads.length, 0);
    await cleanup();
    document.body.innerHTML = "";
  }
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
  assert.match(tip()!.textContent!, /Elige dónde guardar cada archivo/);
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
