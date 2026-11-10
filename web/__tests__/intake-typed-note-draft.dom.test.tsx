import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, beforeEach, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { TypedNoteQueue } from "@/components/business-app/typed-note-queue";

// The workspace owns a typed note from its first letter: closing Agregar, or switching Business and back,
// keeps the unsaved text and its Compra or Venta until it is saved or the page goes.
const A = "aaaaaaaa-0000-4000-8000-000000000001";
const B = "bbbbbbbb-0000-4000-8000-000000000002";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
beforeEach(async () => { (await import("@/lib/business-grant")).setChosenGrant(A); });
afterEach(async () => {
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => {
  (await import("@/lib/business-grant")).setChosenGrant(null);
  await GlobalRegistrator.unregister();
});

async function workspace() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const ReceiptIntakeDialog = (await import("@/components/business-app/ReceiptIntakeDialog")).default;
  const { TypedNoteQueue } = await import("@/components/business-app/typed-note-queue");
  const { ReceiptUploadQueue } = await import("@/components/business-app/receipt-upload-queue");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const saved: { text: string; document_type?: string }[] = [];
  const context = {
    source: {
      captureNote: async (body: { text: string; document_type?: string }) => { saved.push(body); return {}; },
      receiptReading: async () => ({ enabled: true, can_change: true, available: true, disclosure: "" }),
    },
    records: { workspace: { accounts: [], currencies: [], assistant_available: false, chat_available: false, receipt_limits: { max_bytes: 1024, media_types: ["image/jpeg"] } }, overview: null, inbox: [], notes: [], notesTruncated: false, error: false },
    bridge: null,
    reload: () => undefined,
  } as unknown as BusinessContextValue;
  // Like the mounted workspace: one note queue and one upload queue outlive every opening of Agregar.
  const notes: TypedNoteQueue = new TypedNoteQueue(() => undefined);
  const queue = new ReceiptUploadQueue(async () => { throw new Error("no upload here"); }, () => undefined);
  const root = createRoot(document.body.appendChild(document.createElement("div")));
  const render = (open: boolean) => act(async () => {
    root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessContext.Provider value={context}><ReceiptIntakeDialog target={open ? "inbox" : null} notes={notes} queue={queue} onClose={() => undefined} onReview={() => undefined} /></BusinessContext.Provider></BusinessConsentTestProvider></I18nextProvider>);
  });
  await render(true);
  const box = () => document.querySelector<HTMLTextAreaElement>("#intake-write-text");
  const typeControl = () => document.querySelector('[data-testid="intake-write-type"]');
  return {
    act,
    notes,
    saved,
    open: () => render(true),
    close: () => render(false),
    choose: (grant: string) => act(async () => setChosenGrant(grant)),
    write: () => act(async () => document.querySelector<HTMLElement>('[data-testid="intake-write-open"]')!.click()),
    type: (value: string) => act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(box()!, value);
      box()!.dispatchEvent(new Event("input", { bubbles: true }));
    }),
    pick: (label: string) => act(async () => [...typeControl()!.querySelectorAll<HTMLElement>("button")].find((item) => item.textContent === label)!.click()),
    save: () => act(async () => { document.querySelector<HTMLButtonElement>('[data-testid="intake-write-save"]')!.click(); await Promise.resolve(); }),
    text: () => box()?.value ?? null,
    count: () => document.querySelector("#intake-write-text-count")?.textContent ?? null,
    picked: () => [...(typeControl()?.querySelectorAll<HTMLElement>("button") ?? [])].find((item) => item.getAttribute("aria-checked") === "true" || item.getAttribute("aria-pressed") === "true")?.textContent ?? null,
    unmount: () => act(async () => root.unmount()),
  };
}

test("an unsaved note keeps its text and Compra or Venta when Agregar closes and opens again", async () => {
  const page = await workspace();
  await page.write();
  await page.type("Prueba QA");
  await page.pick("Venta");
  await page.close();
  assert.equal(page.text(), null, "Agregar is closed");
  await page.open();
  assert.equal(page.text(), "Prueba QA", "Agregar opens on the note it was left with");
  assert.equal(page.count(), "9/500");
  assert.equal(page.picked(), "Venta");
  await page.unmount();
});

test("saving a note clears it, so the next Escríbelo starts empty and unchosen", async () => {
  const page = await workspace();
  await page.write();
  await page.type("Vendí cemento");
  await page.pick("Venta");
  await page.save();
  assert.deepEqual(page.saved, [{ text: "Vendí cemento", document_type: "venta" }]);
  await page.close();
  await page.open();
  assert.equal(page.text(), null, "with nothing unsaved, Agregar opens on its files");
  await page.write();
  assert.equal(page.text(), "");
  assert.equal(page.count(), "0/500");
  assert.equal(page.picked(), null);
  await page.unmount();
});

test("each Business keeps its own unsaved note and never shows another Business's", async () => {
  const page = await workspace();
  await page.write();
  await page.type("Nota de A");
  await page.pick("Compra");
  await page.choose(B);
  assert.equal(page.text(), "", "B does not see A's note");
  assert.equal(page.picked(), null);
  await page.type("Nota de B");
  await page.close();
  await page.choose(A);
  await page.open();
  assert.equal(page.text(), "Nota de A");
  assert.equal(page.picked(), "Compra");
  await page.choose(B);
  assert.equal(page.text(), "Nota de B");
  assert.equal(page.picked(), null);
  await page.unmount();
});

test("leaving the page asks first while a note is typed and not saved", async () => {
  const { intakeWork } = await import("@/components/business-app/intake-work");
  const page = await workspace();
  const leaveGuard = intakeWork([page.notes]);
  let heard = 0;
  leaveGuard.subscribe(() => { heard += 1; });
  await page.write();
  await page.type("   ");
  assert.equal(leaveGuard.unfinished(), false, "blank text has nothing to lose");
  heard = 0;
  await page.type("Prueba QA");
  assert.equal(leaveGuard.unfinished(), true, "typed text would be lost");
  assert.ok(heard > 0, "the guard hears the typing, so it arms without waiting for another change");
  await page.close();
  assert.equal(leaveGuard.unfinished(), true, "closing Agregar does not save it");
  await page.open();
  await page.pick("Compra");
  await page.save();
  await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  assert.equal(leaveGuard.unfinished(), false, "a saved note leaves nothing behind");
  await page.unmount();
});
