import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, setSystemTime, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { I18nextProvider } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { mountConnectedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";
import { keepOwnListSearch } from "./fixtures/own-list-search";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
let unmountBar = async () => {};
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => {
  delete (window as { showSaveFilePicker?: unknown }).showSaveFilePicker;
  await unmountBar(); unmountBar = async () => {};
  await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); (await import("@/components/business-app/foundation/toasts")).clearToasts(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz");
});
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

/** The suite's clock is pinned. A job that starts later needs the clock moved. */
const later = (ms: number) => setSystemTime(new Date(Date.now() + ms));
const SAVE_FAILED = "No se pudo guardar el archivo.";
const BUILD_FAILED = "No pudimos preparar el archivo. Inténtalo de nuevo.";
const panel = () => document.querySelector<HTMLElement>('[data-testid="records-export-panel"]');
const downloadButton = () => document.querySelector<HTMLButtonElement>('[data-testid="records-export-download"]');
const alert = () => document.querySelector('[role="dialog"] [role="alert"]');
const island = () => document.querySelector<HTMLElement>('[data-testid="receipt-upload-island"]');

/** Registros with its real export panel, and the top bar's island and toasts on the same export job. Every export request and upload waits for the test. */
async function registros() {
  const page = await mount();
  const { createRoot } = await import("react-dom/client");
  const { default: ReceiptUploadIsland } = await import("@/components/business-app/ReceiptUploadIsland");
  const { ReceiptUploadQueue } = await import("@/components/business-app/receipt-upload-queue");
  const { RecordsExportJobContext } = await import("@/components/business-app/transacciones/records-export-job");
  const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
  const uploads: ((receipt: ReceiptSummary) => void)[] = [];
  const queue = new ReceiptUploadQueue(() => new Promise<ReceiptSummary>((resolve) => { uploads.push(resolve); }), () => {});
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={page.i18n}><RecordsExportJobContext.Provider value={page.exportJob}>
    <div><ReceiptUploadIsland queue={queue} grant={null} panelOpen={false} drawer={null} onOpen={() => {}} onOpenExport={() => page.exportJob.reopen()} /></div>
    <div data-toasts=""><ToastViewport /></div>
  </RecordsExportJobContext.Provider></I18nextProvider>));
  unmountBar = async () => { await act(async () => root.unmount()); };

  const live = globalThis.fetch;
  const held: (() => void)[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/reports/export")) await new Promise<void>((resolve) => { held.push(resolve); });
    return live(input, init);
  }) as typeof fetch;
  const exportCalls = () => page.fixture.calls.filter((call) => call.path.endsWith("/reports/export")).length;
  return {
    ...page, exportCalls,
    toasts: () => host.querySelector("[data-toasts]")!,
    open: async () => {
      await page.click(document.querySelector('[data-testid="records-export"]'));
      await page.settle(() => /^Exportar \d+ registros?$/.test(downloadButton()?.textContent?.trim() ?? ""));
    },
    /** Lets the server answer the export it holds. */
    answer: async () => {
      await page.settle(() => held.length > 0);
      await act(async () => held.shift()!());
    },
    upload: async (name: string) => {
      await act(async () => {
        queue.add([new File(["recibo"], name, { type: "image/jpeg" })], { max_bytes: 1_000_000, media_types: ["image/jpeg"] }, "inbox");
        void queue.save("inbox", true);
      });
    },
    finishUpload: async () => {
      await page.settle(() => uploads.length > 0);
      await act(async () => uploads.shift()!({ id: `receipt-${uploads.length}` } as ReceiptSummary));
    },
  };
}

/** A Save As window that stays open until the test picks a place. */
function savePicker() {
  const asked: string[] = [];
  const written: Blob[] = [];
  const removed: string[] = [];
  let pick = () => {};
  (window as unknown as { showSaveFilePicker: (options: { suggestedName: string }) => Promise<unknown> }).showSaveFilePicker = async (options) => {
    asked.push(options.suggestedName);
    await new Promise<void>((resolve) => { pick = resolve; });
    let size = 0;
    return {
      getFile: async () => new File([new Uint8Array(size)], options.suggestedName),
      remove: async () => { removed.push(options.suggestedName); },
      createWritable: async () => ({ write: async (blob: Blob) => { written.push(blob); size = blob.size; }, close: async () => {}, abort: async () => {} }),
    };
  };
  return { asked, written, removed, pick: () => act(async () => pick()) };
}

