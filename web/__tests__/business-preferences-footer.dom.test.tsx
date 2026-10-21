import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = (async () => Response.json({ user: { id: "settings-owner", display_name: "Test owner", email: "owner@example.test", language: "es-419", locale: "es-419" }, account_kind: "registered", available: false })) as unknown as typeof fetch;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  (await import("@/lib/switch-labels")).setSwitchLabelsShown(true);
  document.body.innerHTML = "";
});
afterAll(async () => {
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

const button = (text: string) => [...document.body.querySelectorAll("button")].find((item) => item.textContent?.trim() === text);

async function openMenu(language: "es-419" | "en") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { ChatWorkspaceProvider } = await import("@/components/chat/ChatWorkspace");
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const i18n = createInstance();
  await i18n.init({ lng: language, resources: { en: { translation: english }, "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const workspace = { conversationSurface: "business" } as Parameters<typeof ChatWorkspaceProvider>[0]["value"];
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <ChatWorkspaceProvider value={workspace}>
        <ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: anchor }} />
      </ChatWorkspaceProvider>
    </I18nextProvider>,
  ));
  cleanups.push(() => act(async () => root.unmount()));
  return act;
}

for (const [language, copy] of [
  ["es-419", { preferences: "Preferencias", language: "Idioma de la app", words: "Interruptores con palabras", yes: "Sí", no: "No", terms: "Términos", privacy: "Privacidad" }],
  ["en", { preferences: "Preferences", language: "App language", words: "Words on switches", yes: "Yes", no: "No", terms: "Terms", privacy: "Privacy" }],
] as const) {
  test(`${language}: Preferencias holds the switch-words setting beside the language, and flipping it takes the words off and puts them back`, async () => {
    const act = await openMenu(language);
    await act(async () => button(copy.preferences)!.click());
    const setting = document.body.querySelector<HTMLButtonElement>('[data-testid="settings-switch-labels"]');
    assert.ok(setting, "the setting is in Preferencias");
    assert.equal(setting.getAttribute("aria-label"), copy.words);
    assert.equal(setting.getAttribute("aria-checked"), "true", "words are on by default");
    const preferences = document.body.querySelector(`[aria-label="${copy.preferences}"]`)!;
    assert.ok(preferences.contains(setting));
    assert.ok(button(copy.language)!.nextElementSibling!.contains(setting), "it sits right after Idioma de la app");
    assert.ok(button(copy.language)!.nextElementSibling!.textContent!.startsWith(copy.words), "its row names it");
    assert.equal(setting.textContent, `${copy.yes}${copy.no}`);

    await act(async () => setting.click());
    assert.equal(setting.getAttribute("aria-checked"), "false");
    assert.equal(setting.textContent, "", "the switch that turned words off shows none itself");

    await act(async () => setting.click());
    assert.equal(setting.textContent, `${copy.yes}${copy.no}`);
  });

  test(`${language}: the settings menu ends with Términos and Privacidad, opening the published pages in a new tab`, async () => {
    const { PUBLISHED_PRIVACY_URL, PUBLISHED_TERMS_URL } = await import("@/lib/cuadrao-legal-links");
    await openMenu(language);
    const footer = document.body.querySelector('[data-testid="settings-legal-footer"]');
    assert.ok(footer, "the footer shows on Business");
    const links = [...footer.querySelectorAll("a")].map((link) => ({ text: link.textContent, href: link.getAttribute("href"), target: link.getAttribute("target"), rel: link.getAttribute("rel") }));
    assert.deepEqual(links, [
      { text: copy.terms, href: PUBLISHED_TERMS_URL, target: "_blank", rel: "noreferrer" },
      { text: copy.privacy, href: PUBLISHED_PRIVACY_URL, target: "_blank", rel: "noreferrer" },
    ]);
    const surface = document.body.querySelector("[data-profile-menu-surface]")!;
    assert.equal(surface.lastElementChild, footer, "it is the last row of the menu");
  });
}
