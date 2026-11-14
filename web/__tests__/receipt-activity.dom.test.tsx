import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
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
const observed = new Set<Element>();
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
    observe(target: Element) { observerInstance = new Original(() => {}); observed.add(target); super.observe(target); }
    disconnect() { intersections.clear(); super.disconnect(); }
  };
  await i18n.init({ lng: "en", resources: { en: { translation: english } } });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

function clock() {
  let due: (() => void) | null = null;
  let delay = 0;
  return { schedule: (fn: () => void, ms: number) => { due = fn; delay = ms; return () => { if (due === fn) due = null; }; }, delay: () => due ? delay : null,
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

const refreshStates = [
  { active: false, reading: false, hidden: false, requests: 0, delay: null },
  { active: false, reading: true, hidden: false, requests: 1, delay: 5000 },
  { active: true, reading: false, hidden: false, requests: 1, delay: 15000 },
  { active: true, reading: true, hidden: false, requests: 1, delay: 5000 },
  { active: false, reading: false, hidden: true, requests: 0, delay: null },
  { active: false, reading: true, hidden: true, requests: 0, delay: null },
  { active: true, reading: false, hidden: true, requests: 0, delay: null },
  { active: true, reading: true, hidden: true, requests: 0, delay: null },
];

test.each(["focus", "visibilitychange"].flatMap((event) => refreshStates.map((state) => ({ event, ...state }))))(
  "$event refresh with active=$active reading=$reading hidden=$hidden",
  async ({ event, active, reading, hidden: pageHidden, requests, delay }) => {
    hidden = pageHidden;
    const timer = clock();
    let asked = 0;
    const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live", receiptPage: async () => { asked++; return { items: [], activity: counts }; } };
    function Harness() { useReceiptInboxRefresh({ source, active, reading, businessKey: "A", clock: timer.schedule, onRefresh: () => {} }); return null; }
    const page = await host();
    try {
      await act(async () => page.root.render(<Harness />));
      assert.equal(asked, 0);
      assert.equal(timer.delay(), delay);
      await act(async () => (event === "focus" ? window : document).dispatchEvent(new Event(event)));
      assert.equal(asked, requests);
      assert.equal(timer.delay(), delay);
      await timer.tick();
      assert.equal(asked, requests * 2);
    } finally {
      await act(async () => page.root.unmount());
      page.element.remove();
      hidden = false;
    }
  },
);

test.each([
  { active: true, reading: false, delay: 15000 },
  { active: false, reading: true, delay: 5000 },
])("refresh follows changes to active=$active reading=$reading and back to idle", async ({ active, reading, delay }) => {
  hidden = false;
  const timer = clock();
  let asked = 0;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live", receiptPage: async () => { asked++; return { items: [], activity: counts }; } };
  function Harness({ active, reading }: { active: boolean; reading: boolean }) { useReceiptInboxRefresh({ source, active, reading, businessKey: "A", clock: timer.schedule, onRefresh: () => {} }); return null; }
  const page = await host();
  try {
    await act(async () => page.root.render(<Harness active={false} reading={false} />));
    assert.equal(timer.delay(), null);
    await act(async () => page.root.render(<Harness active={active} reading={reading} />));
    assert.equal(timer.delay(), delay);
    await act(async () => window.dispatchEvent(new Event("focus")));
    assert.equal(asked, 1);
    await timer.tick();
    assert.equal(asked, 2);
    await act(async () => page.root.render(<Harness active={false} reading={false} />));
    assert.equal(timer.delay(), null);
    await act(async () => window.dispatchEvent(new Event("focus")));
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    await timer.tick();
    assert.equal(asked, 2);
  } finally {
    await act(async () => page.root.unmount());
    page.element.remove();
    hidden = false;
  }
});

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

test.each([
  { reading: true, normal: 5000, delays: [10000, 20000, 40000, 60000, 60000] },
  { reading: false, normal: 15000, delays: [30000, 60000, 60000, 60000, 60000] },
].flatMap((state) => [true, false].map((paged) => ({ ...state, paged }))))(
  "failed refreshes back off and recovery resets with reading=$reading paged=$paged",
  async ({ reading, normal, delays, paged }) => {
    const timer = clock();
    const items = [await receipt()];
    let failing = false;
    let asked = 0;
    let refreshed = 0;
    let displayed: unknown;
    const receipts = async () => {
      asked++;
      if (failing) throw new Error("offline");
      return items;
    };
    const source: BusinessDataSource = {
      ...createFixtureBusinessDataSource(), mode: "live", receipts,
      receiptPage: paged ? async () => ({ items: await receipts(), activity: counts }) : undefined,
    };
    function Harness() {
      useReceiptInboxRefresh({ source, active: true, reading, businessKey: "A", clock: timer.schedule,
        onRefresh: (page) => { refreshed++; displayed = page; } });
      return null;
    }
    const page = await host();
    try {
      await act(async () => page.root.render(<Harness />));
      assert.equal(timer.delay(), normal);
      await timer.tick();
      assert.deepEqual(displayed, { items, activity: paged ? counts : null });
      const lastGood = displayed;
      failing = true;
      for (const delay of delays) {
        await timer.tick();
        assert.equal(timer.delay(), delay);
        assert.equal(refreshed, 1);
        assert.equal(displayed, lastGood);
      }
      assert.equal(asked, 6);
      failing = false;
      await timer.tick();
      assert.equal(refreshed, 2);
      assert.equal(timer.delay(), normal);
      failing = true;
      await timer.tick();
      assert.equal(timer.delay(), delays[0]);
    } finally {
      await act(async () => page.root.unmount());
      page.element.remove();
    }
  },
);

test.each(["focus", "visibilitychange"])("%s refresh bypasses the delay but only success resets failures", async (event) => {
  const timer = clock();
  let asked = 0;
  let failing = true;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live", receiptPage: async () => {
    asked++;
    if (failing) throw new Error("offline");
    return { items: [], activity: counts };
  } };
  function Harness() { useReceiptInboxRefresh({ source, active: true, reading: true, businessKey: "A", clock: timer.schedule, onRefresh: () => {} }); return null; }
  const page = await host();
  try {
    await act(async () => page.root.render(<Harness />));
    await timer.tick();
    await timer.tick();
    assert.equal(asked, 2);
    await act(async () => (event === "focus" ? window : document).dispatchEvent(new Event(event)));
    assert.equal(asked, 3);
    assert.equal(timer.delay(), 40000);
    failing = false;
    await act(async () => (event === "focus" ? window : document).dispatchEvent(new Event(event)));
    assert.equal(asked, 4);
    assert.equal(timer.delay(), 5000);
  } finally {
    await act(async () => page.root.unmount());
    page.element.remove();
  }
});

