import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { GrantedSpace, ReceiptSummary } from "@/lib/business-api";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";
import { invoiceScope, savedCustomer } from "./fixtures/business-invoice-fixture";

// A Business list screen offers one search: on a wide screen with the bar's search on, the list lends its query to
// the top bar and drops its own field; a phone, or a build without bar search, keeps the list's own field.
const realListSearch = { ...await import("@/components/business-app/foundation/list-search") };
const barSearch = (available: boolean) => mock.module("@/components/business-app/foundation/list-search", () => ({ ...realListSearch, barSearchAvailable: available }));

const original = { node: process.env.NODE_ENV, mock: process.env.NEXT_PUBLIC_MOCK_AUTH, fetch: globalThis.fetch, grant: getChosenGrant() };
let cleanup = async () => {};
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); });
afterEach(async () => {
  await cleanup(); cleanup = async () => {};
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
  globalThis.fetch = original.fetch;
  setChosenGrant(original.grant);
  window.history.replaceState(null, "", "/biz");
  if (original.node === undefined) Reflect.deleteProperty(process.env, "NODE_ENV"); else Reflect.set(process.env, "NODE_ENV", original.node);
  if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
  barSearch(realListSearch.barSearchAvailable);
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

type Screen = "inbox" | "invoicing";

async function mount(screen: Screen, list: (parts: { act: typeof import("react").act }) => Promise<ReactNode>, { width }: { width: number }) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const BusinessHeader = (await import("@/components/business-app/foundation/BusinessHeader")).default;
  const source = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const seed = (await source.receipts("all"))[0];
  const receipts: ReceiptSummary[] = [{ ...seed, id: "review-receipt", merchant: "Recibo admitido", bandeja: { por_revisar: true, leyendo: false, con_problema: false } }];
  const chosen: GrantedSpace = { space_id: invoiceScope.businessId, grant_id: invoiceScope.grantId!, name: "Negocio sintético", role: "owner", capabilities: ["read", "prepare"], permissions: ["read", "prepare", "approve", "manage", "download", "export"], access_seen: true };
  const context: BusinessContextValue = {
    userId: invoiceScope.userId, source: { ...source, receiptPage: async () => ({ items: receipts }) },
    records: { workspace: await source.workspace(), overview: null, inbox: receipts, notes: [], notesTruncated: false, emails: [], error: false },
    spaces: [chosen], chosen, chooseBusiness: () => {}, markAccessSeen: async () => {}, lostAccess: false, clearLostAccess: () => {}, revision: 0, reload: () => {}, refresh: async () => "updated",
    period: { key: "all", from: "", to: null }, setPeriod: () => {}, panel: { kind: screen }, openPanel: () => {},
    actions: { create: [], composer: [], starterEntries: [] },
    bridge: null, attachedReceipt: null, clearAttachedReceipt: () => {}, openExport: () => {}, emailRefresh: { refresh: () => {}, refreshing: false, stalled: false }, retrySources: () => {},
  };
  const content = await list({ act });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  // The shell shows the Business top bar only on a wide screen; a phone has its own search icon instead.
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>{width >= 768 ? <header data-testid="top-bar"><BusinessHeader home={false} name={null} screen={screen} onSearch={() => {}} /></header> : null}{content}</BusinessContext.Provider></I18nextProvider>); });
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  const settle = async (ready: () => boolean) => { for (let i = 0; i < 50; i++) { if (ready()) return; await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); }); } throw new Error(`Missing expected state: ${host.textContent}`); };
  const click = async (node: Element | null | undefined) => { assert.ok(node instanceof HTMLElement); await act(async () => node.click()); };
  const section = (name: string) => click([...host.querySelectorAll("button")].find(button => button.textContent?.trim() === name));
  const bar = () => host.querySelector('[data-testid="top-bar"]');
  const searches = () => ({
    bar: bar()?.querySelectorAll('[data-testid="stable-search"]').length ?? 0,
    own: [...host.querySelectorAll('input[type="search"]')].filter(input => !input.closest('[data-testid="top-bar"]')).length,
  });
  const scope = () => bar()?.querySelector('[data-testid="scoped-search"]')?.textContent ?? null;
  return { host, act, settle, click, section, searches, scope };
}

function invoiceServer() {
  const reads: URL[] = [];
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    reads.push(url);
    if (url.pathname.endsWith("/business/invoices")) return Response.json({ items: [], total: 0, page: 1, page_size: 25, stage_counts: {}, summaries: [], query_version: "synthetic-version", issuance_available: false });
    if (url.pathname.endsWith("/business/customers")) return Response.json({ items: [savedCustomer()], total: 1, page: 1, page_size: 25 });
    return new Response(null, { status: 404 });
  };
  const lastSearch = (path: string) => reads.filter(url => url.pathname.endsWith(path)).at(-1)?.searchParams.get("search") ?? null;
  return { lastSearch };
}

