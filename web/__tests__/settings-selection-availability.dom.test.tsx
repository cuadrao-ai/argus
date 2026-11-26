import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import type { ReactNode } from "react";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import { BusinessContext } from "@/components/business-app/business-context";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { SettingsPanel } from "@/components/sidebar/ProfileSettingsPanels";
import spanish from "@/public/locales/es-419/common.json";

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/lib/memory-privacy")).resetMemoryAvailabilityCache();
  document.body.innerHTML = "";
  window.happyDOM.setWindowSize({ width: 1024, height: 768 });
  globalThis.fetch = originalFetch;
});
afterAll(async () => {
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

async function mount(width: number) {
  window.happyDOM.setWindowSize({ width, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const anchor = document.createElement("button");
  const host = document.createElement("div");
  document.body.append(anchor, host);
  const root = createRoot(host);
  cleanups.push(() => act(async () => root.unmount()));
  const render = (content: ReactNode) => act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <ChatWorkspaceProvider value={{ conversationSurface: "business" } as ChatWorkspace}>
        {content}
      </ChatWorkspaceProvider>
    </I18nextProvider>,
  ));
  return { act, anchor, render };
}

const nav = (panel: SettingsPanel) => document.querySelector<HTMLButtonElement>(`[data-testid="settings-nav-${panel}"]`);
const pane = (panel: SettingsPanel) => document.querySelector(`[data-testid="settings-pane-${panel}"]`);

test.each([1280, 390])("Cuenta stays selected when the delayed profile enables WhatsApp at %ipx", async (width) => {
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const { act, anchor, render } = await mount(width);
  const profile = Promise.withResolvers<Response>();
  let profileReads = 0;
  const unexpected: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/api/v1/me") {
      profileReads += 1;
      return profile.promise;
    }
    if (path === "/api/v1/whatsapp/link") return Response.json({ linked: false, receiving_businesses: [], held_count: 0 });
    if (path === "/api/v1/account/deletion") return Response.json({ allowed: true, blockers: [], notices: [] });
    if (path === "/api/v1/memory/availability") return Response.json({ available: false });
    unexpected.push(path);
    throw new Error(`Unexpected synthetic request: ${path}`);
  }) as typeof fetch;
  const answer = () => profile.resolve(Response.json({
    user: { id: "settings-owner", display_name: "Test owner", email: "owner@example.test", language: "es-419" },
    account_kind: "registered",
  }));
  try {
    await render(
      <BusinessContext.Provider value={{ receivingChannels: { email: { available: false }, whatsapp: { available: true } } } as BusinessContextValue}>
        <ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: anchor }} />
      </BusinessContext.Provider>,
    );
    assert.equal(profileReads, 1, "the profile request is still pending");
    await act(async () => [...document.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Ajustes")!.click());
    assert.ok(!nav("whatsapp"));
    await act(async () => nav("account")!.click());
    const chosenPane = pane("account");
    assert.ok(chosenPane, "Cuenta opened before the profile answered");

    await act(async () => { answer(); });
    assert.ok(nav("whatsapp"), "the late profile adds the WhatsApp row");
    assert.ok(pane("account") === chosenPane, "the selected Cuenta pane stays mounted");
    assert.ok(!pane("appearance"));
    assert.deepEqual(unexpected, []);
  } finally {
    await act(async () => { answer(); });
  }
});

test.each([1280, 390])("unavailable sections fall back once to the first section at %ipx", async (width) => {
  const { default: SettingsWindow } = await import("@/components/settings/SettingsWindow");
  const { act, anchor, render } = await mount(width);
  const sections = (available: SettingsPanel[]) => render(
    <SettingsWindow sections={available} renderSection={(panel) => <span>{panel}</span>} legalLinks={[]} returnFocusRef={{ current: anchor }} onClose={() => {}} />,
  );
  await sections(["appearance", "language", "whatsapp", "account"]);
  await act(async () => nav("whatsapp")!.click());
  const chosenPane = pane("whatsapp");
  assert.ok(chosenPane);
  await sections(["appearance", "whatsapp", "account"]);
  assert.ok(pane("whatsapp") === chosenPane, "removing a different row preserves the selection");

  await sections(["appearance", "account"]);
  assert.ok(!pane("whatsapp"));
  assert.ok(pane("appearance"), "removing the selected row opens the first remaining section");
  await sections(["appearance", "whatsapp", "account"]);
  assert.ok(pane("appearance"), "a returning row does not restore the old selection");
  assert.ok(!pane("whatsapp"));
});
