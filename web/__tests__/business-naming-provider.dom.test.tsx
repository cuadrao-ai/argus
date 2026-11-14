import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { StrictMode, act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import BusinessNamingProvider, { useBusinessNaming } from "@/components/business-app/BusinessNamingProvider";
import { invalidateBrowserAuth } from "@/lib/browser-auth-generation";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";

mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push() {} }), usePathname: () => "/biz" }));
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
const state = (id: string) => ({ id, name: "Mi negocio", name_required: true });
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { resolve, promise }; };

async function mount(fetcher: typeof fetch, options: { strict?: boolean; profile?: boolean } = {}) {
  const originalFetch = globalThis.fetch;
  const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = fetcher;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  let naming: ReturnType<typeof useBusinessNaming>;
  function Probe() { naming = useBusinessNaming(); return null; }
  const render = async (id: string, role: "owner" | "accountant" = "owner") => {
    const context = { chosen: { space_id: id, role, name: "Mi negocio", grant_id: `${id}-grant`, capabilities: ["read"], permissions: role === "owner" ? ["read", "prepare", "approve", "manage", "download", "export", "assign_owner"] : ["read", "export"] }, source: { mode: "live" }, reload() {} } as unknown as BusinessContextValue;
    const ProfileMenu = options.profile ? (await import("@/components/sidebar/ProfileMenu")).default : null;
    const workspace = { conversationSurface: "business" } as ChatWorkspace;
    const child = <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><BusinessNamingProvider><Probe />{ProfileMenu ? <ChatWorkspaceProvider value={workspace}><ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: host }} /></ChatWorkspaceProvider> : null}</BusinessNamingProvider></BusinessContext.Provider></I18nextProvider>;
    await act(async () => { root.render(options.strict ? <StrictMode>{child}</StrictMode> : child); });
  };
  return { render, naming: () => naming!, close: async () => { await act(async () => root.unmount()); host.remove(); globalThis.fetch = originalFetch; if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; } };
}

test("a new owner gets no automatic name prompt: the setup guide holds the first steps (#1817)", async () => {
  const requested: string[] = [];
  const view = await mount(async (url) => { requested.push(String(url)); return Response.json(state("owner-space")); }, { strict: true });
  try {
    await view.render("owner-space");
    await view.render("other-owner-space");
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.doesNotMatch(document.body.textContent ?? "", /¿Cómo se llama tu negocio/);
    assert.deepEqual(requested, [], "nothing is asked of the server until a step needs the name");
  } finally { await view.close(); }
});

test("switching Business cancels a required continuation and removes its dialog", async () => {
  const view = await mount(async () => Response.json(state("owner-space")));
  try {
    await view.render("owner-space");
    let ready: Promise<boolean>;
    await act(async () => { ready = view.naming().requireName(); });
    assert.ok(document.querySelector('[role="dialog"]'));
    await view.render("client-space", "accountant");
    assert.equal(await ready!, false);
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(await view.naming().requireName(), true);
  } finally { await view.close(); }
});

test("an old required-name read cannot open a dialog after switching Business", async () => {
  const read = deferred<Response>();
  const view = await mount(async () => read.promise);
  try {
    await view.render("owner-space");
    let ready: Promise<boolean>;
    await act(async () => { ready = view.naming().requireName(); });
    await view.render("other-owner-space");
    await act(async () => read.resolve(Response.json(state("owner-space"))));
    assert.equal(await ready!, false);
    assert.equal(document.querySelector('[role="dialog"]'), null);
  } finally { await view.close(); }
});

test("leaving the Business while its required check is pending cancels the continuation", async () => {
  const read = deferred<Response>();
  const view = await mount(async () => read.promise);
  await view.render("owner-space");
  let ready: Promise<boolean>;
  await act(async () => { ready = view.naming().requireName(); });
  await view.close();
  await act(async () => read.resolve(Response.json(state("owner-space"))));
  assert.equal(await Promise.race([ready!, new Promise(resolve => setTimeout(() => resolve("stranded"), 100))]), false);
});

for (const role of ["owner", "accountant"] as const) {
  test(`Business ${role} preferences leave the business name to the Negocio page and hide personal country settings`, async () => {
    const view = await mount(async () => Response.json({ user: { id: "settings-owner", display_name: "Test owner", email: "owner@example.test", language: "es-419" }, account_kind: "registered", available: false }), { profile: true });
    try {
      await view.render("settings-space", role);
      const button = (text: string) => [...document.querySelectorAll("button")].find(item => item.textContent?.trim() === text);
      await act(async () => { button("Ajustes")!.click(); });
      assert.equal(button("País y moneda"), undefined);
      assert.ok([...document.querySelectorAll("button")].some(item => item.textContent?.includes(spanish.settings.app.language)), "Ajustes opened");
      assert.equal(button("¿Cómo se llama tu negocio?"), undefined, "the name lives in Negocio > Datos");
    } finally {
      await view.close();
      (await import("@/components/layout/overlayStack")).resetOverlayStack();
    }
  });
}
