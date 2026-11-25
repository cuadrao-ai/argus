import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { ReceiptSummary } from "@/lib/business-api";

let cleanup = async () => {};
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => { await cleanup(); cleanup = async () => {}; window.localStorage.clear(); });
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(paged: boolean, listVersion: string | null = "version-1") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const Reception = (await import("@/components/business-app/recepcion/ReceptionPreview")).default;
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const seed = (await fixture.receipts("all"))[0];
  const inbox: ReceiptSummary[] = [{ ...seed, id: "inbox-receipt", merchant: "Recibo pendiente" }];
  let all: ReceiptSummary[] = [...inbox, { ...seed, id: "accepted-receipt", merchant: "Recibo aceptado", bandeja_group: { group: null, reason: null, label: "accepted", draft_id: null, version: null } }];
  let reads = 0;
  const readAll = async (view: string) => { assert.equal(view, "all"); reads++; return all; };
  let context: BusinessContextValue = {
    source: { ...fixture, receipts: readAll, receiptPage: paged ? async view => ({ items: await readAll(view), activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 1, ready_to_review_count: 1 } }) : undefined },
    records: { workspace: await fixture.workspace(), overview: null, inbox, listVersion, notes: [], notesTruncated: false, emails: [], error: false },
    spaces: [], chosen: null, chooseBusiness: () => {}, markAccessSeen: async () => {}, lostAccess: false, clearLostAccess: () => {},
    revision: 0, reload: () => {}, refresh: async () => "updated", retrySources: () => {},
    period: { key: "all", from: "", to: null }, setPeriod: () => {}, panel: { kind: "inbox" }, openPanel: () => {},
    actions: { create: [], composer: [], starterEntries: [] }, bridge: null, attachedReceipt: null, clearAttachedReceipt: () => {},
    emailRefresh: { refresh: () => {}, refreshing: false, stalled: false },
  };
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const render = () => act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Reception /></BusinessContext.Provider></I18nextProvider>); });
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await render();
  return {
    host,
    reads: () => reads,
    inbox: () => context.records.inbox,
    titles: () => [...host.querySelectorAll('[data-testid="reception-row"]')].map(row => row.textContent ?? "").join("|"),
    editAccepted: () => { all = all.map(row => row.id === "accepted-receipt" ? { ...row, merchant: "Recibo corregido" } : row); },
    tick: async (next: Partial<BusinessContextValue["records"]> = {}) => {
      context = { ...context, records: { ...context.records, listChecks: (context.records.listChecks ?? 0) + 1, ...next } };
      await render();
    },
  };
}

for (const paged of [true, false]) {
  const method = paged ? "receiptPage" : "receipts";

  test(`${method}: a new list version updates Todos while the inbox stays identical`, async () => {
    const page = await mount(paged);
    const inbox = page.inbox();
    assert.match(page.titles(), /Recibo aceptado/);
    assert.equal(page.reads(), 1);
    page.editAccepted();
    await page.tick({ listVersion: "version-2" });
    assert.strictEqual(page.inbox(), inbox);
    assert.match(page.titles(), /Recibo corregido/);
    assert.doesNotMatch(page.titles(), /Recibo aceptado/);
    assert.equal(page.reads(), 2);
    assert.equal(page.host.querySelector('[role="status"], [role="progressbar"]'), null, "refresh stays quiet");
  });

  test(`${method}: the same list version costs no extra Todos read`, async () => {
    const page = await mount(paged);
    page.editAccepted();
    await page.tick();
    await page.tick({ inbox: page.inbox()!.map(row => ({ ...row })) });
    assert.equal(page.reads(), 1, "answered checks and new array identities do not re-read");
    await page.tick({ inbox: page.inbox()!.map(row => ({ ...row, merchant: "Cambio en inbox" })) });
    assert.equal(page.reads(), 1, "inbox content is not a second trigger when a version exists");
    assert.match(page.titles(), /Recibo aceptado/, "Todos still comes from the all response");
    assert.doesNotMatch(page.titles(), /Cambio en inbox|Recibo corregido/);
  });

  test(`${method}: an unversioned fixture keeps the inbox-content fallback`, async () => {
    const page = await mount(paged, null);
    page.editAccepted();
    await page.tick({ inbox: page.inbox()!.map(row => ({ ...row })) });
    assert.equal(page.reads(), 1);
    await page.tick({ inbox: page.inbox()!.map(row => ({ ...row, merchant: "Cambio en inbox" })) });
    assert.equal(page.reads(), 2);
    assert.match(page.titles(), /Recibo corregido/);
    assert.doesNotMatch(page.titles(), /Cambio en inbox/, "the fallback triggers a read; it never supplies Todos rows");
  });
}