test("Descargar asks where to save, then the panel closes and the island shows the export; the button never spins", async () => {
  const page = await registros();
  const save = savePicker();
  await page.open();
  const label = downloadButton()!.textContent;
  await page.click(downloadButton());
  assert.deepEqual(save.asked, ["Compras todas las monedas.xlsx"]);
  assert.ok(panel(), "the panel waits while Save As is open");
  assert.equal(island(), null, "no export runs before a place is chosen");
  assert.equal(page.exportCalls(), 0);

  await save.pick();
  await page.settle(() => panel() === null);
  assert.equal(island()?.dataset.state, "preparing");
  assert.equal(island()?.textContent, "Preparando…");
  assert.ok(island()!.querySelector('[data-arrow="down"]'), "the arrow points down for an export");
  assert.equal(island()!.tagName, "DIV", "an export being prepared has no click and no cancel");

  await page.open();
  assert.equal(downloadButton()!.textContent, label, "the button keeps its words");
  assert.equal(downloadButton()!.querySelector("svg"), null, "no spinner on the button");
  assert.equal(downloadButton()!.getAttribute("aria-busy"), null);
});

test("done: the island shows its check with no words and closes, and the toast says Guardado", async () => {
  const page = await registros();
  const save = savePicker();
  await page.open();
  await page.click(downloadButton());
  await save.pick();
  await page.answer();
  await page.settle(() => island()?.dataset.state === "done");
  assert.equal(island()!.textContent, "", "the check alone");
  assert.equal(island()!.querySelectorAll("svg path").length, 1);
  assert.equal(save.written.length, 1);
  assert.match(page.toasts().textContent!, /Guardado/);
  assert.equal(panel(), null);
  later(1600);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1700)); });
  assert.equal(island(), null, "the island closes by itself");
});

test("done without Save As: the toast offers Descargar de nuevo and the island never does", async () => {
  const page = await registros();
  await page.open();
  await page.click(downloadButton());
  await page.settle(() => island()?.dataset.state === "preparing");
  await page.answer();
  await page.settle(() => page.downloads.length === 1);
  assert.equal(island()?.dataset.state, "done");
  assert.equal(island()!.textContent, "");
  assert.match(page.toasts().textContent!, /Listo\. Revisa tus descargas/);
  await page.click([...page.toasts().querySelectorAll("button")].find((button) => button.textContent === "Descargar de nuevo"));
  assert.equal(page.downloads.length, 2);
  assert.equal(page.downloads[1], page.downloads[0], "the same bytes again");
  assert.equal(page.exportCalls(), 1, "never a second request");
});

