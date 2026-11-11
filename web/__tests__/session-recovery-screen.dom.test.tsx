import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import i18next from "i18next";
import { act, type ComponentProps } from "react";
import { I18nextProvider } from "react-i18next";

import type { SessionRecoveryScreen } from "@/components/status/SessionRecoveryScreen";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount(
  props: ComponentProps<typeof SessionRecoveryScreen>,
  lng: "es-419" | "en" = "es-419",
) {
  const { SessionRecoveryScreen } = await import("@/components/status/SessionRecoveryScreen");
  const { createRoot } = await import("react-dom/client");
  const i18n = i18next.createInstance();
  await i18n.init({
    lng,
    fallbackLng: false,
    resources: { "es-419": { translation: spanish }, en: { translation: english } },
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  let currentProps = props;
  const render = async (next: Partial<typeof props> = {}) => {
    currentProps = { ...currentProps, ...next };
    await act(async () => root.render(
      <I18nextProvider i18n={i18n}><SessionRecoveryScreen {...currentProps} /></I18nextProvider>,
    ));
  };
  const close = async () => {
    await act(async () => root.unmount());
    host.remove();
  };
  await render();
  return { host, render, close };
}

test("a missing session presents one public login link and leaves a public document title", async () => {
  document.title = "Private business name";
  const page = await mount({ state: "missing", onRetry: () => assert.fail("unexpected retry") });
  try {
    const heading = page.host.querySelector("h1");
    assert.equal(heading?.textContent, "Inicia sesión para continuar");
    assert.ok(document.activeElement === heading, "entry focuses the heading");
    assert.equal(document.title, "Cuadrao");
    assert.equal(page.host.querySelector("p")?.textContent, "No hay una sesión activa en este navegador.");
    const actions = Array.from(page.host.querySelectorAll("a, button"));
    assert.deepEqual(actions.map((action) => [action.textContent, action.getAttribute("href")]), [
      ["Iniciar sesión", "/?auth=login"],
    ]);
    assert.equal(page.host.querySelector('img[src="/brand/session-door.png"]')?.getAttribute("alt"), "");
  } finally {
    await page.close();
  }
  assert.equal(document.title, "Cuadrao");
});

test("a failed check offers retry and announces a busy retry without moving focus back to the heading", async () => {
  let retries = 0;
  const page = await mount({ state: "error", onRetry: () => { retries += 1; } });
  try {
    assert.equal(page.host.querySelector("h1")?.textContent, "No pudimos comprobar tu sesión");
    assert.equal(page.host.querySelector("p, a, img[src='/brand/session-door.png']"), null);
    const button = page.host.querySelector("button")!;
    assert.equal(button.textContent, "Reintentar");
    await act(async () => { button.focus(); button.click(); });
    assert.equal(retries, 1);
    await page.render({ busy: true });
    assert.equal(button.disabled, true);
    assert.ok(page.host.querySelector('[aria-busy="true"]'));
    const status = page.host.querySelector('[role="status"]');
    assert.ok(status);
    assert.equal(status.textContent, "Comprobando tu sesión…");
    assert.equal(button.textContent, status.textContent);
    assert.equal(status.closest('[aria-busy="true"]'), null);
    await act(async () => button.click());
    assert.equal(retries, 1);
    await page.render({ busy: false });
    assert.equal(button.disabled, false);
    assert.equal(status.textContent, "");
    assert.ok(document.activeElement !== page.host.querySelector("h1"), "a completed retry leaves focus alone");
    await page.render({ state: "missing" });
    assert.equal(document.activeElement, page.host.querySelector("h1"), "a new recovery state receives focus after the retry button is removed");
  } finally {
    await page.close();
  }
});

test("a changed account exposes a Home action only when it is ready", async () => {
  let continuations = 0;
  const page = await mount({
    state: "different-owner",
    continueDisabled: true,
    onRetry: () => assert.fail("unexpected retry"),
    onContinue: () => { continuations += 1; },
  }, "en");
  try {
    assert.equal(page.host.querySelector("h1")?.textContent, "The active account changed");
    assert.equal(page.host.querySelector("p")?.textContent, "This workspace closed to keep information from different accounts separate.");
    assert.equal(page.host.querySelector("a, img[src='/brand/session-door.png']"), null);
    const button = page.host.querySelector("button")!;
    assert.equal(button.textContent, "Go to Home");
    assert.equal(button.disabled, true);
    await act(async () => button.click());
    assert.equal(continuations, 0);
    await page.render({ continueDisabled: false });
    await act(async () => button.click());
    assert.equal(continuations, 1);
  } finally {
    await page.close();
  }
});
