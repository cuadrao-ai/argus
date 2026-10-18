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
import type { ReceiptSummary } from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";

const limits = { max_bytes: 1024, media_types: ["text/plain"] };
const file = (name: string) => new File(["receipt"], name, { type: "text/plain" });
const savedReceipt = (id: string): ReceiptSummary => ({
  id, channel: "web", filename: null, media_type: "text/plain", size_bytes: 7,
  received_at: "2026-10-09T12:00:00Z", status: "saved", error_code: null,
  attention: null, preparable: true, enterable: true, expense_id: null,
  merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null,
});

beforeAll(async () => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
  for (const name of ["ondrop", "ondragover"] as const) {
    if (!(name in HTMLElement.prototype)) {
      Object.defineProperty(HTMLElement.prototype, name, { configurable: true, writable: true, value: null });
    }
  }
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

function context(): BusinessContextValue {
  return {
    source: {},
    records: { workspace: { accounts: [], currencies: [], assistant_available: false, chat_available: false, receipt_limits: limits }, overview: null, inbox: [], notes: [], notesError: false, notesTruncated: false, error: false },
    bridge: null,
  } as unknown as BusinessContextValue;
}

async function mount(queue: ReceiptUploadQueue) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const render = () => root.render(
    <I18nextProvider i18n={i18n}>
      <BusinessContext.Provider value={context()}>
        <ReceiptIntakeDialog target="inbox" queue={queue} onClose={() => undefined} onReview={() => undefined} />
      </BusinessContext.Provider>
    </I18nextProvider>,
  );
  await act(async () => { render(); });
  return {
    host,
    root,
    rerender: async () => { await act(async () => { render(); }); },
    unmount: async () => { await act(async () => { root.unmount(); }); host.remove(); },
  };
}

function surface() {
  return document.body;
}

function choose(files: File[]) {
  const input = surface().querySelector<HTMLInputElement>('input[type="file"]:not([capture])');
  assert.ok(input, "the picker is on the page");
  assert.equal(input.disabled, false, files.map((item) => item.name).join(","));
  const transfer = new DataTransfer();
  for (const item of files) transfer.items.add(item);
  input.files = transfer.files;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

test("a file added while an upload is in flight shows En cola, uploads next, and is still stored after a reload", async () => {
  let releaseA!: (receipt: ReceiptSummary) => void;
  const order: string[] = [];
  const stored: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate) => {
    order.push(candidate.name);
    if (candidate.name === "a.txt") await new Promise<ReceiptSummary>((resolve) => { releaseA = resolve; });
    stored.push(candidate.name);
    return savedReceipt(candidate.name);
  }, () => undefined);
  const page = await mount(queue);
  try {
    await act(async () => { choose([file("a.txt")]); });
    const save = [...surface().querySelectorAll("button")].find((button) => button.textContent === "Guardar los archivos pendientes");
    assert.ok(save, "the owner can start the upload");
    await act(async () => { save.click(); });
    assert.equal(queue.snapshot()[0]?.status, "uploading");
    await act(async () => { choose([file("b.txt")]); });
    const shown = surface().textContent ?? "";
    assert.equal(shown.includes("Espera a que termine la subida actual"), false);
    assert.match(shown, /b\.txt/);
    assert.match(shown, /En cola/);
    releaseA(savedReceipt("a.txt"));
    for (let turn = 0; order.length < 2 && turn < 20; turn += 1) {
      await act(async () => { await Promise.resolve(); });
    }
    assert.deepEqual(order, ["a.txt", "b.txt"]);
  } finally {
    await page.unmount();
  }
  const afterReload = stored.slice();
  assert.deepEqual(afterReload, ["a.txt", "b.txt"]);
});
