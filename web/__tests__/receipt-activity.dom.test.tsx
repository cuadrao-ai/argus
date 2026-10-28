import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { periodRange } from "@/components/business-app/business-format";
import { inboxCount } from "@/components/business-app/inbox-count";
import ReceiptReadingControl from "@/components/business-app/ReceiptReadingControl";
import { BusinessConsentTestProvider } from "@/components/business-app/business-consent-context";
import ReceiptDossierReview from "@/components/business-app/ReceiptDossierReview";
import { dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import ReceiptSeenBoundary from "@/components/business-app/ReceiptSeenBoundary";
import { useReceiptInboxRefresh } from "@/components/business-app/useReceiptInboxRefresh";
import type { ReceiptActivityCounts, ReceiptDetail, ReceiptReading } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import english from "@/public/locales/en/common.json";

let hidden = false;
let focused = true;
const intersections = new Set<IntersectionObserverCallback>();
let observerInstance: IntersectionObserver;
const i18n = i18next.createInstance();

beforeAll(async () => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => hidden ? "hidden" : "visible" });
  Object.defineProperty(document, "hasFocus", { configurable: true, value: () => focused });
  const Original = globalThis.IntersectionObserver;
  globalThis.IntersectionObserver = class extends Original {
    constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) { super(callback, options); intersections.add((entries, observer) => callback(entries, observer)); }
    observe(target: Element) { observerInstance = new Original(() => {}); super.observe(target); }
    disconnect() { intersections.clear(); super.disconnect(); }
  };
  await i18n.init({ lng: "en", resources: { en: { translation: english } } });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

function clock() {
  let due: (() => void) | null = null;
  let delay = 0;
  return { schedule: (fn: () => void, ms: number) => { due = fn; delay = ms; return () => { due = null; }; }, delay: () => due ? delay : null,
    tick: async () => { const fn = due; due = null; await act(async () => { fn?.(); await Promise.resolve(); await Promise.resolve(); }); } };
}

function context(source: BusinessDataSource, reload: () => void): BusinessContextValue {
  return { source, records: { workspace: null, overview: null, inbox: [], notes: [], notesError: false, notesTruncated: false, error: false },
    spaces: [], chosen: null, chooseBusiness: () => {}, markAccessSeen: async () => {}, lostAccess: false, revision: 0, reload,
    period: periodRange("this_month"), setPeriod: () => {}, panel: { kind: "receipt", receiptId: "r1" }, openPanel: () => {},
    actions: { create: [], composer: [], starterEntries: [] }, bridge: null, attachedReceipt: null, clearAttachedReceipt: () => {} };
}

async function host() { const element = document.createElement("div"); document.body.appendChild(element); return { element, root: createRoot(element) }; }
const counts: ReceiptActivityCounts = { reading_count: 0, unread_count: 1, presentation: "unread", pending_review_count: 2, needs_attention_count: 0, ready_to_review_count: 2 };

async function receipt(): Promise<ReceiptDetail> { const source = createFixtureBusinessDataSource(); const rows = await source.receipts("inbox"); return { ...await source.receipt(rows[0].id), id: "r1", activity: { state: "ready", unread: true, completion_cursor: "a".repeat(64) } }; }

function intersect(element: Element) {
  const bounds = element.getBoundingClientRect();
  const entry: IntersectionObserverEntry = { target: element, isIntersecting: true, intersectionRatio: 1, boundingClientRect: bounds, intersectionRect: bounds, rootBounds: bounds, time: 0 };
  for (const callback of intersections) callback([entry], observerInstance);
}

