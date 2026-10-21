import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import ReceiptIntakeDialog from "@/components/business-app/ReceiptIntakeDialog";
import PanelErrorBoundary from "@/components/business-app/PanelErrorBoundary";
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

function drop(files: File[]) {
  const zone = surface().querySelector("div.border-dashed");
  assert.ok(zone, "the drop zone is on the page");
  const transfer = new DataTransfer();
  for (const item of files) transfer.items.add(item);
  for (const type of ["dragover", "drop"] as const) {
    const event = new DragEvent(type, { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: transfer });
    zone.dispatchEvent(event);
  }
}

test("a file added by picker or drop while another uploads starts at once, shows En espera, omits the wait warning, and stays across a rerender", async () => {
  let releaseA!: (receipt: ReceiptSummary) => void;
  const order: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate) => {
    order.push(candidate.name);
    if (candidate.name === "a.txt") await new Promise<ReceiptSummary>((resolve) => { releaseA = resolve; });
    return savedReceipt(candidate.name);
  }, () => undefined);
  let page = await mount(queue);
  try {
    assert.match(surface().textContent ?? "", /Arrastra tus recibos aquí/);
    await act(async () => { choose([file("a.txt")]); });
    assert.equal([...surface().querySelectorAll("button")].some((button) => /Guardar/.test(button.textContent ?? "")), false, "there is no save button to press");
    assert.equal(queue.snapshot()[0]?.status, "uploading", "a chosen file starts uploading on its own");
    await act(async () => { choose([file("b.txt")]); });
    await act(async () => { drop([file("c.txt")]); });
    const shown = surface().textContent ?? "";
    assert.equal(shown.includes("Espera a que termine la subida actual"), false);
    assert.match(shown, /b\.txt/);
    assert.match(shown, /c\.txt/);
    assert.match(shown, /En espera/);
    assert.equal(shown.includes("En cola"), false);
    await page.unmount();
    const remounted = await mount(queue);
    page = remounted;
    const again = surface().textContent ?? "";
    assert.equal(again.includes("Espera a que termine la subida actual"), false);
    assert.match(again, /b\.txt/);
    assert.match(again, /c\.txt/);
    assert.match(again, /En espera/);
    releaseA(savedReceipt("a.txt"));
    for (let turn = 0; order.length < 3 && turn < 20; turn += 1) {
      await act(async () => { await Promise.resolve(); });
    }
    assert.deepEqual(order, ["a.txt", "b.txt", "c.txt"]);
    assert.deepEqual(queue.snapshot().map((item) => item.status), ["saved", "saved", "saved"]);
  } finally {
    await page.unmount();
  }
});

test("a panel crash keeps the note and the upload that live above it", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  function Boom() {
    throw new Error("framework render");
  }
  function Holder() {
    return (
      <div>
        <input aria-label="note" defaultValue="factura 42" />
        <p>recibo.png</p>
        <PanelErrorBoundary><Boom /></PanelErrorBoundary>
      </div>
    );
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const errors: unknown[] = [];
  const previous = console.error;
  console.error = (...args: unknown[]) => { errors.push(args); };
  try {
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <Holder />
        </I18nextProvider>,
      );
    });
    const shown = host.textContent ?? "";
    assert.match(shown, /Algo salió mal de nuestro lado\./);
    assert.match(shown, /recibo\.png/);
    assert.equal((host.querySelector("input") as HTMLInputElement).value, "factura 42");
    assert.equal(shown.includes("framework render"), false);
  } finally {
    console.error = previous;
    await act(async () => { root.unmount(); });
    host.remove();
  }
});

test("an offline upload keeps the file and offers another try", async () => {
  const keys: string[] = [];
  const queue = new ReceiptUploadQueue(async (_candidate, _consent, key) => {
    keys.push(key);
    throw new TypeError("Failed to fetch");
  }, () => undefined);
  const page = await mount(queue);
  try {
    await act(async () => { choose([file("recibo.txt")]); });
    const row = surface().querySelector('[data-testid="receipt-upload-row"]');
    assert.equal(row?.getAttribute("data-status"), "failed");
    const shown = surface().textContent ?? "";
    assert.match(shown, /Se perdió la conexión\. Tu archivo sigue aquí\./);
    assert.match(shown, /recibo\.txt/);
    assert.equal(queue.snapshot()[0]?.status, "failed");
    const retry = surface().querySelector<HTMLButtonElement>('button[aria-label="Reintentar recibo.txt"]');
    assert.ok(retry, "the row offers another try");
    assert.equal(queue.snapshot()[0]?.file.name, "recibo.txt");
    await act(async () => { retry.click(); });
    assert.equal(keys.length, 2, "the retry sends the file again");
    assert.equal(keys[1], keys[0], "with the same upload key, so it is never saved twice");
  } finally {
    await page.unmount();
  }
});

test("a 503 upload ends on the server screen and keeps the file", async () => {
  const queue = new ReceiptUploadQueue(async () => {
    throw Object.assign(new Error("unavailable"), { status: 503 });
  }, () => undefined);
  const page = await mount(queue);
  try {
    await act(async () => { choose([file("factura.txt")]); });
    const shown = surface().textContent ?? "";
    assert.match(shown, /Algo salió mal de nuestro lado\./);
    assert.match(shown, /factura\.txt/);
    assert.match(shown, /hola@cuadrao\.ai/);
    assert.equal(shown.includes("unavailable"), false);
    assert.equal(queue.snapshot()[0]?.file.name, "factura.txt");
  } finally {
    await page.unmount();
  }
});
