import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, beforeEach, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import ManualCaptureDialog from "@/components/business-app/ManualCaptureDialog";
import ReceiptIntakeDialog from "@/components/business-app/ReceiptIntakeDialog";
import { ReceiptUploadQueue } from "@/components/business-app/receipt-upload-queue";
import { TypedNoteQueue } from "@/components/business-app/typed-note-queue";
import * as api from "@/lib/business-api";
import { GRANT_HEADER, setChosenGrant } from "@/lib/business-grant";
import spanish from "@/public/locales/es-419/common.json";

// A Business write carries the Business the person acted in. Authentication is awaited before the request
// goes out, and the person can switch Business in that gap; a queued note or file can wait far longer. The
// request must still carry the grant chosen when they acted, never the one chosen when it is sent.
const A = "aaaaaaaa-0000-4000-8000-000000000001";
const B = "bbbbbbbb-0000-4000-8000-000000000002";
const limits = { max_bytes: 1024, media_types: ["text/plain"] };
const file = (name = "recibo.txt") => new File(["recibo"], name, { type: "text/plain" });
const sent: { path: string; grant: string | null }[] = [];
let loseNext = false;
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
let originalXhr: unknown;

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  // Without XMLHttpRequest an upload goes over fetch, where the stub below reads its headers.
  originalXhr = globalThis.XMLHttpRequest;
  Object.defineProperty(globalThis, "XMLHttpRequest", { configurable: true, writable: true, value: undefined });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    sent.push({ path: new URL(request.url).pathname, grant: request.headers.get(GRANT_HEADER) });
    if (loseNext) {
      loseNext = false;
      throw new TypeError("Failed to fetch");
    }
    if (request.url.includes("/business/exports")) return new Response(new Blob(["zip"]), { headers: { "Content-Type": "application/zip" } });
    return Response.json({ draft_id: "draft-a", id: "receipt-a" });
  }) as typeof fetch;
});
beforeEach(() => { sent.length = 0; loseNext = false; setChosenGrant(A); });
afterEach(() => { document.body.innerHTML = ""; });
afterAll(async () => {
  globalThis.fetch = originalFetch;
  Object.defineProperty(globalThis, "XMLHttpRequest", { configurable: true, writable: true, value: originalXhr });
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  setChosenGrant(null);
  await GlobalRegistrator.unregister();
});

/** The person acts in A, and switches to B while the write still waits for authentication. */
async function actInAThenSwitchToB(write: () => Promise<unknown>) {
  const pending = write();
  setChosenGrant(B);
  await pending;
}
const until = async (ready: () => boolean) => {
  for (let i = 0; i < 100 && !ready(); i += 1) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.ok(ready(), "the queue settled");
};

test.each([
  ["a record note", () => api.captureBusinessNote({ text: "Pagué RD$900 de flete" }, "note-key")],
  ["an upload", () => api.uploadBusinessReceipt(file(), false, "upload-key")],
  ["a draft approval", () => api.approveBusinessDraft("draft-a", 1, "approve-key", "record_expense")],
  ["a Listos approval", () => api.approveBusinessListos([], "listos-key")],
  ["a receipt confirmation", () => api.confirmBusinessReceipt("receipt-a", 1, "confirm-key")],
  ["a receipt preparation", () => api.prepareBusinessReceipt("receipt-a")],
  ["an access cue dismissal", () => api.markBusinessAccessSeen("grant-a")],
] as const)("%s entered in Business A carries A's grant when the person switches to B before authentication answers", async (_name, write) => {
  await actInAThenSwitchToB(write);
  assert.deepEqual(sent.map((request) => request.grant), [A]);
});

test("an export entered in A refuses to send once the person has switched to B", async () => {
  await assert.rejects(actInAThenSwitchToB(() => api.fetchBusinessExport(undefined, "2026-01-01", "2026-01-31")), { message: "Business selection changed" });
  assert.deepEqual(sent, []);
});

test("a typed note saved in A carries A's grant when the person switches to B before authentication answers", async () => {
  const notes = new TypedNoteQueue(() => undefined);
  await actInAThenSwitchToB(() => notes.add({ grant: A, text: "Compré gasoil", documentType: "recibo" }, (input, key, grant) => api.captureBusinessNote(input, key, grant)));
  assert.deepEqual(sent.map((request) => request.grant), [A]);
  assert.equal(notes.snapshot()[0].status, "saved");
});

