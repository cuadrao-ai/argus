import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import type { ReactNode } from "react";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import spanish from "@/public/locales/es-419/common.json";

const copy = spanish.settings.profile.request_deletion;
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];
let deletionReads = 0;
let deletionAnswer: unknown = { allowed: false, blockers: [{ kind: "business_owner", business_id: "b-1", business_name: "Colmado Peña" }], notices: [] };

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = (async (input: unknown) => {
    if (String(input).endsWith("/account/deletion")) {
      deletionReads += 1;
      return Response.json(deletionAnswer);
    }
    return Response.json({ user: { id: "settings-owner", display_name: "Test owner", email: "owner@example.test", language: "es-419" }, account_kind: "registered", available: false });
  }) as typeof fetch;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
  deletionReads = 0;
});
afterAll(async () => {
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
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
  const workspace = business ? ({ conversationSurface: "business" } as ChatWorkspace) : null;
  await act(async () => root.render(<I18nextProvider i18n={i18n}><ChatWorkspaceProvider value={workspace}>{content}</ChatWorkspaceProvider></I18nextProvider>));
  cleanups.push(() => act(async () => root.unmount()));
  return { act };
}
const button = (text: string) => [...document.body.querySelectorAll("button")].find((item) => item.textContent?.trim() === text);
const settle = async (act: (callback: () => Promise<void>) => Promise<void>) => { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };

test("Ajustes reads the deletion answer as it opens, so the alert opens with it and never waits", async () => {
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  const { act } = await mount(<ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: anchor }} />);
  await settle(act);
  assert.equal(deletionReads, 0, "nothing is read before Ajustes opens");
  await act(async () => button("Ajustes")!.click());
  await settle(act);
  assert.equal(deletionReads, 1, "opening Ajustes reads it");
  assert.equal(document.body.textContent?.includes("Colmado Peña"), false, "the row stays a row; the names live in the alert");

  await act(async () => button("Eliminar cuenta")!.click());
  assert.equal(document.querySelector('[data-testid="delete-account-checking"]'), null, "the alert opens on the answer it already has");
  assert.ok(document.querySelector('[data-testid="delete-account-business-owner"]')?.textContent?.includes("Colmado Peña"));
  assert.equal(document.querySelector('[data-testid="delete-account-confirm"]'), null);
  await settle(act);
  assert.equal(deletionReads, 2, "opening the alert refreshes the answer behind it");
});

test("a check that could not run shows its reference and Reintentar, never Eliminar", async () => {
  const { default: Dialog } = await import("@/components/sidebar/ProfileDeleteRequestDialog");
  let retried = 0;
  const check = { answer: null, error: { reference: "ref-503-check" }, refresh: () => { retried += 1; } };
  const { act } = await mount(<Dialog check={check} state="idle" supportMailto="mailto:support@example.test" onClose={() => undefined} onSubmit={() => undefined} />);
  assert.ok(document.body.textContent?.includes("ref-503-check"));
  assert.equal(document.querySelector('[data-testid="delete-account-confirm"]'), null);
  await act(async () => button(spanish.common.retry)!.click());
  assert.equal(retried, 1);
});

test("Personal keeps its household wording and a neutral checking line; Business keeps its own", async () => {
  const { default: Dialog } = await import("@/components/sidebar/ProfileDeleteRequestDialog");
  const allowed = { answer: { allowed: true as const, blockers: [] as [], notices: [] }, error: null, refresh: () => undefined };
  const waiting = { answer: null, error: null, refresh: () => undefined };
  for (const business of [false, true]) {
    await mount(<Dialog check={allowed} state="idle" supportMailto="mailto:support@example.test" onClose={() => undefined} onSubmit={() => undefined} />, business);
    assert.equal(document.querySelector('[data-testid="delete-account-allowed"]')?.textContent, business ? copy.body : copy.body_personal);
    for (const cleanup of cleanups.splice(0)) await cleanup();
    document.body.innerHTML = "";
    await mount(<Dialog check={waiting} state="idle" supportMailto="mailto:support@example.test" onClose={() => undefined} onSubmit={() => undefined} />, business);
    assert.equal(document.querySelector('[data-testid="delete-account-checking"]')?.textContent?.trim(), business ? spanish.business.lifecycle.deletion.checking : copy.checking);
    for (const cleanup of cleanups.splice(0)) await cleanup();
    document.body.innerHTML = "";
  }
  assert.ok(copy.body_personal.includes("hogares"), "Personal gets back its household sentence");
});
