import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import type { ReactNode } from "react";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import spanish from "@/public/locales/es-419/common.json";

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const originalSpanish = process.env.NEXT_PUBLIC_ENABLE_SPANISH;
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  process.env.NEXT_PUBLIC_ENABLE_SPANISH = "true";
  delete process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL;
  delete process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL;
  globalThis.fetch = (async () => Response.json({ user: { id: "settings-owner", display_name: "Test owner", email: "owner@example.test", language: "es-419" }, account_kind: "registered", available: false })) as typeof fetch;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => {
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  if (originalSpanish === undefined) delete process.env.NEXT_PUBLIC_ENABLE_SPANISH;
  else process.env.NEXT_PUBLIC_ENABLE_SPANISH = originalSpanish;
  await GlobalRegistrator.unregister();
});

async function mount(content: ReactNode, business = true) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const workspace = business ? { conversationSurface: "business" } as ChatWorkspace : null;
  await act(async () => root.render(<I18nextProvider i18n={i18n}><ChatWorkspaceProvider value={workspace}>{content}</ChatWorkspaceProvider></I18nextProvider>));
  cleanups.push(() => act(async () => root.unmount()));
  return { act, host };
}
const button = (text: string) => [...document.body.querySelectorAll("button")].find((item) => item.textContent?.trim() === text);

for (const business of [true, false]) {
  test(`${business ? "Business hides" : "Personal preserves"} country, legacy legal, usage, and archived chats`, async () => {
    const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
    const anchor = document.createElement("button");
    document.body.appendChild(anchor);
    const { act } = await mount(<ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: anchor }} />, business);
    assert.equal(document.querySelectorAll('a[href="/terms"],a[href="/privacy"]').length, business ? 0 : 2);
    await act(async () => button("Preferencias")!.click());
    assert.equal(Boolean(button("País y moneda")), !business);
    await act(async () => button("Controles de datos")!.click());
    assert.equal(Boolean(button("Chats archivados")), !business);
    assert.equal(Boolean(button("Uso")), !business);
    assert.equal(button("Eliminar todas las conversaciones"), undefined);
    assert.ok(button("Seguridad"));
    await act(async () => button("Ayuda y legal")!.click());
    assert.equal(document.querySelectorAll('a[href="/terms"],a[href="/privacy"]').length, business ? 0 : 4);
    assert.equal(document.querySelector("[data-testid=help-legal-empty]") !== null, business);
  });
}

test("Ayuda y legal links the published terms and privacy URLs and stays empty without them", async () => {
  const terms = process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL;
  const privacy = process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL;
  delete process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL;
  delete process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL;
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const open = async () => {
    const anchor = document.createElement("button");
    document.body.appendChild(anchor);
    const view = await mount(<ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: anchor }} />);
    await view.act(async () => button("Ayuda y legal")!.click());
    return view;
  };
  await open();
  assert.equal(document.querySelectorAll("a").length, 0);
  assert.ok(document.querySelector("[data-testid=help-legal-empty]"));
  assert.equal(document.querySelector('a[href^="mailto:"]'), null);
  for (const cleanup of cleanups.splice(0)) await cleanup();
  document.body.innerHTML = "";
  process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "https://cuadrao.example/terminos";
  process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = "https://cuadrao.example/privacidad";
  await open();
  const termsLink = document.querySelector('a[href="https://cuadrao.example/terminos"]');
  const privacyLink = document.querySelector('a[href="https://cuadrao.example/privacidad"]');
  assert.equal(termsLink?.textContent?.trim(), "Términos");
  assert.equal(privacyLink?.textContent?.trim(), "Privacidad");
  assert.equal(termsLink?.getAttribute("target"), "_blank");
  assert.equal(privacyLink?.getAttribute("rel"), "noreferrer");
  assert.equal(document.querySelector("[data-testid=help-legal-empty]"), null);
  assert.equal(document.querySelector('a[href^="mailto:"]'), null);
  if (terms === undefined) delete process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL;
  else process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = terms;
  if (privacy === undefined) delete process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL;
  else process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = privacy;
});

test("the preferences sheet is titled Preferencias", async () => {
  const originalMatchMedia = window.matchMedia.bind(window);
  window.matchMedia = (query: string) => ({
    matches: query.includes("max-width"),
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return false; },
  }) as MediaQueryList;
  try {
    const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
    const anchor = document.createElement("button");
    document.body.appendChild(anchor);
    const { act } = await mount(<ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: anchor }} />);
    await act(async () => button("Preferencias")!.click());
    const headings = [...document.querySelectorAll("h1, h2")].map((node) => node.textContent?.trim());
    assert.equal(headings.includes("Preferencias"), true);
    assert.equal(headings.includes("App"), false);
  } finally {
    window.matchMedia = originalMatchMedia;
  }
});

test("Business feedback uses the requested copy without an inactive learn-more action", async () => {
  const { default: FeedbackDialog } = await import("@/components/feedback/FeedbackDialog");
  await mount(<FeedbackDialog isOpen onClose={() => {}} type="general" />);
  assert.ok(document.body.textContent?.includes("Cuéntanos cómo te va con Cuadrao. Leemos cada comentario."));
  assert.equal(button("Más información"), undefined);
  assert.ok(document.body.textContent?.includes("No se adjunta la conversación ni información de contacto."));
});

test("the language picker shows English once", async () => {
  const { default: LanguageModal } = await import("@/components/settings/LanguageModal");
  await mount(<LanguageModal onClose={() => {}} />);
  assert.ok(button("English"));
  assert.equal(button("EnglishEnglish"), undefined);
});

for (const succeeds of [true, false]) {
  test(`copy address shows ${succeeds ? "confirmation" : "failure"} only after the clipboard answers`, async () => {
    const { EmailReceivingAddress } = await import("@/components/business-app/BusinessEmailDeliveries");
    const address = "receipts@example.test";
    const writes: string[] = [];
    const originalClipboard = navigator.clipboard;
    let release: () => void = () => {};
    const pending = new Promise<void>((resolve) => { release = resolve; });
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (value: string) => { writes.push(value); await pending; if (!succeeds) throw new Error("Clipboard refused"); } } });
    cleanups.push(async () => { Object.defineProperty(navigator, "clipboard", { configurable: true, value: originalClipboard }); });
    const { act } = await mount(<EmailReceivingAddress intake={{ enabled: true, receiving_address: address }} onActivate={async () => {}} />);
    await act(async () => button("Copiar dirección")!.click());
    assert.equal(document.querySelector('[role="status"]'), null);
    await act(async () => release());
    assert.deepEqual(writes, [address]);
    assert.equal(document.querySelector('[role="status"]')?.textContent, succeeds ? spanish.business.email.copied : spanish.business.email.copy_failed);
  });
}