test("same-Business rerenders and timing changes retain failures", async () => {
  const timer = clock();
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live", receiptPage: async () => { throw new Error("offline"); } };
  function Harness({ active = true, reading = true }: { active?: boolean; reading?: boolean }) {
    useReceiptInboxRefresh({ source, active, reading, businessKey: "A", clock: timer.schedule, onRefresh: () => {} });
    return null;
  }
  const page = await host();
  try {
    await act(async () => page.root.render(<Harness />));
    await timer.tick();
    await act(async () => page.root.render(<Harness />));
    assert.equal(timer.delay(), 10000);
    await act(async () => page.root.render(<Harness reading={false} />));
    assert.equal(timer.delay(), 30000);
    await act(async () => page.root.render(<Harness active={false} reading={false} />));
    assert.equal(timer.delay(), null);
    await act(async () => page.root.render(<Harness />));
    assert.equal(timer.delay(), 10000);
  } finally {
    await act(async () => page.root.unmount());
    page.element.remove();
  }
});

test.each(["success", "failure"])("hidden tabs cancel back-off and ignore an aborted request's late %s", async (outcome) => {
  const timer = clock();
  let asked = 0;
  let refreshed = 0;
  let signal: AbortSignal | undefined;
  let finish!: () => void;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live", receiptPage: async (_view, requestSignal) => {
    asked++;
    if (asked !== 2) throw new Error("offline");
    signal = requestSignal;
    return new Promise((resolve, reject) => { finish = () => outcome === "success" ? resolve({ items: [], activity: counts }) : reject(new Error("aborted")); });
  } };
  function Harness() { useReceiptInboxRefresh({ source, active: true, reading: true, businessKey: "A", clock: timer.schedule, onRefresh: () => { refreshed++; } }); return null; }
  const page = await host();
  try {
    await act(async () => page.root.render(<Harness />));
    await timer.tick();
    hidden = true;
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    assert.equal(timer.delay(), null);
    await timer.tick();
    assert.equal(asked, 1);
    hidden = false;
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    assert.equal(asked, 2);
    hidden = true;
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    assert.equal(signal?.aborted, true);
    await act(async () => finish());
    assert.equal(timer.delay(), null);
    assert.equal(refreshed, 0);
    hidden = false;
    await act(async () => window.dispatchEvent(new Event("focus")));
    assert.equal(asked, 3);
    assert.equal(timer.delay(), 20000);
  } finally {
    await act(async () => page.root.unmount());
    page.element.remove();
    hidden = false;
  }
});

