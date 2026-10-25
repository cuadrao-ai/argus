import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import type { LocalInvitation } from "@/components/sidebar/CuadraoInvitationPreview";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
const click = async (node: Element | null | undefined) => { assert.ok(node); await act(async () => (node as HTMLElement).click()); };
const button = (text: string) => [...document.querySelectorAll("button")].find((node) => node.textContent === text);
async function mount(width = 1280, language = "es-419") {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { default: Preview } = await import("@/components/sidebar/CuadraoInvitationPreview");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const en = (await import("@/public/locales/en/common.json")).default;
  await i18n.init({ lng: language, resources: { "es-419": { translation: es }, en: { translation: en } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.append(host);
  const opener = document.createElement("button"); opener.textContent = "Open"; document.body.append(opener); opener.focus();
  const returnFocusRef = { current: opener };
  let recorded: LocalInvitation[] = [];
  function Harness() {
    const [open, setOpen] = useState(true);
    const [rows, setRows] = useState<LocalInvitation[]>([]);
    return <I18nextProvider i18n={i18n}>{open ? <Preview invitations={rows} onSent={(row) => setRows((old) => { recorded = [...old, row]; return recorded; })} onClose={() => setOpen(false)} returnFocusRef={returnFocusRef} /> : null}</I18nextProvider>;
  }
  const root = createRoot(host);
  await act(async () => root.render(<Harness />));
  return { opener, records: () => recorded, cleanup: async () => { await act(async () => root.unmount()); host.remove(); opener.remove(); } };
}
async function enter(value: string) {
  const input = document.querySelector<HTMLInputElement>('input[type="email"]'); assert.ok(input);
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); });
  return input;
}
async function finishSend() { await act(async () => new Promise((resolve) => setTimeout(resolve, 320))); }

for (const width of [1280, 390]) {
  test(`invitation history starts empty and preserves a draft at ${width}px`, async () => {
    const page = await mount(width);
    try {
      assert.equal(document.querySelector('[data-testid="referral-sent-count"]')?.textContent, "0");
      assert.equal(document.querySelector('[data-testid="referral-joined-count"]')?.textContent, "0");
      await enter("draft@example.test"); await click(button("Historial de invitaciones"));
      assert.match(document.body.textContent ?? "", /Tus invitaciones empiezan aquí/);
      assert.equal(document.activeElement, button("Volver a la invitación"));
      await click(button("Volver a la invitación"));
      assert.equal(document.querySelector<HTMLInputElement>('input[type="email"]')?.value, "draft@example.test");
      assert.equal(document.activeElement, button("Historial de invitaciones"));
    } finally { await page.cleanup(); }
  });
}

test("email validation and local sends update one pending row, reset and reject duplicates", async () => {
  const page = await mount();
  try {
    await enter("wrong"); await click(button("Enviar"));
    assert.equal(page.records().length, 0);
    assert.equal(document.querySelector('input[type="email"]')?.getAttribute("aria-invalid"), "true");
    await enter("ANA@example.test"); await click(button("Enviar"));
    assert.equal(document.querySelector("form")?.getAttribute("aria-busy"), "true");
    assert.equal(document.querySelector<HTMLInputElement>('input[type="email"]')?.readOnly, true);
    await finishSend();
    assert.equal(page.records().length, 1); assert.equal(page.records()[0].status, "pending");
    assert.equal(document.querySelector('[data-testid="referral-sent-count"]')?.textContent, "1");
    assert.equal(document.querySelector('[data-testid="referral-joined-count"]')?.textContent, "0");
    assert.equal(document.querySelector<HTMLInputElement>('input[type="email"]')?.value, "");
    assert.equal(document.activeElement, document.querySelector('input[type="email"]'));
    await enter("ana@example.test"); await click(button("Enviar"));
    assert.match(document.body.textContent ?? "", /Ya invitaste a este correo/);
    assert.equal(page.records().length, 1);
    await click(button("Historial de invitaciones"));
    assert.match(document.body.textContent ?? "", /ana@example.test/);
    assert.match(document.body.textContent ?? "", /Pendiente de aceptación/);
  } finally { await page.cleanup(); }
});

test("English copy and Escape return to the account trigger", async () => {
  const page = await mount(1280, "en");
  try {
    assert.match(document.body.textContent ?? "", /Invite to Cuadrao/);
    assert.match(document.body.textContent ?? "", /This invitation does not give access to your businesses/);
    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(document.activeElement, page.opener);
  } finally { await page.cleanup(); }
});

test("clipboard failure leaves the link selected and gives a visible correction", async () => {
  const page = await mount();
  const original = navigator.clipboard.writeText;
  Object.defineProperty(navigator.clipboard, "writeText", { configurable: true, value: async () => { throw new Error("denied"); } });
  try {
    await click(button("Copiar"));
    const link = document.querySelector<HTMLInputElement>('input[readonly]'); assert.ok(link);
    assert.equal(document.activeElement, link);
    assert.equal(link.selectionStart, 0); assert.equal(link.selectionEnd, link.value.length);
    assert.match(document.body.textContent ?? "", /Selecciona el enlace y cópialo manualmente/);
    Object.defineProperty(navigator.clipboard, "writeText", { configurable: true, value: async () => {} });
    await click(button("Copiar"));
    assert.doesNotMatch(document.body.textContent ?? "", /Selecciona el enlace y cópialo manualmente/);
  } finally { Object.defineProperty(navigator.clipboard, "writeText", { configurable: true, value: original }); await page.cleanup(); }
});
