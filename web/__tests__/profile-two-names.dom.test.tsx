import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import spanish from "@/public/locales/es-419/common.json";

const profileCopy = spanish.settings.profile;
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];
const patches: unknown[] = [];
const user = { id: "names-owner", display_name: "Ana Peña", preferred_name: null as string | null, username: "ana", email: "ana@example.test", language: "es-419" };

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = (async (_input: unknown, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      const body = JSON.parse(String(init.body));
      patches.push(body);
      Object.assign(user, body);
    }
    return Response.json({ user, account_kind: "registered", available: false });
  }) as typeof fetch;
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

const button = (text: string) => [...document.body.querySelectorAll("button")].find((item) => item.textContent?.trim() === text);

test("Perfil shows two names edited in place, without the handle or a language shortcut", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><ChatWorkspaceProvider value={{ conversationSurface: "business" } as ChatWorkspace}><ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: anchor }} /></ChatWorkspaceProvider></I18nextProvider>));
  cleanups.push(() => act(async () => root.unmount()));
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  await act(async () => button(profileCopy.title)!.click());

  const dialog = () => document.querySelector('[role="dialog"]');
  assert.ok(dialog()?.textContent?.includes("ana@example.test"));
  assert.equal(dialog()?.textContent?.includes("@ana"), false, "no handle");
  assert.equal(document.querySelector("#argus-profile-language-trigger"), null, "the language lives in Ajustes");
  assert.ok(document.querySelector('[data-testid="profile-name-row-profile-name"]'));
  assert.ok(document.querySelector('[data-testid="profile-name-row-profile-preferred-name"]'));
  assert.ok(dialog()?.textContent?.includes(profileCopy.preferred_name_hint));

  // The pencil opens the field; Escape cancels the edit and keeps Perfil open.
  await act(async () => document.querySelector<HTMLButtonElement>("button#profile-preferred-name")!.click());
  assert.ok(document.querySelector("input#profile-preferred-name"));
  await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  assert.equal(document.querySelector("input#profile-preferred-name"), null);
  assert.ok(dialog(), "Escape cancelled the edit, not Perfil");

  // The check saves only that name.
  await act(async () => document.querySelector<HTMLButtonElement>("button#profile-preferred-name")!.click());
  const input = document.querySelector<HTMLInputElement>("input#profile-preferred-name")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Ana");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => document.querySelector<HTMLButtonElement>(`[aria-label="${spanish.common.save}"]`)!.click());
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  assert.deepEqual(patches, [{ preferred_name: "Ana" }]);
  assert.equal(document.querySelector("input#profile-preferred-name"), null, "the row returns to its value");
  assert.ok(dialog()?.textContent?.includes("Ana"));
});
