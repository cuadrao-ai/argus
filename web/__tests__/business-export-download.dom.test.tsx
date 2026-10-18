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
import { invalidateBrowserAuth } from "@/lib/browser-auth-generation";
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
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith("/business/fiscal-profile")) return Response.json({ rnc: null, can_edit: false });
    calls.push({ url, init }); return respond(init);
  };
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
  const submit = async () => { assert.ok(button(), "Gastos mounts the Spanish ZIP download control"); await act(async () => { button()!.click(); }); };
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

test("Todo requires a supported explicit period and follows the next selected period", async () => {
  const view = await mount();
  try {
    await view.render({ period: { key: "all", from: "2000-01-01", to: "2026-10-17" } });
    assert.equal(view.button()!.disabled, true);
    assert.match(view.host.textContent!, /1 y 366 días/);
    await act(async () => view.button()!.click());
    assert.equal(calls.length, 0);
    const input = view.button()!.form!.querySelector("input")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "2026-10-01");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    assert.equal(view.button()!.disabled, false);
    await view.submit();
    assert.equal(calls[0].url.searchParams.get("start"), "2026-10-01");
    await view.render({ period: { key: "last_month", from: "2026-09-01", to: "2026-09-30" } });
    await view.submit();
    assert.equal(calls[1].url.searchParams.get("start"), "2026-09-01");
    assert.equal(calls[1].url.searchParams.get("end"), "2026-09-30");
  } finally { await view.close(); }
});

test("through today waits for this period's server end date", async () => {
  const view = await mount();
  try {
    await view.render({ period: { key: "this_month", from: "2026-11-01", to: null } });
    assert.equal(view.button(), undefined);
    await view.render({ records: { ...view.context.records, overview: { ...view.context.records.overview!, from: "2026-11-01", to: "2026-11-02" } } });
    await view.submit();
    assert.equal(calls[0].url.searchParams.get("end"), "2026-11-02");
  } finally { await view.close(); }
});

for (const [status, pattern] of [[403, /acceso actual/], [404, /acceso actual/], [413, /período más corto/], [503, /No se pudo descargar/]] as const) test(`export refusal ${status} keeps the error visible and permits retry`, async () => {
  const view = await mount(client);
  try {
    respond = async () => new Response(JSON.stringify({ code: "export_refused" }), { status });
    await view.submit();
    assert.match(view.host.querySelector('[role="alert"]')!.textContent!, pattern);
    assert.equal(downloads.length, 0);
    assert.equal(view.button()!.disabled, false);
    respond = async () => new Response(bytes, { headers: { "Content-Type": "application/zip" } });
    await view.submit();
    assert.equal(downloads.length, 1);
    assert.equal(view.host.querySelector('[role="alert"]'), null);
  } finally { await view.close(); }
});

for (const change of ["business", "period", "permission", "session"] as const) test(`changing ${change} rejects an in-flight export`, async () => {
  const view = await mount(client);
  let finish!: (response: Response) => void;
  try {
    respond = async () => new Promise((resolve) => { finish = resolve; });
    await view.submit();
    assert.equal(calls.length, 1);
    await act(async () => view.host.querySelector<HTMLButtonElement>('button[type="submit"]:disabled')?.click());
    assert.equal(calls.length, 1);
    if (change === "business") await view.render({ chosen: own });
    if (change === "period") await view.render({ period: { key: "last_month", from: "2026-09-01", to: "2026-09-30" } });
    if (change === "permission") await view.render({ chosen: { ...client, capabilities: [] } });
    if (change === "session") invalidateBrowserAuth();
    await act(async () => finish(new Response(bytes, { headers: { "Content-Type": "application/zip" } })));
    assert.equal(downloads.length, 0);
    if (change !== "session") assert.equal(calls[0].init?.signal?.aborted, true);
    if (change === "permission") assert.equal(view.button(), undefined);
  } finally { await view.close(); }
});

test("a changed grant before a click never exports a different Business", async () => {
  const view = await mount(client);
  try {
    setChosenGrant("different-grant");
    await view.submit();
    assert.equal(calls.length, 0);
    assert.equal(downloads.length, 0);
    assert.ok(view.host.querySelector('[role="alert"]'));
  } finally { await view.close(); }
});

test("preview and unreadable Businesses never dispatch exports", async () => {
  const view = await mount({ ...client, capabilities: [] });
  try {
    assert.equal(view.button(), undefined);
    await view.render({ chosen: own, source: { ...view.context.source, mode: "fixture" } });
    assert.equal(view.button()!.disabled, true);
    await act(async () => view.button()!.click());
    assert.equal(calls.length, 0);
    assert.match(view.host.textContent!, /vista conectada/);
  } finally { await view.close(); }
});
