import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import ExportRecordsPanel from "@/components/business-app/ExportRecordsPanel";
import { useMonthCloseSource } from "@/components/business-app/BusinessMonthClosePanel";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { setChosenGrant } from "@/lib/business-grant";
import { invalidateBrowserAuth } from "@/lib/browser-auth-generation";
import type { GrantedSpace } from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";
import { currentMonthKey, shiftMonthKey, windowForMonth } from "@/lib/business-month-close";

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
    if (url.pathname.endsWith("/business/fiscal-profile")) return Response.json({ name: "Taller Luna", tax_id: null, can_edit: false });
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
    panel: { kind: "expenses" }, actions: { create: [] }, spaces: [chosen],
    setPeriod: () => undefined,
  } as unknown as BusinessContextValue;
  // The sheet as the workspace opens it from Agregar or search: this month, over any screen.
  function Sheet() {
    const [shown, setShown] = useState(true);
    const monthClose = useMonthCloseSource();
    return shown
      ? <ExportRecordsPanel month={currentMonthKey()} monthClose={monthClose} onClose={() => setShown(false)} />
      : <button type="button" data-testid="reopen-export" onClick={() => setShown(true)}>Exportar registros</button>;
  }
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const render = async (patch: Partial<BusinessContextValue> = {}) => {
    context = { ...context, ...patch };
    setChosenGrant(context.chosen?.role === "accountant" ? context.chosen.grant_id : null);
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Sheet /></BusinessContext.Provider></I18nextProvider>));
  };
  await render();
  const button = () => document.querySelector<HTMLButtonElement>('[data-testid="export-download"]') ?? undefined;
  const open = async () => {
    if (button()) return;
    const door = host.querySelector<HTMLButtonElement>('[data-testid="reopen-export"]');
    assert.ok(door, "the closed sheet can open again");
    await act(async () => { door.click(); });
    for (let i = 0; i < 10; i += 1) await act(async () => { await Promise.resolve(); });
  };
  const submit = async () => { await open(); assert.ok(button(), "the export panel shows Exportar"); await act(async () => { button()!.click(); }); };
  const choose = async (key: string) => { await open(); await act(async () => { document.querySelector<HTMLButtonElement>(`[data-testid="export-period"] [data-segment="${key}"]`)!.click(); }); };
  return { host, context, render, button, open, submit, choose, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

const thisMonth = windowForMonth(currentMonthKey());
const exports = () => calls.filter((call) => call.url.pathname.endsWith("/business/exports"));

for (const chosen of [own, client]) test(`Exportar registros downloads this month's ZIP for ${chosen.role}`, async () => {
  const view = await mount(chosen);
  try {
    await view.submit();
    assert.equal(exports().length, 1);
    assert.deepEqual([...exports()[0].url.searchParams], [["start", thisMonth.from], ["end", thisMonth.to]]);
    assert.equal(new Headers(exports()[0].init?.headers).get("X-Business-Grant"), chosen.role === "accountant" ? chosen.grant_id : null);
    assert.equal(downloads.length, 1);
    assert.deepEqual(new Uint8Array(await downloads[0].blob.arrayBuffer()), bytes);
    assert.equal(downloads[0].filename, `business-export-${thisMonth.from}-${thisMonth.to}.zip`);
    assert.equal(view.button(), undefined, "a finished download closes the panel");
  } finally { await view.close(); }
});

test("the export downloads the period chosen in the panel, whatever the workspace period", async () => {
  const view = await mount();
  try {
    await view.render({ period: { key: "all", from: "2000-01-01", to: "2026-10-17" } });
    await view.choose("last_month");
    const previous = windowForMonth(shiftMonthKey(currentMonthKey(), -1));
    await view.submit();
    assert.deepEqual([...exports()[0].url.searchParams], [["start", previous.from], ["end", previous.to]]);
    assert.equal(downloads[0].filename, `business-export-${previous.from}-${previous.to}.zip`);
    await view.choose("year");
    const year = currentMonthKey().slice(0, 4);
    await view.submit();
    assert.deepEqual([...exports()[1].url.searchParams], [["start", `${year}-01-01`], ["end", `${year}-12-31`]]);
  } finally { await view.close(); }
});

for (const [status, pattern] of [[403, /acceso actual/], [404, /acceso actual/], [413, /período más corto/], [503, /No se pudo descargar/]] as const) test(`export refusal ${status} keeps the error visible and permits retry`, async () => {
  const view = await mount(client);
  try {
    respond = async () => new Response(JSON.stringify({ code: "export_refused" }), { status });
    await view.submit();
    assert.match(document.querySelector('[role="alert"]')!.textContent!, pattern);
    assert.equal(downloads.length, 0);
    assert.equal(view.button()!.disabled, false);
    respond = async () => new Response(bytes, { headers: { "Content-Type": "application/zip" } });
    await view.submit();
    assert.equal(downloads.length, 1);
    assert.equal(document.querySelector('[role="alert"]'), null);
  } finally { await view.close(); }
});

for (const change of ["business", "month", "permission", "session"] as const) test(`changing ${change} rejects an in-flight export`, async () => {
  const view = await mount(client);
  let finish!: (response: Response) => void;
  try {
    respond = async () => new Promise((resolve) => { finish = resolve; });
    await view.submit();
    assert.equal(exports().length, 1);
    await act(async () => view.button()?.click());
    assert.equal(exports().length, 1);
    if (change === "business") await view.render({ chosen: own });
    if (change === "month") await view.choose("last_month");
    if (change === "permission") await view.render({ chosen: { ...client, capabilities: [] } });
    if (change === "session") invalidateBrowserAuth();
    await act(async () => finish(new Response(bytes, { headers: { "Content-Type": "application/zip" } })));
    assert.equal(downloads.length, 0);
    if (change !== "session") assert.equal(exports()[0].init?.signal?.aborted, true);
    if (change === "permission") assert.equal(view.button(), undefined);
  } finally { await view.close(); }
});

test("a changed grant before a click never exports a different Business", async () => {
  const view = await mount(client);
  try {
    setChosenGrant("different-grant");
    await view.submit();
    assert.equal(exports().length, 0);
    assert.equal(downloads.length, 0);
    assert.ok(document.querySelector('[role="alert"]'));
  } finally { await view.close(); }
});

test("preview and unreadable Businesses never dispatch exports", async () => {
  const view = await mount({ ...client, capabilities: [] });
  try {
    assert.ok(document.querySelector('[data-testid="export-records-panel"]'), "the sheet opens");
    assert.equal(view.button(), undefined, "no read, no Exportar in the sheet");
    await view.render({ chosen: own, source: { ...view.context.source, mode: "fixture" } });
    await view.open();
    assert.equal(view.button()!.disabled, true);
    await act(async () => view.button()!.click());
    assert.equal(exports().length, 0);
    assert.match(document.body.textContent!, /vista conectada/);
  } finally { await view.close(); }
});
