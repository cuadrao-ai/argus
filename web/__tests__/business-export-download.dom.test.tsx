import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import BusinessExpensesPanel from "@/components/business-app/BusinessExpensesPanel";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { setChosenGrant } from "@/lib/business-grant";
import type { GrantedSpace } from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";

const own: GrantedSpace = { space_id: "own-space", grant_id: "own-grant", name: "Taller Luna", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true };
const client: GrantedSpace = { ...own, space_id: "client-space", grant_id: "client-grant", name: "Colmado Sol", role: "accountant", capabilities: ["read"] };
const bytes = new Uint8Array([80, 75, 3, 4, 0, 255]);
const original = { fetch: globalThis.fetch, create: URL.createObjectURL, revoke: URL.revokeObjectURL, auth: process.env.NEXT_PUBLIC_MOCK_AUTH };
let calls: { url: URL; init?: RequestInit }[] = [];
let downloads: { filename: string; blob: Blob }[] = [];
let respond: (init?: RequestInit) => Promise<Response>;

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz?view=expenses" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  URL.createObjectURL = (blob) => { downloads.push({ filename: "", blob: blob as Blob }); return "blob:export"; };
  URL.revokeObjectURL = () => undefined;
  HTMLAnchorElement.prototype.click = function () { downloads.at(-1)!.filename = this.download; };
  globalThis.fetch = async (input, init) => { calls.push({ url: new URL(String(input)), init }); return respond(init); };
});
afterAll(async () => {
  globalThis.fetch = original.fetch;
  URL.createObjectURL = original.create;
  URL.revokeObjectURL = original.revoke;
  if (original.auth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = original.auth;
  setChosenGrant(null);
  await GlobalRegistrator.unregister();
});

async function mount(chosen = own) {
  calls = []; downloads = [];
  respond = async () => new Response(bytes, { headers: { "Content-Type": "application/zip" } });
  setChosenGrant(chosen.role === "owner" ? null : chosen.grant_id);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const source = { ...createFixtureBusinessDataSource(), mode: "live" as const, expenses: async () => [], dossier: async () => { throw new Error("Exports must not fetch a dossier"); } };
  let context = {
    source, chosen, revision: 0,
    period: { key: "custom", from: "2026-10-01", to: "2026-10-17" },
    records: { workspace: null, overview: { from: "2026-10-01", to: "2026-10-17" }, error: false },
    panel: { kind: "expenses" }, actions: { create: [] },
    setPeriod: () => undefined,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const render = async (patch: Partial<BusinessContextValue> = {}) => {
    context = { ...context, ...patch };
    setChosenGrant(context.chosen?.role === "accountant" ? context.chosen.grant_id : null);
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><BusinessExpensesPanel /></BusinessContext.Provider></I18nextProvider>));
  };
  await render();
  const button = () => [...host.querySelectorAll("button")].find((item) => item.textContent?.includes("Descargar CSV, Excel y originales"));
  const submit = async () => { assert.ok(button(), "Gastos mounts the Spanish ZIP download control"); await act(async () => { host.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); }); };
  return { host, context, render, button, submit, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

for (const chosen of [own, client]) test(`Gastos downloads the current period ZIP for ${chosen.role}`, async () => {
  const view = await mount(chosen);
  try {
    await view.submit();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url.pathname.endsWith("/business/exports"), true);
    assert.deepEqual([...calls[0].url.searchParams], [["start", "2026-10-01"], ["end", "2026-10-17"]]);
    assert.equal(new Headers(calls[0].init?.headers).get("X-Business-Grant"), chosen.role === "accountant" ? chosen.grant_id : null);
    assert.equal(downloads.length, 1);
    assert.deepEqual(new Uint8Array(await downloads[0].blob.arrayBuffer()), bytes);
    assert.equal(downloads[0].filename, "business-export-2026-10-01-2026-10-17.zip");
    assert.ok(view.host.textContent?.includes(chosen.name));
  } finally { await view.close(); }
});
