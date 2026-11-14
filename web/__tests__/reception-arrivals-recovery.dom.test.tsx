import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace, ReceiptSummary } from "@/lib/business-api";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

const originalEnvironment = { node: process.env.NODE_ENV, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
let cleanup = async () => {};
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => {
  await cleanup(); cleanup = async () => {};
  document.body.innerHTML = "";
  if (originalEnvironment.node === undefined) Reflect.deleteProperty(process.env, "NODE_ENV"); else Reflect.set(process.env, "NODE_ENV", originalEnvironment.node);
  if (originalEnvironment.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalEnvironment.mock;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const ACTIVITY = { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 1, needs_attention_count: 0, ready_to_review_count: 1 };

/** The live Bandeja over a source whose full read the test can break, and a poll the test can tick. */
async function mount(language: "es-419" | "en" = "es-419", panel: BusinessContextValue["panel"] = { kind: "inbox" }) {
  Reflect.set(process.env, "NODE_ENV", "production");
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const Inbox = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const source = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default }, en: { translation: (await import("@/public/locales/en/common.json")).default } }, interpolation: { escapeValue: false } });
  const seed = (await source.receipts("all"))[0];
  const receipt = (id: string): ReceiptSummary => ({ ...seed, id, merchant: `Recibo ${id}`, bandeja: { por_revisar: true, leyendo: false, con_problema: false } });
  let receipts = [receipt("uno")];
  const calls: string[] = [];
  const read = { failure: null as Error | null };
  const chosen: GrantedSpace = { space_id: "recovery-business", grant_id: "recovery-grant", name: "Negocio sintético", role: "owner", capabilities: ["read", "prepare"], access_seen: true };
  let context: BusinessContextValue = {
    userId: "recovery-person",
    source: { ...source, receiptPage: async (view: string) => { calls.push(view); if (view === "all" && read.failure) throw read.failure; return { items: receipts, activity: ACTIVITY }; } },
    records: { workspace: await source.workspace(), overview: null, inbox: receipts, notes: [], notesTruncated: false, emails: [], error: false, receiptActivity: ACTIVITY },
    spaces: [chosen], chosen, chooseBusiness: () => {}, markAccessSeen: async () => {}, lostAccess: false, clearLostAccess: () => {}, revision: 0, reload: () => {}, refresh: async () => "updated",
    period: { key: "all", from: "", to: null }, setPeriod: () => {}, panel, openPanel: () => {},
    actions: { create: [], composer: [], starterEntries: [] },
    bridge: null, attachedReceipt: null, clearAttachedReceipt: () => {}, emailRefresh: { refresh: () => {}, refreshing: false, stalled: false }, retrySources: () => {},
  };
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const render = () => act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Inbox /></BusinessContext.Provider></I18nextProvider>); });
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  const wait = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 40)); });
  const alert = () => host.querySelector<HTMLElement>('[role="alert"]');
  const titles = () => [...host.querySelectorAll('[data-testid="reception-row"]')].map(row => row.textContent ?? "");
  const allReads = () => calls.filter(view => view === "all").length;
  return {
    host, alert, titles, allReads, act, wait,
    start: async () => { await render(); await wait(); },
    breakRead: (error: Error) => { read.failure = error; },
    healRead: () => { read.failure = null; },
    /** The poll hands a new array each tick; the content is the same unless `next` says otherwise. */
    tick: async (next?: ReceiptSummary[]) => {
      if (next) receipts = next;
      context = { ...context, records: { ...context.records, inbox: receipts.map(item => ({ ...item })) } };
      await render(); await wait();
    },
    receipt,
    receipts: () => receipts,
  };
}

const serverError = () => Object.assign(new Error("API error 500"), { status: 500, code: "internal_error" });
const offlineError = () => new TypeError("Failed to fetch");

test("a healthy list re-reads only when the poll carries changed content", async () => {
  const page = await mount();
  await page.start();
  assert.equal(page.alert(), null);
  assert.equal(page.allReads(), 1, "one full read on arrival");
  await page.tick();
  await page.tick();
  assert.equal(page.allReads(), 1, "ticks with the same content do not re-read");
  await page.tick([...page.receipts(), page.receipt("dos")]);
  assert.equal(page.allReads(), 2, "a changed tick re-reads once");
  assert.equal(page.titles().length, 2, "the new arrival is in the list");
});

test("after a failed full read, the next poll tick asks again even when the content is unchanged", async () => {
  const page = await mount();
  page.breakRead(offlineError());
  await page.start();
  assert.ok(page.alert(), "the failure is said");
  assert.equal(page.titles().length, 0);
  const failedReads = page.allReads();
  page.healRead();
  await page.tick();
  assert.equal(page.alert(), null, "the unchanged tick recovered the list");
  assert.equal(page.titles().length, 1);
  assert.equal(page.allReads(), failedReads + 1);
  await page.tick();
  assert.equal(page.allReads(), failedReads + 1, "healthy again, so unchanged ticks stop re-reading");
});

