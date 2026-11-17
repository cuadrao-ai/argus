import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BusinessActivityItem } from "@/lib/business-activity-api";
import type { GrantedSpace } from "@/lib/business-api";
import { SKELETON_DELAY_MS } from "@/components/business-app/business-skeletons";
import { fixtureId } from "./fixtures/business-report-http-fixture";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountAnnotatedReport, unmountConnectedReport } from "./support/business-reports-connected";
import { ShellAccount } from "./support/shell-account";
import { translate } from "./support/i18n-instance";

// DESIGN.md, Loading: a surface's loading view is that surface with its data pending.
// Every main block carries data-surface-block on the component both views share.

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
let unmountScreen = async () => {};
afterEach(async () => { await unmountConnectedReport(); await unmountScreen(); unmountScreen = async () => {}; (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

const pause = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });

/** The outermost marked blocks on screen, in document order. */
const blocks = () => [...document.querySelectorAll<HTMLElement>("[data-surface-block]")]
  .filter((element) => !element.parentElement?.closest("[data-surface-block]"))
  .map((element) => element.dataset.surfaceBlock ?? "");

/** Each loading view the surface passes through, then its loaded view. */
type Views = { loading: string[][]; loaded: string[] };
type Surface = { name: string; width: number; blocks: readonly string[]; views: (width: number) => Promise<Views> };

const registrosAnswered = () => document.querySelector('[data-report-schema="2"] [data-testid="records-count"]') !== null;
const registrosLoading = () => document.querySelector('[data-testid="transacciones-loading"]') !== null && document.querySelector('[data-testid="records-count"]') === null;

/** Registros loads in two steps: the pending layout before the workspace answers, then the connected page before the first report answers. */
async function registrosViews(width: number): Promise<Views> {
  let release!: () => void;
  const queryGate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mountAnnotatedReport({ width, topLevel: true, grantId: fixtureId(3100), workspaceGrant: fixtureId(3101), queryGate, waitForAnswer: false });
  const loading: string[][] = [];
  try {
    await pause(SKELETON_DELAY_MS + 20);
    assert.ok(registrosLoading(), "before the workspace answers");
    loading.push(blocks());
    page.context.records.workspaceGrant = fixtureId(3100);
    await page.rerender();
    assert.ok(registrosLoading(), "before the first report answers");
    loading.push(blocks());
  } finally { await act(async () => release()); }
  await page.settle(registrosAnswered);
  return { loading, loaded: blocks() };
}

const OWNER: GrantedSpace = { space_id: fixtureId(3400), grant_id: fixtureId(3401), name: "Colmado sintético", role: "owner", business_role: "owner", capabilities: ["read", "prepare", "approve"], permissions: ["read", "prepare", "approve", "manage", "assign_owner", "download", "export"], access_seen: true } as GrantedSpace;

/** Mounts one Business screen for a person whose guide is not dismissed, in a live Business. */
async function mountScreen(width: number, screen: ReactNode, context: (base: BusinessContextValue) => Partial<BusinessContextValue>) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const base = {
    source: { ...fixture, mode: "live" }, userId: "synthetic-person", chosen: OWNER, spaces: [OWNER], chooseBusiness: () => {}, markAccessSeen: async () => {}, lostAccess: false, clearLostAccess: () => {},
    receivingChannels: { email: { available: true }, whatsapp: { available: true } },
    records: { workspace: await fixture.workspace(), overview: null, inbox: [], notes: [], notesTruncated: false, emails: [], error: false, receiptActivity: null },
    revision: 0, reload: () => {}, refresh: async () => "updated", retrySources: () => {}, period: { key: "all", from: "", to: null }, setPeriod: () => {},
    panel: { kind: "inbox" }, openPanel: () => {}, actions: { create: [], composer: [], starterEntries: [] },
    bridge: null, attachedReceipt: null, clearAttachedReceipt: () => {}, emailRefresh: { refresh: () => {}, refreshing: false, stalled: false },
  } as unknown as BusinessContextValue;
  const value = { ...base, ...context(base) } as BusinessContextValue;
  const i18n = await translate("es-419");
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><ShellAccount member="synthetic-person" dismissed={[]}>{screen}</ShellAccount></BusinessContext.Provider></I18nextProvider>));
  unmountScreen = async () => { await act(async () => root.unmount()); host.remove(); };
  const settle = async (done: () => boolean) => { for (let i = 0; i < 80 && !done(); i++) await pause(10); assert.ok(done(), document.body.textContent?.slice(-400)); };
  return { settle };
}