test("a typed note retried after the person moved to B still goes to A, where it was typed", async () => {
  const notes = new TypedNoteQueue(() => undefined);
  const capture = (input: Parameters<typeof api.captureBusinessNote>[0], key: string, grant: string | null) => api.captureBusinessNote(input, key, grant);
  loseNext = true;
  await notes.add({ grant: A, text: "Vendí cemento", documentType: "venta" }, capture);
  assert.equal(notes.snapshot()[0].status, "uncertain");
  setChosenGrant(B);
  await notes.retry(notes.snapshot()[0].key, capture);
  assert.deepEqual(sent.map((request) => request.grant), [A, A]);
  assert.equal(notes.snapshot()[0].status, "saved");
});

test("a file added in A uploads to A when the person switches to B before it is sent", async () => {
  const queue = new ReceiptUploadQueue((candidate, consent, key, documentType, onProgress, grant) => api.uploadBusinessReceipt(candidate, consent, key, documentType, onProgress, grant), () => undefined);
  queue.add([file()], limits, "inbox", null, null, A);
  await actInAThenSwitchToB(() => queue.save("inbox", false));
  assert.deepEqual(sent.map((request) => request.grant), [A]);
  assert.equal(queue.snapshot()[0].status, "saved");
});

test("a file that failed in A retries to A after the person moved to B", async () => {
  const queue = new ReceiptUploadQueue((candidate, consent, key, documentType, onProgress, grant) => api.uploadBusinessReceipt(candidate, consent, key, documentType, onProgress, grant), () => undefined);
  loseNext = true;
  queue.add([file()], limits, "inbox", null, null, A);
  await queue.save("inbox", false);
  assert.equal(queue.snapshot()[0].status, "failed");
  setChosenGrant(B);
  queue.retry(queue.snapshot()[0].key);
  await until(() => queue.snapshot()[0].status === "saved");
  assert.deepEqual(sent.map((request) => request.grant), [A, A]);
});

async function mount(element: () => ReactElement, source: Partial<BusinessContextValue["source"]>) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const context = {
    source,
    records: { workspace: { accounts: [], currencies: [], assistant_available: false, chat_available: false, receipt_limits: limits }, overview: null, inbox: [], notes: [], notesError: false, notesTruncated: false, error: false },
    bridge: null,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>{element()}</BusinessContext.Provider></I18nextProvider>); });
  return { unmount: () => act(async () => root.unmount()) };
}
const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent === text || item.getAttribute("aria-label") === text);

test("the Agregar picker hands the queue the Business it is open in, and a retry keeps it after a switch", async () => {
  const uploads: (string | null)[] = [];
  let lose = true;
  const queue = new ReceiptUploadQueue(async (_file, _consent, _key, _type, _onProgress, grant) => {
    uploads.push(grant);
    if (lose) { lose = false; throw new TypeError("Failed to fetch"); }
    return { id: "receipt-a" } as unknown as api.ReceiptSummary;
  }, () => undefined);
  const page = await mount(() => <ReceiptIntakeDialog target="inbox" notes={new TypedNoteQueue(() => undefined)} queue={queue} onClose={() => undefined} onReview={() => undefined} />, {});
  const input = document.querySelector<HTMLInputElement>('input[type="file"]:not([capture])')!;
  const transfer = new DataTransfer();
  transfer.items.add(file());
  await act(async () => { input.files = transfer.files; input.dispatchEvent(new Event("change", { bubbles: true })); });
  await until(() => queue.snapshot()[0]?.status === "failed");
  await act(async () => { setChosenGrant(B); });
  await act(async () => { button("Reintentar recibo.txt")!.click(); });
  await until(() => queue.snapshot()[0]?.status === "saved");
  assert.deepEqual(uploads, [A, A]);
  await page.unmount();
});

test("a record note retried after the person moved to B still goes to A, where it was written", async () => {
  const captures: (string | null | undefined)[] = [];
  let lose = true;
  const captureNote = async (_input: unknown, _key: string, grant?: string | null) => {
    captures.push(grant);
    if (lose) { lose = false; throw new TypeError("Failed to fetch"); }
    return { draft_id: "draft-a" } as Awaited<ReturnType<typeof api.captureBusinessNote>>;
  };
  const page = await mount(() => <ManualCaptureDialog isOpen onClose={() => undefined} onSaved={() => undefined} />, { captureNote });
  const field = document.querySelector<HTMLTextAreaElement>("textarea")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, "Pagué RD$900 de flete");
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { button("Guardar nota")!.click(); });
  assert.ok(button("Reintentar la misma nota"), "the note waits for its retry");
  await act(async () => { setChosenGrant(B); });
  await act(async () => { button("Reintentar la misma nota")!.click(); });
  assert.deepEqual(captures, [A, A]);
  await page.unmount();
});
