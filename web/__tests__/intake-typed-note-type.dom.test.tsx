import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

// A typed note prints no RNC, so the server's rule (resolved_document_type with no issuer) makes it a Compra.
// "Automático" would turn every typed sale into a purchase: a typed note names its own type before it is saved.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount() {
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
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const notes: { text: string; document_type?: string }[] = [];
  const context = {
    source: {
      captureNote: async (body: { text: string; document_type?: string }) => { notes.push(body); return {}; },
      receiptReading: async () => ({ enabled: true, can_change: true, available: true, disclosure: "" }),
    },
    records: { workspace: { accounts: [], currencies: [], assistant_available: false, chat_available: false, receipt_limits: { max_bytes: 1024, media_types: ["image/jpeg"] } }, overview: null, inbox: [], notes: [], notesTruncated: false, error: false },
    bridge: null,
    reload: () => undefined,
  } as unknown as BusinessContextValue;
  const queue = new ReceiptUploadQueue(async () => { throw new Error("no upload here"); }, () => undefined);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessContext.Provider value={context}><ReceiptIntakeDialog target="inbox" notes={new TypedNoteQueue(() => undefined)} queue={queue} onClose={() => undefined} onReview={() => undefined} /></BusinessContext.Provider></BusinessConsentTestProvider></I18nextProvider>);
  });
  // While Escríbelo is open its own choice sits in the card; uploads keep "Se guardan como".
  const typeControl = () => document.querySelector('[data-testid="intake-write-type"]') ?? document.querySelector('[data-testid="intake-document-type"]')!;
  const segments = () => [...typeControl().querySelectorAll<HTMLElement>('[role="radio"], button')].map((item) => ({ label: item.textContent, checked: item.getAttribute("aria-checked") === "true" || item.getAttribute("aria-pressed") === "true" }));
  const click = (selector: string) => act(async () => document.querySelector<HTMLElement>(selector)!.click());
  const type = async (value: string) => {
    const field = document.querySelector<HTMLTextAreaElement>("#intake-write-text")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, value);
      field.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  const choose = (label: string) => act(async () => [...typeControl().querySelectorAll<HTMLElement>("button")].find((item) => item.textContent === label)!.click());
  return { act, root, notes, segments, click, type, choose, help: () => document.querySelector('[data-testid="intake-type-help"]')?.textContent ?? null, save: () => document.querySelector<HTMLButtonElement>('[data-testid="intake-write-save"]')! };
}

test("file uploads keep Automático, chosen by default, with the RNC rule beside it", async () => {
  const page = await mount();
  assert.deepEqual(page.segments().map((segment) => segment.label), ["Automático", "Compra", "Venta"]);
  assert.equal(page.segments().find((segment) => segment.checked)?.label, "Automático");
  assert.match(page.help() ?? "", /RNC/);
  await page.act(async () => page.root.unmount());
});

test("a typed note asks Compra or Venta inside its card, none chosen, and saves only with text and a choice", async () => {
  const page = await mount();
  await page.click('[data-testid="intake-write-open"]');
  const card = document.querySelector('[data-testid="intake-write"]')!;
  assert.ok(card.querySelector('[data-testid="intake-write-type"]'), "the choice sits inside the Escríbelo card");
  assert.match(card.textContent ?? "", /¿Es una compra o una venta\?/);
  const choice = card.querySelector('[data-testid="intake-write-type"]')!;
  assert.ok(choice.compareDocumentPosition(page.save()) & Node.DOCUMENT_POSITION_FOLLOWING, "Guardar follows the choice");
  assert.equal(document.querySelector('[data-testid="intake-document-type"]'), null, "Se guardan como is not shown while writing");
  assert.doesNotMatch(document.body.textContent ?? "", /Se guardan como/);
  assert.deepEqual(page.segments().map((segment) => segment.label), ["Compra", "Venta"]);
  assert.equal(page.segments().some((segment) => segment.checked), false, "no type is chosen for the person");
  assert.doesNotMatch(document.body.textContent ?? "", /RNC/, "the RNC rule does not apply to a typed note");
  assert.equal(page.save().disabled, true, "no text and no choice");
  await page.choose("Venta");
  assert.equal(page.save().disabled, true, "a choice without text waits");
  await page.type("   ");
  assert.equal(page.save().disabled, true, "blank text waits");
  await page.type("Vendí 3 sacos de cemento a RD$1,500");
  assert.equal(page.save().disabled, false, "text and a choice");
  await page.act(async () => page.save().click());
  await page.act(async () => { await Promise.resolve(); });
  assert.deepEqual(page.notes, [{ text: "Vendí 3 sacos de cemento a RD$1,500", document_type: "venta" }]);
  await page.click('[data-testid="intake-write-open"]');
  assert.equal(page.segments().some((segment) => segment.checked), false, "the next note starts unchosen again");
  await page.type("Compré gasoil por RD$500 en efectivo");
  assert.equal(page.save().disabled, true, "text without Compra or Venta waits");
  await page.act(async () => page.save().click());
  assert.equal(page.notes.length, 1, "nothing is saved until Compra or Venta is chosen");
  await page.act(async () => page.root.unmount());
});

