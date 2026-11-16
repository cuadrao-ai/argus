import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { SKELETON_DELAY_MS } from "@/components/business-app/business-skeletons";
import spanish from "@/public/locales/es-419/common.json";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountAnnotatedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

const pause = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
const tableSkeletonShown = () => { const table = document.querySelector('[data-testid="transacciones-loading"]'); return table !== null && table.querySelector(".waiting") === null && table.querySelector(".shimmer") !== null; };

test("the skeleton holds the guide's place, and the page draws the guide in it", async () => {
  let release!: () => void;
  const queryGate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ queryGate, waitForAnswer: false });
  const guide = () => document.querySelector('[data-testid="transacciones"] > section[aria-labelledby]');
  const place = () => document.querySelector('[data-testid="transacciones"] > [data-guide-slot]');
  try {
    await pause(SKELETON_DELAY_MS + 20);
    assert.ok(tableSkeletonShown());
    assert.ok(place() && guide() === null, "the skeleton holds the guide's place");
  } finally { await act(async () => release()); }
  await page.settle(() => document.querySelector('[data-testid="records-count"]') !== null);
  assert.ok(guide() && place() === null, "the guide draws in its place with the page");
  assert.deepEqual(page.guideRequests, []);
});

test("Registros shows its own guide on both tabs, hides it at once on dismiss and saves it once", async () => {
  let confirm = () => {};
  const page = await mount({ dismissedGuides: ["bandeja-intro"], guideDismissGate: new Promise<void>((resolve) => { confirm = resolve; }) });
  const guide = () => document.querySelector<HTMLElement>('[data-testid="transacciones"] > section[aria-labelledby]');
  await page.settle(() => guide() !== null);
  const copy = spanish.business.guide_cards.registros_intro;
  assert.equal(guide()!.querySelector("h3")?.textContent, copy.title);
  assert.deepEqual([...guide()!.querySelectorAll("li strong")].map((item) => item.textContent), [copy.browse.label, copy.find.label, copy.pending.label]);
  assert.ok(guide()!.compareDocumentPosition(document.querySelector('[data-testid="records-overview-preview"]')!) & Node.DOCUMENT_POSITION_FOLLOWING);
  await page.click(page.button("Ventas"));
  await page.settle(() => page.button("Ventas")?.getAttribute("aria-selected") === "true");
  assert.ok(guide());
  await page.click(page.button("Ocultar guía"));
  assert.equal(guide(), null, "the guide leaves at once");
  await act(async () => confirm());
  await pause(50);
  assert.equal(guide(), null);
  assert.deepEqual(page.guideRequests, ["POST /business/guide-cards/registros-intro/dismiss"]);
  assert.deepEqual([...page.dismissedGuides].sort(), ["bandeja-intro", "registros-intro"]);
});

test("a dismissal the server refused brings the guide back with its retry", async () => {
  let refuse = true;
  const page = await mount({ guideDismissFailure: () => refuse });
  const guide = () => document.querySelector<HTMLElement>('[data-testid="transacciones"] > section[aria-labelledby]');
  await page.settle(() => guide() !== null);
  await page.click(page.button("Ocultar guía"));
  await page.settle(() => guide()?.querySelector('[role="alert"]') != null);
  assert.ok(guide()!.querySelector('[title="guide-server-123"]'));
  refuse = false;
  await page.click(page.button("Reintentar"));
  assert.equal(guide(), null);
  await pause(50);
  assert.equal(guide(), null);
  assert.deepEqual(page.guideRequests, ["POST /business/guide-cards/registros-intro/dismiss", "POST /business/guide-cards/registros-intro/dismiss"]);
});