test("visible idle discovery uses 15 seconds, reading uses 5, and hidden/unmounted views stop", async () => {
  hidden = false;
  const timer = clock();
  let asked = 0;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live", receiptPage: async () => { asked++; return { items: [], activity: counts }; } };
  function Harness({ reading, active = true }: { reading: boolean; active?: boolean }) { useReceiptInboxRefresh({ source, reading, active, businessKey: "A", clock: timer.schedule, onRefresh: () => {} }); return null; }
  const page = await host();
  await act(async () => page.root.render(<Harness reading={false} />));
  assert.equal(timer.delay(), 15000);
  await timer.tick();
  assert.equal(asked, 1);
  await act(async () => page.root.render(<Harness reading />));
  assert.equal(timer.delay(), 5000);
  hidden = true;
  await act(async () => document.dispatchEvent(new Event("visibilitychange")));
  assert.equal(timer.delay(), null);
  await timer.tick();
  assert.equal(asked, 1);
  hidden = false;
  await act(async () => window.dispatchEvent(new Event("focus")));
  assert.equal(asked, 2);
  await act(async () => page.root.unmount());
  assert.equal(timer.delay(), null);
});

test("switching Business aborts discovery and ignores the old response", async () => {
  const timer = clock();
  let resolve!: (page: { items: ReceiptDetail[]; activity: ReceiptActivityCounts }) => void;
  let oldSignal: AbortSignal | undefined;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live", receiptPage: async (_view, signal) => { oldSignal = signal; return new Promise((done) => { resolve = done; }); } };
  let refreshed = 0;
  function Harness({ business }: { business: string }) { useReceiptInboxRefresh({ source, reading: false, active: true, businessKey: business, clock: timer.schedule, onRefresh: () => { refreshed++; } }); return null; }
  const page = await host();
  await act(async () => page.root.render(<Harness business="A" />));
  await timer.tick();
  await act(async () => page.root.render(<Harness business="B" />));
  assert.equal(oldSignal?.aborted, true);
  await act(async () => resolve({ items: [], activity: counts }));
  assert.equal(refreshed, 0);
  await act(async () => page.root.unmount());
});

test("the badge uses the server count and an unknown count is never 0", () => {
  assert.equal(inboxCount({ receiptActivity: null }), null);
  assert.equal(inboxCount({ receiptActivity: { ...counts, ready_to_review_count: 1 } }), 1);
});

test("opening or old hydration does not mark seen; focused visible hydrated content does", async () => {
  const detail = await receipt();
  let marked = 0;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), markReceiptRead: async (_id, cursor) => { marked++; return { state: "ready", unread: false, completion_cursor: cursor }; } };
  const value = context(source, () => {});
  const page = await host();
  const render = (hydrated: boolean) => <I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><ReceiptSeenBoundary receipt={detail} hydrated={hydrated} /></BusinessContext.Provider></I18nextProvider>;
  await act(async () => page.root.render(render(false)));
  assert.equal(marked, 0);
  await act(async () => intersect(page.element));
  assert.equal(marked, 0);
  focused = false;
  await act(async () => page.root.render(render(true)));
  await act(async () => intersect(page.element));
  assert.equal(marked, 0);
  hidden = true; focused = true;
  await act(async () => window.dispatchEvent(new Event("focus")));
  assert.equal(marked, 0);
  hidden = false;
  await act(async () => document.dispatchEvent(new Event("visibilitychange")));
  assert.equal(marked, 1);
  await act(async () => page.root.unmount());
});


test("an unpaid NCF due notice shows Factura por pagar on the dossier", async () => {
  const fixture = createFixtureBusinessDataSource();
  const marked = { ...await fixture.dossier(dossierFixtureIds.ready), bill_mark: "Factura por pagar" as const };
  const detail = { ...await receipt(), draft_id: marked.draft_id, version: marked.version };
  const source: BusinessDataSource = { ...fixture, dossier: async () => marked };
  const page = await host();
  await act(async () => page.root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context(source, () => {})}><ReceiptDossierReview draftId={marked.draft_id} receipt={detail} /></BusinessContext.Provider></I18nextProvider>));
  assert.equal(page.element.querySelector('[data-testid="bill-mark"]')?.textContent, "Factura por pagar");
  await act(async () => page.root.unmount());
});

