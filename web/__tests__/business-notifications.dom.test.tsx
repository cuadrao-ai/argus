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

async function mount(width: number, language = "es-419", preview = false, mock = true) {
  const originalEnv = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: String(mock) });
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
  const actions: string[] = [];
  const render = async (businessId = "business-a", businessName = "Colmado Luna") => {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessNotifications businessId={businessId} businessName={businessName} preview={preview} onAction={(target) => actions.push(target)} /></I18nextProvider>));
  };
  await render();
  return { host, actions, render, trigger: host.querySelector<HTMLButtonElement>("button")!, close: async () => {
    await act(async () => root.unmount()); host.remove();
    for (const [key, value] of Object.entries(originalEnv)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; }
  } };
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
    assert.match(panel.textContent ?? "", /Aquí aparecerán los avisos de tu cuenta y de Colmado Luna/);
    assert.equal(document.activeElement?.getAttribute("aria-label"), "Cerrar");
    assert.equal(panel.querySelectorAll("[data-notice]").length, 0);
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
    assert.match(page.host.textContent ?? "", /Updates for your account and Colmado Luna will appear here/);
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

const click = async (element: Element | null) => { assert.ok(element); await act(async () => (element as HTMLElement).click()); };
const key = async (value: string) => { await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: value, bubbles: true }))); };
const button = (label: string) => Array.from(document.querySelectorAll("button")).find((item) => item.getAttribute("aria-label") === label || item.textContent === label) ?? null;
const rows = () => document.querySelectorAll("[data-notice]");
const unread = () => document.querySelectorAll('[aria-label="Notificación sin leer"]');

test("nonmock preview has no sample notices or unread badge", async () => {
  const page = await mount(1280, "en", true, false);
  try {
    await click(page.trigger);
    assert.equal(rows().length, 0);
    assert.equal(page.trigger.getAttribute("aria-describedby"), null);
  } finally { await page.close(); }
});

test("filter keyboard navigation and nested Escape preserve the notification panel", async () => {
  const page = await mount(1280, "es-419", true);
  try {
    await click(page.trigger);
    assert.equal(rows().length, 3); assert.equal(unread().length, 2);
    assert.match(document.getElementById(page.trigger.getAttribute("aria-describedby")!)?.textContent ?? "", /2 notificaciones sin leer/);
    const filter = button("Filtrar notificaciones")!;
    await click(filter);
    assert.equal(document.activeElement?.textContent, "Todas");
    await key("ArrowDown"); assert.equal(document.activeElement?.textContent, "Sin leer");
    await key("Escape");
    assert.equal(document.querySelector('[role="menu"]'), null);
    assert.ok(document.querySelector('[role="dialog"]'));
    assert.equal(document.activeElement, filter);
    await click(filter); await click(document.querySelectorAll('[role="menuitemradio"]')[1]);
    assert.equal(rows().length, 2);
    await act(async () => button("Marcar todas como leídas")!.focus());
    await click(button("Marcar todas como leídas"));
    assert.equal(document.activeElement, filter);
    assert.equal(rows().length, 0); assert.match(page.host.textContent ?? "", /Estás al día/);
    await click(filter); await click(document.querySelectorAll('[role="menuitemradio"]')[0]);
    assert.equal(rows().length, 3); assert.equal(unread().length, 0);
    assert.equal(page.trigger.getAttribute("aria-describedby"), null);
    await key("Escape"); await click(page.trigger); assert.equal(unread().length, 0);
  } finally { await page.close(); }
});

test("dismiss and read state stay with their Business across switching", async () => {
  const page = await mount(1280, "es-419", true);
  try {
    await click(page.trigger);
    await click(button("Marcar todas como leídas"));
    await click(button("Descartar: Invitación aceptada"));
    assert.equal(document.activeElement, button("Filtrar notificaciones"));
    assert.equal(rows().length, 2);
    await page.render("business-b", "Taller Sol");
    assert.match(page.host.textContent ?? "", /Taller Sol/);
    assert.equal(rows().length, 3); assert.equal(unread().length, 2);
    await page.render(); assert.equal(rows().length, 2); assert.equal(unread().length, 0);
  } finally { await page.close(); }
});