test("after a failed full read, the connection returning asks again without waiting for a tick", async () => {
  const page = await mount();
  page.breakRead(offlineError());
  await page.start();
  assert.ok(page.alert());
  page.healRead();
  await page.act(async () => { window.dispatchEvent(new Event("online")); });
  await page.wait();
  assert.equal(page.alert(), null);
  assert.equal(page.titles().length, 1);
});

test("a server failure offers Reintentar, and a refusal does not ask again on a tick", async () => {
  const retryable = await mount();
  retryable.breakRead(serverError());
  await retryable.start();
  const retry = [...retryable.alert()!.querySelectorAll("button")].find(button => button.textContent === "Reintentar");
  assert.ok(retry, "a retryable failure shows Reintentar");
  retryable.healRead();
  await retryable.act(async () => retry.click());
  await retryable.wait();
  assert.equal(retryable.alert(), null);
  assert.equal(retryable.titles().length, 1);
  await cleanup(); cleanup = async () => {};

  const refused = await mount();
  refused.breakRead(Object.assign(new Error("Business is not available."), { status: 404, code: "business_unavailable" }));
  await refused.start();
  const reads = refused.allReads();
  await refused.tick();
  assert.equal(refused.allReads(), reads, "asking again would get the same refusal");
});

const arrivedTitles = (page: Awaited<ReturnType<typeof mount>>) => [...page.host.querySelectorAll('[data-testid="reception-row"][data-arrived="true"]')].map(row => row.textContent ?? "");
const later = (page: Awaited<ReturnType<typeof mount>>, id: string, minutes: number): ReceiptSummary => ({ ...page.receipt(id), received_at: new Date(Date.parse(page.receipts()[0].received_at) + minutes * 60000).toISOString() });

for (const language of ["es-419", "en"] as const) test(`a new arrival lands at the top on its own, marked for a moment, with no bar to press in ${language}`, async () => {
  const { ARRIVAL_HIGHLIGHT_MS } = await import("@/components/business-app/foundation/list-arrivals");
  const page = await mount(language);
  await page.start();
  assert.deepEqual(arrivedTitles(page), [], "the rows the screen opened with are not marked");
  await page.tick([...page.receipts(), later(page, "dos", 1)]);
  assert.match(page.titles()[0], /Recibo dos/);
  assert.equal(arrivedTitles(page).length, 1);
  assert.match(arrivedTitles(page)[0], /Recibo dos/);
  assert.equal(page.host.querySelector('[role="status"]'), null, "no bar announces it");
  assert.equal([...page.host.querySelectorAll("button")].some(button => /Actualizar lista|Update list/.test(button.textContent ?? "")), false);
  await page.act(async () => { await new Promise(resolve => setTimeout(resolve, ARRIVAL_HIGHLIGHT_MS + 100)); });
  assert.deepEqual(arrivedTitles(page), [], "the mark goes away by itself");
  assert.equal(page.titles().length, 2);
}, 10000);

test("rows already shown keep their order when a later one arrives, and an open record stays open", async () => {
  const page = await mount("es-419", { kind: "receipt", receiptId: "uno", list: "inbox" });
  await page.start();
  const open = () => page.host.querySelector('[data-testid="reception-row"][aria-current="true"]')?.textContent ?? "";
  assert.match(open(), /Recibo uno/);
  await page.tick([...page.receipts(), later(page, "dos", 1), later(page, "tres", 2)]);
  assert.match(page.titles().join("|"), /Recibo tres.*\|.*Recibo dos.*\|.*Recibo uno/);
  // The server now sorts "uno" first; the screen keeps what the person was looking at where it was.
  await page.tick(page.receipts().map(item => item.id === "uno" ? later(page, "uno", 9) : item));
  assert.match(page.titles().join("|"), /Recibo tres.*\|.*Recibo dos.*\|.*Recibo uno/);
  assert.match(open(), /Recibo uno/);
});

test("rows that land above what the person is reading do not move it; at the top they simply show", async () => {
  const ROW = 40;
  const page = await mount();
  await page.tick(["a", "b", "c", "d", "e"].map((id, index) => later(page, id, -index)));
  let scrolled = 2.5 * ROW;
  const moves: number[] = [];
  const rect = HTMLElement.prototype.getBoundingClientRect;
  const scrollBy = window.scrollBy;
  HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
    const index = [...document.querySelectorAll("[data-list-row]")].indexOf(this);
    const top = index < 0 ? 0 : index * ROW - scrolled;
    return { top, bottom: top + ROW, left: 0, right: 0, width: 0, height: ROW, x: 0, y: top, toJSON: () => ({}) };
  };
  window.scrollBy = ((_x: number, y: number) => { moves.push(y); scrolled += y; }) as typeof window.scrollBy;
  try {
    await page.tick([...page.receipts(), later(page, "nuevo", 5)]);
    assert.deepEqual(moves, [ROW], "the page scrolls by exactly the height that landed above");
    scrolled = 0; moves.length = 0;
    await page.tick([...page.receipts(), later(page, "otro", 6)]);
    assert.deepEqual(moves, [], "at the top of the list the new row is simply there");
    assert.match(page.titles()[0], /Recibo otro/);
  } finally { HTMLElement.prototype.getBoundingClientRect = rect; window.scrollBy = scrollBy; }
});
