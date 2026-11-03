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
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
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
  await GlobalRegistrator.unregister();
});

async function mount(content: (anchor: HTMLButtonElement) => ReactNode) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const anchor = document.createElement("button");
  anchor.setAttribute("data-testid", "account-button");
  document.body.appendChild(anchor);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const workspace = { conversationSurface: "business" } as ChatWorkspace;
  await act(async () => root.render(<I18nextProvider i18n={i18n}><ChatWorkspaceProvider value={workspace}>{content(anchor)}</ChatWorkspaceProvider></I18nextProvider>));
  cleanups.push(() => act(async () => root.unmount()));
  return { act, anchor };
}
const button = (text: string) => [...document.body.querySelectorAll("button")].find((item) => item.textContent?.trim() === text);
const dialogs = () => document.body.querySelectorAll('[role="dialog"][aria-modal="true"]');

test("Ajustes is one window: sections change in place, Escape closes it, and focus returns to the account button", async () => {
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const { act, anchor } = await mount((opener) => <ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: opener }} />);
  await act(async () => { await Promise.resolve(); });
  await act(async () => button("Ajustes")!.click());
  assert.equal(dialogs().length, 1);
  assert.equal(button("Apariencia")!.getAttribute("aria-current"), "page", "it opens on the first section");
  assert.ok(document.querySelector('[data-testid="settings-pane-appearance"]'));

  await act(async () => button("Idioma de la app")!.click());
  assert.equal(dialogs().length, 1, "a section never stacks a second surface");
  assert.equal(button("Idioma de la app")!.getAttribute("aria-current"), "page");
  assert.equal(button("Apariencia")!.getAttribute("aria-current"), null);
  assert.equal(document.querySelector('[data-testid="settings-pane-appearance"]'), null);
  assert.ok(document.querySelector('[data-testid="settings-pane-language"]'));
  assert.equal(document.body.querySelectorAll("h3")[0]?.textContent, "Idioma de la app", "the pane is titled for its section");

  await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  assert.equal(document.querySelector('[data-testid="settings-window"]'), null);
  assert.equal(document.activeElement, anchor);
});

test("Comentarios opens the form straight away, its type picked inside it", async () => {
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const opened: string[] = [];
  const { act } = await mount((opener) => <ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} onFeedback={(type) => opened.push(type)} anchorRef={{ current: opener }} />);
  assert.equal(button("Reportar un error"), undefined, "the menu has no feedback submenu");
  await act(async () => button("Comentarios")!.click());
  assert.deepEqual(opened, ["general"]);
});

test("the feedback form is a centered dialog on desktop", async () => {
  const { default: FeedbackDialog } = await import("@/components/feedback/FeedbackDialog");
  await mount(() => <FeedbackDialog isOpen onClose={() => {}} type="general" />);
  const dialog = document.querySelector('[data-testid="feedback-dialog"]');
  assert.ok(dialog, "it draws the centered dialog, not the side drawer");
  assert.equal(dialog.getAttribute("aria-modal"), "true");
  assert.ok(dialog.querySelector("h2")?.textContent);
});