test("the reading line shows for file uploads and not for a typed note, which nothing reads", async () => {
  const spanishBack = (await import("@/public/locales/es-419/common.json")).default.business.intake.write_back;
  const page = await mount();
  const reading = () => (document.body.textContent ?? "").includes("La lectura de documentos está activada");
  await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  assert.equal(reading(), true, "uploads say reading is on");
  await page.click('[data-testid="intake-write-open"]');
  await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  assert.equal(reading(), false, "a typed note is never read, so the line does not apply");
  await page.act(async () => [...document.querySelectorAll<HTMLButtonElement>('[data-testid="intake-write"] button')].find((button) => button.textContent === spanishBack)!.click());
  await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  assert.equal(reading(), true, "back to files, the line returns");
  await page.act(async () => page.root.unmount());
});

test("a typed note shows the record-note counter and stops at 500 characters", async () => {
  const page = await mount();
  await page.click('[data-testid="intake-write-open"]');
  const counter = () => document.querySelector("#intake-write-text-count")?.textContent ?? null;
  assert.equal(counter(), "0/500");
  assert.equal(document.querySelector("#intake-write-text")!.getAttribute("aria-describedby")?.includes("intake-write-text-count"), true);
  await page.type("🟢".repeat(501));
  assert.equal(document.querySelector<HTMLTextAreaElement>("#intake-write-text")!.value, "🟢".repeat(500), "typing stops at 500");
  assert.equal(counter(), "500/500");
  await page.act(async () => page.root.unmount());
});

test("the note box starts at six lines, grows with its text and stops where a full note fits, with no animation", async () => {
  const { noteBoxHeight } = await import("@/components/business-app/NoteCount");
  const box = { lineHeight: 26, chrome: 26, textWidth: 380, charWidth: 8 };
  // 380px at 8px a character is 47 characters a line: 500 characters fill 11 lines, plus one for a short last word.
  assert.deepEqual(noteBoxHeight({ ...box, content: 60 }), { height: 6 * 26 + 26, overflow: false }, "short text keeps six lines");
  assert.deepEqual(noteBoxHeight({ ...box, content: 9 * 26 + 26 }), { height: 9 * 26 + 26, overflow: false }, "longer text grows the box");
  assert.deepEqual(noteBoxHeight({ ...box, content: 40 * 26 }), { height: 12 * 26 + 26, overflow: true }, "the box stops at the full-note height");
  assert.deepEqual(noteBoxHeight({ ...box, textWidth: 300, content: 40 * 26 }), { height: 15 * 26 + 26, overflow: true }, "a narrower sheet allows more lines");

  const page = await mount();
  await page.click('[data-testid="intake-write-open"]');
  const field = document.querySelector<HTMLTextAreaElement>("#intake-write-text")!;
  assert.doesNotMatch(field.className, /transition/, "the growth is never animated");
  assert.match(field.className, /resize-none/);
  let content = 0;
  Object.defineProperty(field, "scrollHeight", { configurable: true, get: () => content });
  Object.defineProperty(field, "clientWidth", { configurable: true, get: () => 400 });
  content = 20 * 40;
  await page.type("🟢".repeat(500));
  const grown = parseFloat(field.style.height);
  assert.ok(grown > 0, "the box takes a height from its text");
  assert.equal(field.style.overflowY, "auto", "only text past a full note scrolls");
  content = 10;
  await page.type("corto");
  assert.ok(parseFloat(field.style.height) < grown, "it shrinks back with less text");
  assert.equal(field.style.overflowY, "hidden");
  await page.act(async () => page.root.unmount());
});
