import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { SKELETON_DELAY_MS } from "@/components/business-app/business-skeletons";
import { fixtureId } from "./fixtures/business-report-http-fixture";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountAnnotatedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

const pause = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
const cardSlots = () => [...document.querySelectorAll<HTMLElement>('[data-testid="records-overview-preview"] [data-overview-card]')];
const tableSkeletonShown = () => { const table = document.querySelector('[data-testid="transacciones-loading"]'); return table !== null && table.querySelector(".waiting") === null && table.querySelector(".shimmer") !== null; };

/** Whether an element paints: the nearest hidden or visible style above it decides. */
const seen = (node: Element | null | undefined) => {
  if (!node) return false;
  for (let element: Element | null = node; element; element = element.parentElement) {
    if (element.classList.contains("waiting")) return false;
    const visibility = (element as HTMLElement).style?.visibility;
    if (visibility) return visibility !== "hidden";
  }
  return true;
};
const skeletonFrame = () => {
  const cards = cardSlots();
  const table = document.querySelector('[data-testid="transacciones-loading"]');
  return { cards: cards.length === 6 && cards.every(seen), placeholders: cards.length === 6 && cards.every((card) => seen(card.querySelector(".shimmer"))), table: seen(table?.querySelector(".shimmer")) };
};
const workspaceStates = [{ name: "before the workspace answers", workspaceGrant: fixtureId(3101) }, { name: "with the workspace known", workspaceGrant: fixtureId(3100) }];

for (const width of [1440, 390]) for (const state of workspaceStates) test(`Registros at ${width}px ${state.name} paints the cards, their placeholders and the table in the same frame`, async () => {
  let release!: () => void;
  const queryGate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ width, topLevel: true, grantId: fixtureId(3100), workspaceGrant: state.workspaceGrant, queryGate, waitForAnswer: false });
  try {
    const first = skeletonFrame();
    assert.ok(first.cards === first.placeholders && first.placeholders === first.table, `before the shared delay the skeleton paints all of it or none of it: ${JSON.stringify(first)}`);
    await pause(SKELETON_DELAY_MS + 20);
    assert.deepEqual(skeletonFrame(), { cards: true, placeholders: true, table: true });
    page.context.records.workspaceGrant = fixtureId(3100);
    await page.rerender();
    assert.deepEqual(skeletonFrame(), { cards: true, placeholders: true, table: true }, "the same wait keeps all of it");
  } finally { await act(async () => release()); }
});

const slotName = (element: Element) => element.querySelector('[role="tablist"]') ? "tabs" : element.matches('[data-testid="records-overview-preview"]') ? "cards" : element.querySelector('[data-testid="records-toolbar"]') ? "toolbar" : element.matches('[data-testid="transacciones-loading"], [data-testid="records-page-preview"]') ? "table" : element.tagName.toLowerCase();
const pageSlots = () => {
  const cards = document.querySelector('[data-testid="records-overview-preview"]');
  return cards?.parentElement ? [...cards.parentElement.children].map(slotName) : [];
};

for (const width of [1440, 390]) test(`Registros loading at ${width}px holds the tabs and the toolbar where the loaded page has them`, async () => {
  let release!: () => void;
  const queryGate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ width, topLevel: true, grantId: fixtureId(3100), workspaceGrant: fixtureId(3101), queryGate, waitForAnswer: false, dismissedGuides: ["registros-intro"] });
  let pending: string[] = [];
  try {
    await pause(SKELETON_DELAY_MS + 20);
    pending = pageSlots();
    assert.equal(document.querySelector("#records-type-gasto")?.getAttribute("aria-selected"), "true", "the tab Registros opens on is chosen");
    assert.equal(document.querySelector('[data-testid="records-toolbar"]')?.textContent, "", "the toolbar names no period or currency before the server answers");
    page.context.records.workspaceGrant = fixtureId(3100);
    await page.rerender();
    assert.deepEqual(pageSlots(), pending, "the workspace answer moves nothing");
  } finally { await act(async () => release()); }
  await page.settle(() => document.querySelector('[data-testid="records-count"]') !== null);
  assert.deepEqual(pending, pageSlots(), "the loaded page has the same slots in the same order");
  assert.ok(pending.indexOf("tabs") < pending.indexOf("cards") && pending.indexOf("cards") < pending.indexOf("toolbar") && pending.indexOf("toolbar") < pending.indexOf("table"));
});

for (const dismissed of [false, true]) test(`a late guide read holds the skeleton, then the page draws once ${dismissed ? "without" : "with"} the guide`, async () => {
  let answerGuide!: () => void;
  const guideReadGate = new Promise<void>((resolve) => { answerGuide = resolve; });
  const page = await mount({ topLevel: true, grantId: fixtureId(3100), guideReadGate, waitForAnswer: false, dismissedGuides: dismissed ? ["registros-intro"] : [] });
  const guide = () => document.querySelector('[data-testid="transacciones"] > section[aria-labelledby]');
  try {
    await pause(SKELETON_DELAY_MS + 100);
    assert.equal(document.querySelector('[data-testid="records-count"]'), null, "the records answer alone does not draw the page");
    assert.ok(tableSkeletonShown());
  } finally { await act(async () => answerGuide()); }
  await page.settle(() => document.querySelector('[data-testid="records-count"]') !== null);
  assert.equal(guide() !== null, !dismissed, "the guide draws with the page or never");
  await pause(50);
  assert.equal(guide() !== null, !dismissed);
});
