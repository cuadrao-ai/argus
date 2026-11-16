import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { SKELETON_DELAY_MS } from "@/components/business-app/business-skeletons";
import { fixtureId } from "./fixtures/business-report-http-fixture";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountAnnotatedReport, unmountConnectedReport } from "./support/business-reports-connected";

// DESIGN.md, Loading: a surface's loading view is that surface with its data pending.
// Every main block carries data-surface-block on the component both views share.

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await unmountConnectedReport(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
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

const registros = ["guide", "tabs", "overview", "toolbar", "table"] as const;
const surfaces: Surface[] = [
  { name: "Registros", width: 1440, blocks: registros, views: registrosViews },
  { name: "Registros", width: 390, blocks: ["heading", ...registros], views: registrosViews },
];

for (const surface of surfaces) test(`${surface.name} at ${surface.width}px loads as its own layout: the same blocks in the same order`, async () => {
  const { loading, loaded } = await surface.views(surface.width);
  assert.deepEqual(loaded, surface.blocks, "the loaded view has the surface's blocks");
  assert.ok(loading.length > 0);
  for (const [step, view] of loading.entries()) assert.deepEqual(view, loaded, `loading step ${step + 1} matches the loaded view`);
});