test("old dossier hydration cannot consume a newer receipt completion", async () => {
  hidden = false; focused = true;
  const fixture = createFixtureBusinessDataSource();
  const dossier = await fixture.dossier(dossierFixtureIds.ready);
  const detail = { ...await receipt(), draft_id: dossier.draft_id, version: dossier.version + 1 };
  let marked = 0;
  const source: BusinessDataSource = { ...fixture, markReceiptRead: async (_id, cursor) => { marked++; return { state: "ready", unread: false, completion_cursor: cursor }; } };
  const page = await host();
  await act(async () => page.root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context(source, () => {})}><ReceiptDossierReview draftId={dossier.draft_id} receipt={detail} /></BusinessContext.Provider></I18nextProvider>));
  await act(async () => intersect(page.element));
  assert.equal(marked, 0);
  await act(async () => page.root.unmount());
});

test("navigation while acknowledgement is in flight ignores its late UI response", async () => {
  const detail = await receipt();
  let resolve!: (value: NonNullable<ReceiptDetail["activity"]>) => void;
  let reloaded = 0;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), markReceiptRead: async () => new Promise((done) => { resolve = done; }) };
  const page = await host();
  const render = (row: ReceiptDetail) => <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context(source, () => { reloaded++; })}><ReceiptSeenBoundary receipt={row} hydrated /></BusinessContext.Provider></I18nextProvider>;
  await act(async () => page.root.render(render(detail)));
  await act(async () => intersect(page.element));
  await act(async () => page.root.render(render({ ...detail, id: "r2", activity: { state: "ready", unread: true, completion_cursor: "b".repeat(64) } })));
  await act(async () => resolve({ state: "ready", unread: false, completion_cursor: "a".repeat(64) }));
  assert.equal(reloaded, 0);
  await act(async () => page.root.unmount());
});

test("a late reading-toggle response cannot replace another Business disclosure", async () => {
  const reading: ReceiptReading = { scope_version: 1, enabled: false, available: true, can_change: true, disclosure: "Business A disclosure", disclosure_token: "a".repeat(64), route: null, consented_at: null, revoked_at: null };
  let resolve!: (value: ReceiptReading) => void;
  let signal: AbortSignal | undefined;
  let reloads = 0;
  const sourceA: BusinessDataSource = { ...createFixtureBusinessDataSource(), receiptReading: async () => reading, setReceiptReading: async (_reading, _enabled, _language, requestSignal) => { signal = requestSignal; return new Promise((done) => { resolve = done; }); } };
  const sourceB: BusinessDataSource = { ...createFixtureBusinessDataSource(), receiptReading: async () => ({ ...reading, disclosure: "Business B disclosure" }) };
  const page = await host();
  const render = (source: BusinessDataSource) => <I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessContext.Provider value={context(source, () => { reloads++; })}><ReceiptReadingControl /></BusinessContext.Provider></BusinessConsentTestProvider></I18nextProvider>;
  const turnOn = () => [...page.element.querySelectorAll("button")].find((button) => button.textContent === "Turn receipt reading on");
  await act(async () => page.root.render(render(sourceA)));
  await act(async () => turnOn()?.click());
  assert.ok(document.body.textContent?.includes("Business A disclosure"), "the words agreed to sit beside the switch");
  await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="receipt-reading-switch"]')?.click());
  await act(async () => page.root.render(render(sourceB)));
  assert.equal(signal?.aborted, true);
  await act(async () => resolve({ ...reading, enabled: true }));
  assert.equal(document.querySelector('[data-testid="receipt-reading-sheet"]'), null, "the old Business's sheet closed with it");
  assert.equal(reloads, 0);
  assert.equal(turnOn()?.disabled, false);
  await act(async () => turnOn()?.click());
  assert.ok(document.body.textContent?.includes("Business B disclosure"));
  assert.ok(!document.body.textContent?.includes("Business A disclosure"));
  assert.equal(document.querySelector('[data-testid="receipt-reading-switch"]')?.getAttribute("aria-checked"), "false");
  await act(async () => page.root.unmount());
});
