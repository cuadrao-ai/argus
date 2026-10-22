import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { createRoot } from "react-dom/client";
import BusinessCloseDialog, { businessCloseCopyEs, type BusinessCloseState } from "@/components/business-app/BusinessCloseDialog";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount() {
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const confirmed: string[] = [];
  let cancelled = 0;
  let exported = 0;
  const render = async (state: BusinessCloseState = { kind: "idle" }, name = "Taller Luna") => {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessCloseDialog businessName={name} preview={{ member_count: 7, reopen_until: "2026-11-20T17:45:00Z" }} copy={businessCloseCopyEs} state={state} onConfirm={(name) => { confirmed.push(name); }} onCancel={() => { cancelled++; }} exportControl={<button type="button" onClick={() => { exported++; }}>{businessCloseCopyEs.download}</button>} /></I18nextProvider>));
  };
  await render();
  const button = (text: string) => { const found = [...document.querySelectorAll("button")].find((item) => item.textContent === text); assert.ok(found); return found; };
  const enter = async (value: string) => { const input = document.querySelector("input"); assert.ok(input); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); }); };
  const openConfirm = () => act(async () => button(businessCloseCopyEs.close).click());
  return { confirmed, render, button, enter, openConfirm, cancelled: () => cancelled, exported: () => exported, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("the dialog keeps the exact approved copy and independent export control", async () => {
  const view = await mount();
  try {
    for (const text of [businessCloseCopyEs.title, businessCloseCopyEs.warning, businessCloseCopyEs.consequences, businessCloseCopyEs.download]) assert.ok(document.body.textContent?.includes(text));
    await act(async () => view.button(businessCloseCopyEs.download).click());
    assert.equal(view.exported(), 1);
    assert.deepEqual(view.confirmed, []);
    await view.openConfirm();
    assert.equal(document.querySelectorAll('[aria-modal="true"]').length, 1);
    assert.ok(document.querySelector('[role="alertdialog"]'));
    assert.ok(document.body.textContent?.includes(businessCloseCopyEs.confirmation));
    await act(async () => view.button(businessCloseCopyEs.cancel).click());
    assert.equal(view.cancelled(), 0);
    const dismiss = document.querySelector<HTMLButtonElement>(`button[aria-label="${businessCloseCopyEs.cancel}"]`);
    assert.ok(dismiss);
    await act(async () => dismiss.click());
    assert.equal(view.cancelled(), 1);
  } finally { await view.close(); }
});

test("close requires the exact current name without trimming or case folding", async () => {
  const view = await mount();
  try {
    await view.openConfirm();
    assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
    for (const name of ["Taller", "taller luna", "Taller Luna "]) {
      await view.enter(name);
      assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
    }
    await view.enter("Taller Luna");
    assert.equal(view.button(businessCloseCopyEs.close).disabled, false);
    await act(async () => view.button(businessCloseCopyEs.close).click());
    assert.deepEqual(view.confirmed, ["Taller Luna"]);
    await view.render({ kind: "idle" }, "Taller Sol");
    assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
  } finally { await view.close(); }
});

test("submitting blocks repeated close and cancellation while errors preserve the name", async () => {
  const view = await mount();
  try {
    await view.openConfirm();
    await view.enter("Taller Luna");
    await view.render({ kind: "submitting" });
    assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
    assert.equal(view.button(businessCloseCopyEs.cancel).disabled, true);
    await view.render({ kind: "error", message: "fixture error" });
    assert.equal(document.querySelector("input")?.value, "Taller Luna");
    assert.equal(document.querySelector('[role="alert"]')?.textContent, "fixture error");
    assert.equal(view.button(businessCloseCopyEs.close).disabled, false);
  } finally { await view.close(); }
});


test("close uses readable destructive colors in light and dark modes", async () => {
  const view = await mount();
  const luminance = (hex: string) => {
    const rgb = hex.match(/../g)!.map((part) => parseInt(part, 16) / 255).map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  };
  try {
    await view.openConfirm();
    await view.enter("Taller Luna");
    const classes = view.button(businessCloseCopyEs.close).className;
    const light = classes.match(/(?:^| )bg-\[#([0-9a-f]{6})\]/);
    const dark = classes.match(/dark:bg-\[#([0-9a-f]{6})\]/);
    assert.ok(light && dark);
    assert.ok(classes.split(" ").includes("text-white"));
    const darkForeground = classes.match(/dark:text-\[#([0-9a-f]{6})\]/);
    assert.ok(darkForeground);
    const contrast = (foreground: string, background: string) => {
      const values = [luminance(foreground), luminance(background)].sort((a, b) => a - b);
      return (values[1] + 0.05) / (values[0] + 0.05);
    };
    assert.ok(contrast("ffffff", light[1]) >= 4.5);
    assert.ok(contrast(darkForeground[1], dark[1]) >= 4.5);
  } finally { await view.close(); }
});


test("close confirmation uses the server member count and Dominican Republic preview deadline", async () => {
  const view = await mount();
  try {
    await view.openConfirm();
    assert.ok(document.body.textContent?.includes("7 miembros pierden acceso al cerrar."));
    assert.ok(document.body.textContent?.includes("20 de noviembre de 2026"));
    assert.ok(document.body.textContent?.includes("13:45") || document.body.textContent?.includes("1:45"));
    assert.ok(document.body.textContent?.includes("¿Cerrar Taller Luna?"));
    assert.deepEqual(view.confirmed, []);
  } finally { await view.close(); }
});