test.each(["success", "failure"])("Business switches reset back-off and ignore a previous Business's late %s", async (outcome) => {
  const timer = clock();
  let asked = 0;
  let refreshed = 0;
  let signal: AbortSignal | undefined;
  let finish!: () => void;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live", receiptPage: async (_view, requestSignal) => {
    asked++;
    if (asked !== 3) throw new Error("offline");
    signal = requestSignal;
    return new Promise((resolve, reject) => { finish = () => outcome === "success" ? resolve({ items: [], activity: counts }) : reject(new Error("offline")); });
  } };
  function Harness({ business }: { business: string }) { useReceiptInboxRefresh({ source, active: true, reading: true, businessKey: business, clock: timer.schedule, onRefresh: () => { refreshed++; } }); return null; }
  const page = await host();
  try {
    await act(async () => page.root.render(<Harness business="A" />));
    await timer.tick();
    await timer.tick();
    await timer.tick();
    await act(async () => page.root.render(<Harness business="B" />));
    assert.equal(signal?.aborted, true);
    assert.equal(timer.delay(), 5000);
    await timer.tick();
    assert.equal(timer.delay(), 10000);
    await act(async () => finish());
    assert.equal(refreshed, 0);
    await timer.tick();
    assert.equal(timer.delay(), 20000);
  } finally {
    await act(async () => page.root.unmount());
    page.element.remove();
  }
});

test("the badge uses the server count and an unknown count is never 0", () => {
  assert.equal(inboxCount({ receiptActivity: null }), null);
  assert.equal(inboxCount({ receiptActivity: { ...counts, pending_review_count: 1 } }), 1);
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


test("the record in view acknowledges it, not only its last line", async () => {
  const detail = await receipt();
  let marked = 0;
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), markReceiptRead: async (_id, cursor) => { marked++; return { state: "ready", unread: false, completion_cursor: cursor }; } };
  const page = await host();
  await act(async () => page.root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context(source, () => {})}><section data-testid="record"><p>Facts</p><ReceiptSeenBoundary receipt={detail} hydrated /></section></BusinessContext.Provider></I18nextProvider>));
  const record = page.element.querySelector('[data-testid="record"]')!;
  assert.ok(observed.has(record), "the boundary watches the record it closes, so a record taller than the screen is seen on open");
  await act(async () => intersect(record));
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
  const turnOn = () => [...page.element.querySelectorAll("button")].find((button) => button.textContent === "Turn on document reading");
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