test("quiet actions open existing settings targets and close notifications", async () => {
  const page = await mount(1280, "en", true);
  try {
    for (const label of ["View team", "View channels", "View profile"]) {
      await click(page.trigger); await click(button(label));
      assert.equal(document.querySelector('[data-testid="business-notifications-popover"]'), null);
    }
    assert.deepEqual(page.actions, ["equipo", "correo", "datos"]);
    await click(page.trigger);
    assert.equal(document.querySelectorAll('[aria-label="Unread notification"]').length, 0);
  } finally { await page.close(); }
});

test("phone nested Escape closes the filter before the shared sheet", async () => {
  const page = await mount(390, "es-419", true);
  try {
    await click(page.trigger);
    assert.equal(rows().length, 3);
    await click(button("Descartar: Invitación aceptada"));
    assert.equal(document.activeElement, button("Filtrar notificaciones"));
    await click(button("Filtrar notificaciones")); await key("Escape");
    assert.equal(document.querySelector('[role="menu"]'), null);
    assert.equal(page.trigger.getAttribute("aria-expanded"), "true");
    await key("Escape"); assert.equal(page.trigger.getAttribute("aria-expanded"), "false");
    assert.equal(document.activeElement, page.trigger);
  } finally { await page.close(); }
});

for (const width of [1280, 390]) {
  test(`empty notifications hide list tools and preserve focus after final dismissal at ${width}px`, async () => {
    const page = await mount(width, "es-419", true);
    try {
      await click(page.trigger);
      for (const title of ["Invitación aceptada", "Canales de recepción", "Dale tu toque al negocio"]) {
        await click(button(`Descartar: ${title}`));
      }
      const empty = document.querySelector('[data-notification-state="empty-all"]')!;
      assert.ok(empty);
      assert.match(empty.textContent ?? "", /Todo tranquilo por aquí/);
      assert.match(empty.textContent ?? "", /Colmado Luna/);
      assert.equal(button("Filtrar notificaciones"), null);
      assert.equal(button("Marcar todas como leídas"), null);
      assert.equal(button("Ver todas"), null);
      assert.equal(document.activeElement, empty.querySelector("h3"));
      const art = empty.querySelector("img")!;
      assert.equal(art.getAttribute("alt"), "");
      assert.match(art.getAttribute("src") ?? "", /quiet-bell/);
      await key("Escape");
      assert.equal(document.activeElement, page.trigger);
    } finally { await page.close(); }
  });

  test(`empty unread offers a way back to the read list at ${width}px`, async () => {
    const page = await mount(width, "en", true);
    try {
      await click(page.trigger);
      await click(button("Filter notifications"));
      await click(document.querySelectorAll('[role="menuitemradio"]')[1]);
      await click(button("Mark all read"));
      const empty = document.querySelector('[data-notification-state="empty-unread"]')!;
      assert.ok(empty);
      assert.match(empty.textContent ?? "", /You're all caught up/);
      assert.match(empty.textContent ?? "", /You have no unread notifications/);
      await click(button("View all"));
      assert.equal(rows().length, 3);
      assert.equal(document.activeElement, button("Filter notifications"));
      assert.equal(document.querySelector('[data-notification-state]'), null);
    } finally { await page.close(); }
  });
}

test("empty notifications without a Business name use generic account copy", async () => {
  const page = await mount(1280, "en");
  try {
    await page.render("business-a", "");
    await click(page.trigger);
    const empty = document.querySelector('[data-notification-state="empty-all"]')!;
    assert.match(empty.textContent ?? "", /Updates for your account will appear here/);
    assert.doesNotMatch(empty.textContent ?? "", /undefined|{{business}}/);
  } finally { await page.close(); }
});