const bandeja = async () => {
  Reflect.set(process.env, "NODE_ENV", "production"); process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  const Inbox = (await import("@/components/business-app/BusinessInboxPanel")).default;
  return <Inbox />;
};
const connectedInvoicing = async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; setChosenGrant(invoiceScope.grantId);
  const Connected = (await import("@/components/business-app/invoicing/ConnectedInvoicingWorkspace")).default;
  return <Connected scope={invoiceScope} business="Negocio sintético" capabilities={{ prepare: true, issue: false, download: true }} />;
};
const previewInvoicing = async () => {
  window.history.replaceState(null, "", "/biz?view=invoicing&invoicePreview=seeded");
  const Preview = (await import("@/components/business-app/invoicing/InvoicingPreview")).default;
  return <Preview />;
};

test("Bandeja at a wide width shows only the bar's search, scoped to Bandeja", async () => {
  barSearch(true);
  const page = await mount("inbox", bandeja, { width: 1440 });
  await page.settle(() => page.host.querySelector('[data-testid="reception-row"]') !== null);
  assert.deepEqual(page.searches(), { bar: 1, own: 0 });
  assert.ok(page.scope()?.startsWith("En Bandeja"));
});

test("each Facturación section at a wide width shows only the bar's search, scoped to that section's own query", async () => {
  barSearch(true);
  const server = invoiceServer();
  const page = await mount("invoicing", connectedInvoicing, { width: 1440 });
  await page.settle(() => server.lastSearch("/business/invoices") !== null);
  assert.deepEqual(page.searches(), { bar: 1, own: 0 }, "Facturas");
  assert.ok(page.scope()?.startsWith("En Facturas"));

  const { applyListSearch } = await import("@/components/business-app/foundation/list-search");
  await page.act(async () => applyListSearch("invoices", "M-007"));
  await page.settle(() => server.lastSearch("/business/invoices") === "M-007");
  assert.ok(page.scope()?.includes("M-007"), "the bar shows the filter the section applied");

  await page.section("Clientes");
  await page.settle(() => server.lastSearch("/business/customers") !== null);
  assert.deepEqual(page.searches(), { bar: 1, own: 0 }, "Clientes");
  assert.ok(page.scope()?.startsWith("En Clientes"));
  assert.ok(!page.scope()?.includes("M-007"), "Clientes keeps its own query, apart from Facturas'");
  await page.act(async () => applyListSearch("customers", "Sintético"));
  await page.settle(() => server.lastSearch("/business/customers") === "Sintético");
  await page.click(page.host.querySelector('[data-testid="scoped-search-clear"]'));
  await page.settle(() => server.lastSearch("/business/customers") === "");

  await page.section("Programadas");
  assert.deepEqual(page.searches(), { bar: 1, own: 0 }, "Programadas has no list yet, so only the bar searches");
  assert.equal(page.scope(), null);

  await page.section("Facturas");
  await page.settle(() => page.scope()?.includes("M-007") === true);
});

test("the Facturación preview's three sections at a wide width show only the bar's search", async () => {
  barSearch(true);
  const page = await mount("invoicing", previewInvoicing, { width: 1440 });
  await page.settle(() => page.scope() !== null);
  for (const [name, place] of [["Facturas", "En Facturas"], ["Clientes", "En Clientes"], ["Programadas", "En Programadas"]] as const) {
    await page.section(name);
    assert.deepEqual(page.searches(), { bar: 1, own: 0 }, name);
    assert.ok(page.scope()?.startsWith(place), name);
  }
});

test("a phone keeps each list's own search field", async () => {
  barSearch(true);
  const inbox = await mount("inbox", bandeja, { width: 390 });
  await inbox.settle(() => inbox.host.querySelector('[data-testid="reception-row"]') !== null);
  assert.deepEqual(inbox.searches(), { bar: 0, own: 1 }, "Bandeja");
  await cleanup(); cleanup = async () => {};
  invoiceServer();
  const connected = await mount("invoicing", connectedInvoicing, { width: 390 });
  assert.deepEqual(connected.searches(), { bar: 0, own: 1 }, "Facturas");
  await connected.section("Clientes");
  assert.deepEqual(connected.searches(), { bar: 0, own: 1 }, "Clientes");
  await cleanup(); cleanup = async () => {};
  const preview = await mount("invoicing", previewInvoicing, { width: 390 });
  for (const name of ["Facturas", "Clientes", "Programadas"]) {
    await preview.section(name);
    assert.deepEqual(preview.searches(), { bar: 0, own: 1 }, name);
  }
});

test("without the bar's search every list keeps its own field and the bar lends no scope", async () => {
  barSearch(false);
  const inbox = await mount("inbox", bandeja, { width: 1440 });
  await inbox.settle(() => inbox.host.querySelector('[data-testid="reception-row"]') !== null);
  assert.equal(inbox.searches().own, 1, "Bandeja");
  assert.equal(inbox.scope(), null);
  await cleanup(); cleanup = async () => {};
  const preview = await mount("invoicing", previewInvoicing, { width: 1440 });
  for (const name of ["Facturas", "Clientes", "Programadas"]) {
    await preview.section(name);
    assert.equal(preview.searches().own, 1, name);
    assert.equal(preview.scope(), null, name);
  }
});