/** Captures the loading view as first painted and once its placeholders show, then releases the first page and captures the loaded view. */
async function loadingSteps(isLoading: () => boolean, release: () => void, isLoaded: () => boolean, settle: (done: () => boolean) => Promise<void>): Promise<Views> {
  const loading: string[][] = [];
  try {
    assert.ok(isLoading(), "first paint, before the shared delay");
    loading.push(blocks());
    await pause(SKELETON_DELAY_MS + 20);
    assert.ok(isLoading(), "placeholders shown");
    loading.push(blocks());
  } finally { await act(async () => release()); }
  await settle(isLoaded);
  return { loading, loaded: blocks() };
}

/** Actividad loads in one step: the history card with placeholder days and rows until the feed's first page answers. */
async function actividadViews(width: number): Promise<Views> {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const at = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
  const items: BusinessActivityItem[] = [
    { id: "a1", occurred_at: at(5), actor: { display_name: "Ana Pérez", kind: "member" }, action: "receipt_upload", object: { kind: "receipt", id: "r1", label: "Ferretería sintética" } },
    { id: "a2", occurred_at: at(2 * 24 * 60), actor: { display_name: "Luis Gómez", kind: "member" }, action: "approve_expense", object: { kind: "draft", id: "d1", label: "Colmado sintético" } },
  ];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (!String(input).includes("/business/activity")) throw new Error(`Unexpected request ${String(input)}`);
    await gate;
    return Response.json({ items, next_cursor: null });
  }) as typeof fetch;
  const ActivityDraft = (await import("@/components/business-app/actividad/ActivityDraft")).default;
  try {
    const { settle } = await mountScreen(width, <ActivityDraft />, () => ({ panel: { kind: "activity" } as BusinessContextValue["panel"] }));
    return await loadingSteps(
      () => document.querySelector('[data-testid="activity-loading"]') !== null,
      release,
      () => document.querySelector('[data-testid="activity-loading"]') === null && document.querySelector('[data-surface-block="history"] section[aria-label]') !== null,
      settle,
    );
  } finally { globalThis.fetch = originalFetch; }
}

/** Recepción loads in one step: its tabs, toolbar, column titles and pagination stand while the rows and counts are placeholders. */
async function recepcionViews(width: number): Promise<Views> {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const ReceptionPreview = (await import("@/components/business-app/recepcion/ReceptionPreview")).default;
  const { settle } = await mountScreen(width, <ReceptionPreview />, (base) => {
    const source = base.source;
    return { source: { ...source, receiptPage: async (view: string, signal?: AbortSignal) => { await gate; return source.receiptPage!(view as never, signal); } } as BusinessContextValue["source"] };
  });
  return loadingSteps(
    () => document.querySelector('[data-testid="reception-pending"]') !== null,
    release,
    () => document.querySelector('[data-testid="reception-row"]') !== null,
    settle,
  );
}

const registros = ["guide", "tabs", "overview", "toolbar", "table"] as const;
const actividad = ["guide", "history"] as const;
const recepcion = ["guide", "tabs", "toolbar", "list", "pagination"] as const;
const surfaces: Surface[] = [
  { name: "Registros", width: 1440, blocks: registros, views: registrosViews },
  { name: "Registros", width: 390, blocks: ["heading", ...registros], views: registrosViews },
  { name: "Actividad", width: 1440, blocks: actividad, views: actividadViews },
  { name: "Actividad", width: 390, blocks: ["heading", ...actividad], views: actividadViews },
  { name: "Recepción", width: 1440, blocks: recepcion, views: recepcionViews },
  { name: "Recepción", width: 390, blocks: ["heading", ...recepcion], views: recepcionViews },
];

for (const surface of surfaces) test(`${surface.name} at ${surface.width}px loads as its own layout: the same blocks in the same order`, async () => {
  const { loading, loaded } = await surface.views(surface.width);
  assert.deepEqual(loaded, surface.blocks, "the loaded view has the surface's blocks");
  assert.ok(loading.length > 0);
  for (const [step, view] of loading.entries()) assert.deepEqual(view, loaded, `loading step ${step + 1} matches the loaded view`);
});