type Check = { known: string | null; answer: (page: { items: []; activity: ReceiptActivityCounts; version: string } | null) => void; fail: () => void; signal?: AbortSignal };
/** A live source whose change checks the test answers by hand, in any order. */
function checkedSource() {
  const checks: Check[] = [];
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), mode: "live",
    receiptChanges: (known, signal) => new Promise((resolve, reject) => { checks.push({ known, answer: resolve, fail: () => reject(new Error("offline")), signal }); }) };
  const page = (version: string) => ({ items: [] as [], activity: counts, version });
  const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { checks, source, page, settle };
}

test("each check names the version on screen; no change hands over nothing and the rhythm goes on", async () => {
  const timer = clock();
  const { checks, source, page, settle } = checkedSource();
  const seen: (string | null)[] = [];
  function Harness({ known }: { known: string | null }) {
    useReceiptInboxRefresh({ source, active: true, reading: false, businessKey: "A", known, clock: timer.schedule, onRefresh: (answer) => { seen.push(answer ? answer.version ?? null : null); } });
    return null;
  }
  const view = await host();
  try {
    await act(async () => view.root.render(<Harness known={'"v1"'} />));
    await timer.tick();
    assert.equal(checks[0].known, '"v1"');
    checks[0].answer(null);
    await settle();
    assert.deepEqual(seen, [null], "no change: no list to apply");
    assert.equal(timer.delay(), 15000);
    await timer.tick();
    checks[1].answer(page('"v2"'));
    await settle();
    assert.deepEqual(seen, [null, '"v2"']);
    await act(async () => view.root.render(<Harness known={'"v2"'} />));
    await timer.tick();
    assert.equal(checks[2].known, '"v2"', "the next check names what the last one brought");
  } finally { await act(async () => view.root.unmount()); view.element.remove(); }
});

test("a slow check that lands after a reload started is dropped: the newer answer wins (#2116)", async () => {
  const timer = clock();
  const { checks, source, page, settle } = checkedSource();
  const applied: (string | null)[] = [];
  function Harness({ epoch }: { epoch: number }) {
    useReceiptInboxRefresh({ source, active: true, reading: false, businessKey: "A", known: '"v1"', epoch, clock: timer.schedule, onRefresh: (answer) => { if (answer) applied.push(answer.version ?? null); } });
    return null;
  }
  const view = await host();
  try {
    await act(async () => view.root.render(<Harness epoch={0} />));
    await timer.tick();
    assert.equal(checks.length, 1, "the check is in flight");
    // An action reloads: its answer is newer than anything the check can bring.
    await act(async () => view.root.render(<Harness epoch={1} />));
    assert.equal(checks[0].signal?.aborted, true, "the reload cancels the check in flight");
    checks[0].answer(page('"stale"'));
    await settle();
    assert.deepEqual(applied, [], "the older answer never reaches the screen");
    assert.equal(timer.delay(), 15000, "and the rhythm starts again from the reload");
    await timer.tick();
    checks[1].answer(page('"v3"'));
    await settle();
    assert.deepEqual(applied, ['"v3"']);
  } finally { await act(async () => view.root.unmount()); view.element.remove(); }
});

test("with change checks a hidden tab asks nothing and a failed check still backs off", async () => {
  const timer = clock();
  const { checks, source, settle } = checkedSource();
  function Harness() { useReceiptInboxRefresh({ source, active: true, reading: false, businessKey: "A", known: '"v1"', clock: timer.schedule, onRefresh: () => {} }); return null; }
  const view = await host();
  try {
    await act(async () => view.root.render(<Harness />));
    await timer.tick();
    checks[0].fail();
    await settle();
    assert.equal(timer.delay(), 30000, "one failure doubles the wait");
    hidden = true;
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    assert.equal(timer.delay(), null, "hidden: nothing is scheduled");
    await timer.tick();
    assert.equal(checks.length, 1, "hidden: nothing is asked");
    hidden = false;
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    assert.equal(checks.length, 2, "one check when the tab comes back");
    checks[1].answer(null);
    await settle();
    assert.equal(timer.delay(), 15000, "an answer, even no change, clears the back-off");
  } finally { hidden = false; await act(async () => view.root.unmount()); view.element.remove(); }
});