test("failed: the island turns red with the alert icon and no words, its name is the panel's sentence, a click reopens the panel at that error, and Reintentar reuses the place", async () => {
  const page = await registros();
  const save = savePicker();
  page.fixture.controls.exportFails = true;
  await page.open();
  await page.click(page.button("CSV"));
  await page.click(downloadButton());
  await save.pick();
  await page.answer();
  await page.settle(() => island()?.dataset.state === "failed");
  assert.equal(panel(), null, "the panel stays closed");
  assert.equal(island()!.textContent, "", "the alert icon alone, at every width");
  assert.equal(island()!.getAttribute("aria-label"), SAVE_FAILED);
  assert.match(island()!.className, /text-\[#9e2f39\]/);
  assert.equal(page.toasts().textContent, "", "a failure is never a toast");

  await page.click(island());
  await page.settle(() => alert() !== null);
  assert.equal(island(), null, "the open panel says it");
  assert.ok(alert()!.textContent!.startsWith(SAVE_FAILED), "the panel shows the island's sentence");
  assert.equal(page.button("CSV")!.getAttribute("aria-checked"), "true", "the panel opens on the failed file's choices");

  page.fixture.controls.exportFails = false;
  await page.click(page.button("Reintentar"));
  await page.settle(() => panel() === null);
  assert.equal(island()?.dataset.state, "preparing");
  await page.answer();
  await page.settle(() => save.written.length === 1);
  assert.deepEqual(save.asked, ["Compras todas las monedas.csv"], "the place is not asked again");
  assert.equal(page.exportCalls(), 2);
  assert.deepEqual(save.removed, []);
  assert.match(page.toasts().textContent!, /Guardado/);
});

test("failed without Save As: the island's name and the panel both say the file could not be prepared, and closing the panel lets the failure go", async () => {
  const page = await registros();
  page.fixture.controls.exportFails = true;
  await page.open();
  await page.click(downloadButton());
  await page.answer();
  await page.settle(() => island()?.dataset.state === "failed");
  assert.equal(island()!.textContent, "");
  assert.equal(island()!.getAttribute("aria-label"), BUILD_FAILED);
  await page.click(island());
  await page.settle(() => alert() !== null);
  assert.ok(alert()!.textContent!.startsWith(BUILD_FAILED));
  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  assert.equal(island(), null);
  await page.open();
  assert.equal(alert(), null);
});

/** What each export request asked the server for. */
const exported = (page: { fixture: { calls: { path: string; body: unknown }[] } }) => page.fixture.calls.filter((call) => call.path.endsWith("/reports/export")).map((call) => call.body as { format: string; report: { filters: { q: string } } });
/** Fails an export of the whole table as CSV, then searches the table, so the table's request is no longer the failed file's. */
async function failThenSearch() {
  const page = await registros();
  page.fixture.controls.exportFails = true;
  await page.open();
  await page.click(page.button("CSV"));
  await page.click(downloadButton());
  await page.answer();
  await page.settle(() => island()?.dataset.state === "failed");
  page.fixture.controls.exportFails = false;
  await page.type(document.querySelector('input[type="search"]')!, "proveedor");
  await page.settle(() => page.fixture.calls.some((call) => call.path.endsWith("/reports/query") && JSON.stringify(call.body).includes('"q":"proveedor"')));
  return page;
}

test("a failure never shows on another request: Exportar on a changed table opens clean and exports the new request, and the failed file stays in the island", async () => {
  const page = await failThenSearch();
  await page.open();
  assert.match(panel()!.textContent!, /1 filtro/, "the panel is on the table's new request");
  assert.equal(alert(), null, "the other file's failure is not this request's");
  assert.equal(page.button("Reintentar"), undefined);
  assert.equal(page.button("CSV")!.getAttribute("aria-checked"), "false", "the panel does not take the failed file's choices");
  assert.equal(island()?.dataset.state, "failed", "the failed file is still in the island");

  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  assert.equal(island()?.dataset.state, "failed", "closing another request's panel does not let the failure go");

  await page.open();
  await page.click(downloadButton());
  await page.settle(() => island()?.dataset.state === "preparing");
  await page.answer();
  await page.settle(() => page.downloads.length === 1);
  assert.deepEqual(exported(page).map((sent) => [sent.format, sent.report.filters.q]), [["csv", ""], ["xlsx", "proveedor"]], "Descargar exports the new request");
});

test("a click on the red island opens the panel on the failed file's own request, whatever the table shows now, and Reintentar downloads that same file", async () => {
  const page = await failThenSearch();
  await page.click(island());
  await page.settle(() => alert() !== null);
  assert.ok(alert()!.textContent!.startsWith(BUILD_FAILED));
  assert.doesNotMatch(panel()!.textContent!, /1 filtro/, "the panel is on the failed file's request, not the table's");
  assert.equal(page.button("CSV")!.getAttribute("aria-checked"), "true");
  assert.equal(island(), null, "the open panel says it");

  await page.click(page.button("Excel"));
  assert.equal(alert(), null, "another format is another file: the failure is not its own");
  await page.click(page.button("CSV"));
  assert.ok(alert(), "back on the failed file, its failure shows again");

  await page.click(page.button("Reintentar"));
  await page.settle(() => island()?.dataset.state === "preparing");
  await page.answer();
  await page.settle(() => page.downloads.length === 1);
  assert.deepEqual(exported(page).map((sent) => [sent.format, sent.report.filters.q]), [["csv", ""], ["csv", ""]], "the same request again");
});

test("closing the panel while a file is prepared does not cancel it, and Descargar is off until it ends", async () => {
  const page = await registros();
  await page.open();
  await act(async () => { downloadButton()!.click(); downloadButton()!.click(); });
  await page.settle(() => island()?.dataset.state === "preparing");
  await page.open();
  assert.equal(downloadButton()!.disabled, true, "one export at a time");
  await page.click(downloadButton());
  await page.click(page.button("Cerrar"));
  await page.settle(() => panel() === null);
  assert.equal(island()?.dataset.state, "preparing", "closing the panel leaves the export running");
  await page.answer();
  await page.settle(() => page.downloads.length === 1);
  assert.equal(page.exportCalls(), 1);
  assert.match(page.toasts().textContent!, /Listo\. Revisa tus descargas/);
  await page.open();
  assert.equal(downloadButton()!.disabled, false);
});

test("an upload and an export together: the island shows the newer job, then the other when the first finishes", async () => {
  const page = await registros();
  await page.upload("a.jpg");
  await page.settle(() => island()?.dataset.state === "uploading");
  assert.equal(island()!.textContent, "1 de 1");
  later(1000);
  await page.open();
  await page.click(downloadButton());
  await page.settle(() => island()?.dataset.state === "preparing");
  assert.equal(island()!.textContent, "Preparando…", "the export started last");
  await page.answer();
  await page.settle(() => island()?.dataset.state === "uploading");
  assert.equal(island()!.textContent, "1 de 1", "the upload is still going");

  later(1000);
  await page.open();
  await page.click(downloadButton());
  await page.settle(() => panel() === null);
  assert.equal(island()!.textContent, "Preparando…");
  later(1000);
  await page.upload("b.jpg");
  await page.settle(() => island()?.dataset.state === "uploading");
  assert.equal(island()!.textContent, "1 de 2", "the newer files come in front of the export");
  await page.finishUpload();
  await page.finishUpload();
  await page.settle(() => island()?.dataset.state === "preparing");
  assert.equal(island()!.textContent, "Preparando…", "the export is still being prepared");
});
