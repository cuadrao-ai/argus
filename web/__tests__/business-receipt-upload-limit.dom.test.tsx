import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import ReceiptIntakeDialog from "@/components/business-app/ReceiptIntakeDialog";
import { ReceiptUploadQueue } from "@/components/business-app/receipt-upload-queue";
import { retryAfterMs, uploadBusinessReceipt, type ReceiptSummary } from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";

const limits = { max_bytes: 1024, media_types: ["image/jpeg"] };
const names = Array.from({ length: 9 }, (_, index) => `recibo-${index + 1}.jpg`);
const original = { xhr: undefined as unknown, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  original.xhr = globalThis.XMLHttpRequest;
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => {
  if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
  Object.defineProperty(globalThis, "XMLHttpRequest", { configurable: true, writable: true, value: original.xhr });
  await GlobalRegistrator.unregister();
});

type FakeReply = { status: number; body: unknown; headers?: Record<string, string> };

/** The upload dialog sends bytes over XMLHttpRequest so it can show progress; this stands in for the server. */
function fakeXhr(respond: (request: { url: string; method: string; headers: Headers }) => FakeReply) {
  return class FakeXhr {
    upload: { onprogress: ((event: { loaded: number; total: number; lengthComputable: boolean }) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onabort: (() => void) | null = null;
    withCredentials = false;
    status = 0;
    responseText = "";
    private url = "";
    private method = "";
    private sent = new Headers();
    private received = new Headers();
    open(method: string, url: string) { this.method = method; this.url = url; }
    setRequestHeader(name: string, value: string) { this.sent.set(name, value); }
    getResponseHeader(name: string) { return this.received.get(name); }
    send() {
      queueMicrotask(() => {
        const reply = respond({ url: this.url, method: this.method, headers: this.sent });
        this.status = reply.status;
        this.responseText = JSON.stringify(reply.body);
        for (const [name, value] of Object.entries(reply.headers ?? {})) this.received.set(name, value);
        this.onload?.();
      });
    }
  };
}

function saved(id: string, filename: string): ReceiptSummary {
  return {
    id, channel: "web", filename, media_type: "image/jpeg", size_bytes: 7,
    received_at: "2026-10-19T12:00:00Z", status: "saved", error_code: null,
    attention: null, preparable: true, enterable: true, expense_id: null,
    merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null,
  };
}

const text = () => document.body.textContent ?? "";

test("nine files under the upload limit wait out Retry-After, retry the same file and all save", async () => {
  const requests: { filename: string; key: string | null; at: number }[] = [];
  let limitedOnce = false;
  let limited!: () => void;
  const sawLimit = new Promise<void>((resolve) => { limited = resolve; });
  Object.defineProperty(globalThis, "XMLHttpRequest", { configurable: true, writable: true, value: fakeXhr((request) => {
    assert.ok(new URL(request.url).pathname.endsWith("/business/receipts"), request.url);
    assert.equal(request.method, "POST");
    const filename = decodeURIComponent(request.headers.get("X-Document-Filename") ?? "");
    requests.push({ filename, key: request.headers.get("Idempotency-Key"), at: Date.now() });
    if (filename === "recibo-6.jpg" && !limitedOnce) {
      limitedOnce = true;
      limited();
      return {
        status: 429,
        body: { code: "document_rate_limited", title: "Too Many Requests", detail: "Wait before uploading another document." },
        headers: { "Retry-After": "1" },
      };
    }
    return { status: 201, body: saved(`receipt-${requests.length}`, filename) };
  }) });
  const queue = new ReceiptUploadQueue(uploadBusinessReceipt, () => undefined);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const context = {
    source: {},
    records: { workspace: { accounts: [], currencies: [], assistant_available: false, chat_available: false, receipt_limits: limits }, overview: null, inbox: [], notes: [], notesError: false, notesTruncated: false, error: false },
    bridge: null,
  } as unknown as BusinessContextValue;
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={context}>
          <ReceiptIntakeDialog target="inbox" queue={queue} onClose={() => undefined} onReview={() => undefined} />
        </BusinessContext.Provider>
      </I18nextProvider>,
    );
  });
  try {
    const input = host.ownerDocument.querySelector<HTMLInputElement>('input[type="file"]:not([capture])');
    assert.ok(input, "the picker is on the page");
    const transfer = new DataTransfer();
    for (const name of names) transfer.items.add(new File([name], name, { type: "image/jpeg" }));
    await act(async () => {
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    assert.equal([...document.querySelectorAll("button")].some((button) => /Guardar/.test(button.textContent ?? "")), false, "there is no save button to press");
    await act(async () => { await sawLimit; });

    assert.match(text(), /Subiendo 6 de 9…/);
    assert.equal(text().includes("No pudimos leer el recibo"), false, "the limit is never shown as an unreadable receipt");
    assert.equal(queue.snapshot().some((item) => item.status === "failed"), false);

    for (let turn = 0; queue.uploading && turn < 60; turn += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
    }
    assert.equal(queue.uploading, false, "the drain finished on its own");
    assert.deepEqual(queue.snapshot().map((item) => item.status), Array(9).fill("saved"));
    assert.deepEqual(requests.map((item) => item.filename), [...names.slice(0, 6), ...names.slice(5)]);
    const [first, retry] = requests.filter((item) => item.filename === "recibo-6.jpg");
    assert.equal(retry.key, first.key, "the retry reuses the upload key, so it never saves twice");
    assert.ok(retry.at - first.at >= 1000, `waited ${retry.at - first.at}ms for Retry-After: 1`);
    assert.equal(text().includes("No pudimos leer el recibo"), false);
    assert.equal(text().includes("Subiendo"), false, "progress leaves once every file is saved");
  } finally {
    await act(async () => { root.unmount(); });
    host.remove();
  }
});

test("Retry-After reads seconds and HTTP dates, and nothing else", () => {
  const now = Date.parse("2026-10-19T12:00:00Z");
  assert.equal(retryAfterMs("3", now), 3000);
  assert.equal(retryAfterMs("Mon, 19 Oct 2026 12:00:30 GMT", now), 30_000);
  assert.equal(retryAfterMs("Mon, 19 Oct 2026 11:00:00 GMT", now), 0);
  assert.equal(retryAfterMs(null, now), null);
  assert.equal(retryAfterMs("soon", now), null);
});
