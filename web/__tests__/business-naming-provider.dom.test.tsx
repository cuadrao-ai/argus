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
import { ReceiptPeriodExport } from "@/components/business-app/ReceiptDossierReview";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push() {} }), usePathname: () => "/biz" }));
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
const state = (id: string, show = false) => ({ id, name: "Mi negocio", name_required: true, name_prompt_seen: true, show_prompt: show });
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { resolve, promise }; };

async function mount(fetcher: typeof fetch, options: { strict?: boolean; export?: boolean; profile?: boolean } = {}) {
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
  const dossier = await createDossierFixtures([{ id: "account-fixture", nickname: "Caja", type: "cash", currency: "DOP" }]).dossier(dossierFixtureIds.ready);
  const render = async (id: string, role: "owner" | "accountant" = "owner") => {
    const context = { chosen: { space_id: id, role }, source: { mode: "live" }, reload() {} } as unknown as BusinessContextValue;
    const ProfileMenu = options.profile ? (await import("@/components/sidebar/ProfileMenu")).default : null;
    const workspace = { conversationSurface: "business" } as ChatWorkspace;
    const child = <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><BusinessNamingProvider><Probe />{ProfileMenu ? <ChatWorkspaceProvider value={workspace}><ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: host }} /></ChatWorkspaceProvider> : null}{options.export ? <ReceiptPeriodExport dossier={dossier} start="2026-10-01" end="2026-10-31" available /> : null}</BusinessNamingProvider></BusinessContext.Provider></I18nextProvider>;
    await act(async () => { root.render(options.strict ? <StrictMode>{child}</StrictMode> : child); });
  };
  return { render, naming: () => naming!, close: async () => { await act(async () => root.unmount()); host.remove(); globalThis.fetch = originalFetch; if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; } };
}

test("StrictMode claims once and a return visit never reuses the first prompt", async () => {
  let claims = 0;
  const pending = deferred<Response>();
  const view = await mount(async () => { claims++; return pending.promise; }, { strict: true });
  try {
    await view.render("owner-space");
    assert.equal(claims, 1);
    await act(async () => pending.resolve(Response.json(state("owner-space", true))));
    assert.match(document.body.textContent ?? "", /¿Cómo se llama tu negocio/);
    await act(async () => { [...document.querySelectorAll("button")].find(button => button.textContent === "Ahora no")!.click(); });
    await view.render("client-space", "accountant");
    await view.render("owner-space");
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(claims, 1);
  } finally { await view.close(); }
});

test("late prompt from another account cannot show in the current Business", async () => {
  const old = deferred<Response>();
  const requested: string[] = [];
  const view = await mount(async (_url, init) => {
    const id = JSON.parse(String(init?.body)).space_id;
    requested.push(id);
    return id === "old-space" ? old.promise : Response.json(state(id, true));
  });
  try {
    await view.render("old-space");
    invalidateBrowserAuth();
    await view.render("new-space");
    await act(async () => old.resolve(Response.json(state("old-space", true))));
    assert.deepEqual(requested, ["old-space", "new-space"]);
    assert.match(document.body.textContent ?? "", /¿Cómo se llama tu negocio/);
    assert.equal(document.querySelectorAll('[role="dialog"]').length, 1);
  } finally { await view.close(); }
});

test("switching Business cancels a required continuation and removes its dialog", async () => {
  const view = await mount(async (url, init) => Response.json(String(url).endsWith("name-prompt") ? state(JSON.parse(String(init?.body)).space_id) : state("owner-space")));
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
  const view = await mount(async (url, init) => String(url).endsWith("name-prompt") ? Response.json(state(JSON.parse(String(init?.body)).space_id)) : read.promise);
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

test("the existing export component waits for the same required-name dialog", async () => {
  let exports = 0;
  const view = await mount(async (url, init) => {
    if (String(url).includes("/exports")) { exports++; return new Response("PKfixture", { headers: { "Content-Type": "application/zip" } }); }
    return Response.json(String(url).endsWith("name-prompt") ? state(JSON.parse(String(init?.body)).space_id) : state("owner-space"));
  }, { export: true });
  try {
    await view.render("owner-space");
    await act(async () => { document.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
    assert.equal(exports, 0);
    const dialog = document.querySelector('[role="dialog"]');
    assert.match(dialog?.textContent ?? "", /Guardar y continuar/);
    assert.equal(dialog?.querySelectorAll("button").length, 1);
    await view.render("client-space", "accountant");
    assert.equal(exports, 0);
  } finally { await view.close(); }
});

test("a late first-visit claim cannot replace a required continuation", async () => {
  const claim = deferred<Response>();
  const view = await mount(async url => String(url).endsWith("name-prompt") ? claim.promise : Response.json(state("owner-space")));
  try {
    await view.render("owner-space");
    let ready: Promise<boolean>;
    await act(async () => { ready = view.naming().requireName(); });
    await act(async () => claim.resolve(Response.json(state("owner-space", true))));
    const dialog = document.querySelector('[role="dialog"]');
    assert.match(dialog?.textContent ?? "", /Guardar y continuar/);
    assert.equal(dialog?.querySelectorAll("button").length, 1);
    await view.render("client-space", "accountant");
    assert.equal(await ready!, false);
  } finally { await view.close(); }
});

test("leaving the Business while its required check is pending cancels the continuation", async () => {
  const read = deferred<Response>();
  const view = await mount(async (url, init) => String(url).endsWith("name-prompt") ? Response.json(state(JSON.parse(String(init?.body)).space_id)) : read.promise);
  await view.render("owner-space");
  let ready: Promise<boolean>;
  await act(async () => { ready = view.naming().requireName(); });
  await view.close();
  await act(async () => read.resolve(Response.json(state("owner-space"))));
  assert.equal(await Promise.race([ready!, new Promise(resolve => setTimeout(() => resolve("stranded"), 100))]), false);
});

for (const role of ["owner", "accountant"] as const) {
  test(`Business ${role} preferences preserve naming access and hide personal country settings`, async () => {
    const view = await mount(async (url, init) => String(url).endsWith("name-prompt")
      ? Response.json(state(JSON.parse(String(init?.body)).space_id))
      : Response.json({ user: { id: "settings-owner", display_name: "Test owner", email: "owner@example.test", language: "es-419" }, account_kind: "registered", available: false }), { profile: true });
    try {
      await view.render("settings-space", role);
      const button = (text: string) => [...document.querySelectorAll("button")].find(item => item.textContent?.trim() === text);
      await act(async () => { button("Preferencias")!.click(); });
      assert.equal(button("País y moneda"), undefined);
      assert.equal(Boolean(button("¿Cómo se llama tu negocio?")), role === "owner");
    } finally {
      await view.close();
      (await import("@/components/layout/overlayStack")).resetOverlayStack();
    }
  });
}
