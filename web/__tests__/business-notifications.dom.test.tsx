import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(width: number, language = "es-419") {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { default: BusinessNotifications } = await import("@/components/business-app/foundation/BusinessNotifications");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const en = (await import("@/public/locales/en/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: es }, en: { translation: en } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessNotifications /></I18nextProvider>));
  return { host, trigger: host.querySelector<HTMLButtonElement>("button")!, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("desktop notifications open from the bell, dismiss with Escape, and return focus", async () => {
  const page = await mount(1280);
  try {
    assert.equal(page.trigger.getAttribute("aria-label"), "Notificaciones");
    assert.equal(page.trigger.getAttribute("aria-expanded"), "false");
    await act(async () => page.trigger.click());
    const panel = page.host.querySelector('[role="dialog"]')!;
    assert.ok(panel);
    assert.equal(page.trigger.getAttribute("aria-controls"), panel.id);
    assert.match(panel.textContent ?? "", /Tus invitaciones y avisos aparecerán aquí/);
    assert.equal(document.activeElement, panel.querySelector("button"));
    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    assert.equal(page.host.querySelector('[role="dialog"]'), null);
    assert.equal(document.activeElement, page.trigger);
    assert.equal(page.trigger.getAttribute("aria-expanded"), "false");
  } finally { await page.close(); }
});

test("desktop notifications close on an outside pointer without stealing focus", async () => {
  const page = await mount(1280, "en");
  try {
    assert.equal(page.trigger.getAttribute("aria-label"), "Notifications");
    await act(async () => page.trigger.click());
    assert.match(page.host.textContent ?? "", /Your invitations and updates will appear here/);
    await act(async () => document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })));
    assert.equal(page.host.querySelector('[role="dialog"]'), null);
  } finally { await page.close(); }
});

test("phone notifications use the shared bottom sheet", async () => {
  const page = await mount(390);
  try {
    await act(async () => page.trigger.click());
    assert.ok(document.querySelector('[data-testid="business-notifications-sheet"]'));
    assert.equal(document.querySelector('[data-testid="business-notifications-popover"]'), null);
    assert.equal(document.querySelector('[role="dialog"]')?.getAttribute("aria-modal"), "true");
  } finally { await page.close(); }
});
