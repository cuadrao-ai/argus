import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { SKELETON_DELAY_MS } from "@/components/business-app/business-skeletons";
import { fixtureId } from "./fixtures/business-report-http-fixture";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountAnnotatedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";
import spanish from "@/public/locales/es-419/common.json";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

const pause = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
const cardSlots = () => [...document.querySelectorAll<HTMLElement>('[data-testid="records-overview-preview"] [data-overview-card]')];

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

const guideTitle = spanish.business.guide_cards.registros_intro.title;
const guideSlot = (element: Element) => element.matches("[data-guide-slot]") ? "guide-slot" : element.matches("section[aria-labelledby]") && element.querySelector("h3")?.textContent === guideTitle ? "guide" : null;
/** The page's slots in order, or null while the page is not painted. */
const paintedSlots = () => {
  const cards = document.querySelector('[data-testid="records-overview-preview"]');
  if (!cards?.parentElement || !seen(cards)) return null;
  return [...cards.parentElement.children].map((element) => guideSlot(element) ?? slotName(element));
};

for (const width of [1440, 390]) test(`Registros at ${width}px holds the guide's place from the first painted frame, and the guide takes it with nothing else moving`, async () => {
  const frames: string[][] = [];
  const record = () => { const slots = paintedSlots(); if (slots && JSON.stringify(frames.at(-1)) !== JSON.stringify(slots)) frames.push(slots); };
  let release!: () => void;
  const queryGate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ width, topLevel: true, grantId: fixtureId(3100), workspaceGrant: fixtureId(3101), queryGate, waitForAnswer: false, onCommit: record });
  try {
    await pause(SKELETON_DELAY_MS + 20);
    record();
    const slot = document.querySelector<HTMLElement>("[data-guide-slot]");
    assert.ok(slot && seen(slot), "the guide's place is painted with the first frame");
    assert.equal(slot.getAttribute("aria-hidden"), "true");
    assert.ok([...slot.children].every((child) => (child as HTMLElement).style.visibility === "hidden"), "the place shows no text");
    page.context.records.workspaceGrant = fixtureId(3100);
    await page.rerender();
  } finally { await act(async () => release()); }
  await page.settle(() => document.querySelector('[data-report-schema="2"] [data-testid="records-count"]') !== null);
  await pause(50);
  record();
  assert.ok(frames.length >= 2, JSON.stringify(frames));
  const [first] = frames;
  assert.ok(first.indexOf("guide-slot") >= 0 && first.indexOf("guide-slot") < first.indexOf("tabs"), `the place sits above the tabs: ${first}`);
  const asLoaded = (slots: string[]) => slots.map((name) => name === "guide-slot" ? "guide" : name);
  for (const frame of frames) assert.deepEqual(asLoaded(frame), asLoaded(first), "only the guide's place changes, into the guide");
  assert.deepEqual(frames.map((frame) => frame.includes("guide-slot") ? "place" : "guide"), ["place", "guide"], "the place turns into the guide once");
  assert.equal(document.querySelector("[data-guide-slot]"), null);
  assert.deepEqual(page.guideRequests, [], "no guide read");
});

for (const account of [{ name: "dismissed", dismissedGuides: ["registros-intro"] }, { name: "unknown", dismissedGuides: null }, { name: "never answered", member: null }] as const) test(`a ${account.name} guide has no place and no guide at any commit`, async () => {
  const commits: boolean[] = [];
  const guideAnywhere = () => document.querySelector("[data-guide-slot]") !== null || (document.body.textContent ?? "").includes(guideTitle);
  let release!: () => void;
  const queryGate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ topLevel: true, grantId: fixtureId(3100), workspaceGrant: fixtureId(3101), queryGate, waitForAnswer: false, onCommit: () => commits.push(guideAnywhere()), ...account });
  try {
    await pause(SKELETON_DELAY_MS + 20);
    page.context.records.workspaceGrant = fixtureId(3100);
    await page.rerender();
  } finally { await act(async () => release()); }
  if ("member" in account) {
    await pause(50);
    assert.ok(document.body.textContent?.includes(spanish.business.transactions.reporting.access_unavailable), "without an account Registros says access is unavailable");
  } else await page.settle(() => document.querySelector('[data-report-schema="2"] [data-testid="records-count"]') !== null);
  assert.ok(commits.length > 0);
  assert.deepEqual(commits.filter(Boolean), []);
  assert.equal(guideAnywhere(), false);
});

test("Registros asks no /me of its own: the person comes with the shell", async () => {
  const page = await mount({ topLevel: true, grantId: fixtureId(3100), waitForAnswer: false });
  await page.settle(() => document.querySelector('[data-report-schema="2"] [data-testid="records-count"]') !== null);
  assert.deepEqual(page.meRequests, []);
  assert.ok(page.fixture.calls.some((call) => call.path.endsWith("/reports/query")));
});

/** What the six cards show in one commit: nothing yet, their placeholder bars, an empty wait, or the numbers. */
const cardFrame = () => {
  const cards = cardSlots();
  if (cards.length !== 6 || !cards.every(seen)) return "unseen";
  if (cards.every((card) => seen(card.querySelector(".shimmer")))) return "bars";
  if (cards.every((card) => card.querySelector(".shimmer") === null)) return "numbers";
  return "empty";
};

test("the cards keep their placeholder bars at every commit from the first visible frame until the numbers, across the swap to the real page", async () => {
  const frames: string[] = [];
  const record = () => { const frame = cardFrame(); if (frames.at(-1) !== frame) frames.push(frame); };
  let release!: () => void;
  const queryGate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ topLevel: true, grantId: fixtureId(3100), workspaceGrant: fixtureId(3101), queryGate, waitForAnswer: false, onCommit: record });
  try {
    await pause(SKELETON_DELAY_MS + 20);
    record();
    page.context.records.workspaceGrant = fixtureId(3100);
    await page.rerender();
    await pause(50);
  } finally { await act(async () => release()); }
  await page.settle(() => document.querySelector('[data-report-schema="2"] [data-testid="records-count"]') !== null);
  await pause(SKELETON_DELAY_MS + 50);
  record();
  assert.deepEqual(frames, ["unseen", "bars", "numbers"]);
});
