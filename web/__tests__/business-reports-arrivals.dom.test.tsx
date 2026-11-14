import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { fixtureId } from "./fixtures/business-report-http-fixture";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountAnnotatedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";
import { installRowSight } from "./support/row-sight";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
let sight: ReturnType<typeof installRowSight>;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; sight = installRowSight(); });
afterEach(async () => { sight.show(); await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { sight.restore(); await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

const arrivedKeys = () => [...document.querySelectorAll('[data-record-key][data-arrived="true"]')].map((row) => row.getAttribute("data-record-key"));
const drawnRows = () => document.querySelectorAll("tbody tr[data-record-key]").length;

test("Registros reads itself again when the change check brings something new: the new row is marked, the table stays drawn and focus stays", async () => {
  let arrived = false;
  const newcomer = fixtureId(9100);
  const page = await mount({ queryAnswer: async (_request, answer) => {
    if (!arrived) return answer;
    await new Promise((resolve) => setTimeout(resolve, 30));
    return { ...answer, items: [{ ...answer.items[0], row_id: newcomer }, ...answer.items.slice(0, -1)] };
  } });
  for (const width of [1440, 390]) assert.equal(document.querySelector('[data-testid="records-refresh"]'), null, `no refresh control at ${width}`);
  const before = drawnRows();
  const queries = () => page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  const asked = queries();
  const held = document.querySelector<HTMLElement>("tbody tr[data-record-key]:nth-child(3)")!;
  held.focus();
  arrived = true;
  await page.listChanged();
  assert.equal(drawnRows(), before, "the rows stay on screen while the new answer is on its way");
  await page.settle(() => arrivedKeys().length > 0);
  assert.deepEqual(arrivedKeys(), [newcomer]);
  assert.equal(document.querySelector("tbody tr[data-record-key]")?.getAttribute("data-record-key"), newcomer);
  assert.equal(queries() - asked, 1);
  assert.equal(document.activeElement, held, "the row that had focus keeps it");
  await page.rerender();
  assert.equal(queries() - asked, 1, "nothing asks again until the next change");
});

test("a new record lands where the sort puts it, not first, marked once it is in sight, and the rows in view stay where they were", async () => {
  const ROW = 40;
  const SLOT = 2;
  let arrived = false;
  const newcomer = fixtureId(9101);
  const page = await mount({ queryAnswer: async (_request, answer) => arrived ? { ...answer, items: [...answer.items.slice(0, SLOT), { ...answer.items[SLOT], row_id: newcomer }, ...answer.items.slice(SLOT, -1)] } : answer });
  const keys = () => [...document.querySelectorAll("tbody tr[data-record-key]")].map((row) => row.getAttribute("data-record-key"));
  const before = keys();
  let scrolled = 3.5 * ROW;
  const moves: number[] = [];
  const rect = HTMLElement.prototype.getBoundingClientRect;
  const scrollBy = window.scrollBy;
  HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
    const index = [...document.querySelectorAll("tbody tr[data-record-key]")].indexOf(this);
    const top = index < 0 ? 0 : index * ROW - scrolled;
    return { top, bottom: top + ROW, left: 0, right: 0, width: 0, height: ROW, x: 0, y: top, toJSON: () => ({}) };
  };
  window.scrollBy = ((_x: number, y: number) => { moves.push(y); scrolled += y; }) as typeof window.scrollBy;
  try {
    sight.hide((row) => row.getAttribute("data-record-key") === newcomer);
    arrived = true;
    await page.listChanged();
    await page.settle(() => keys().includes(newcomer));
    assert.deepEqual(keys(), [...before.slice(0, SLOT), newcomer, ...before.slice(SLOT, -1)], "the record sits at its sort position and no other row changed order");
    assert.deepEqual(moves, [ROW], "the page scrolls by the height that landed above the rows in view");
    assert.deepEqual(arrivedKeys(), [], "the record is above what the person sees, so its mark waits");
    await act(async () => sight.show());
    assert.deepEqual(arrivedKeys(), [newcomer]);
  } finally { HTMLElement.prototype.getBoundingClientRect = rect; window.scrollBy = scrollBy; }
});

test("a change check that finds the same records leaves the table as it is", async () => {
  const page = await mount();
  await page.listChanged();
  await new Promise((resolve) => setTimeout(resolve, 60));
  await page.rerender();
  assert.deepEqual(arrivedKeys(), []);
  assert.ok(drawnRows() > 0);
});

test("a failed re-read keeps the rows shown and stays quiet", async () => {
  const page = await mount();
  const before = drawnRows();
  const live = globalThis.fetch;
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => String(input).endsWith("/reports/query") ? Promise.resolve(Response.json({ code: "internal_error" }, { status: 500 })) : live(input, init)) as typeof fetch;
  try {
    await page.listChanged();
    await new Promise((resolve) => setTimeout(resolve, 60));
    await page.rerender();
  } finally { globalThis.fetch = live; }
  assert.equal(drawnRows(), before);
  assert.equal(document.querySelector('[role="alert"]'), null);
});

test("a failed read of Registros still offers Reintentar", async () => {
  const page = await mount();
  const live = globalThis.fetch;
  let down = true;
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => down && String(input).endsWith("/reports/query") ? Promise.resolve(Response.json({ code: "internal_error" }, { status: 500 })) : live(input, init)) as typeof fetch;
  try {
    await page.reloaded();
    await page.settle(() => page.button("Reintentar") !== undefined);
    assert.equal(drawnRows(), 0);
    down = false;
    await page.click(page.button("Reintentar"));
    await page.settle(() => drawnRows() > 0);
  } finally { globalThis.fetch = live; }
});

const pause = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
/** The report read fails until the test heals it; every other request goes through. */
function brokenReportRead() {
  const live = globalThis.fetch;
  const read = { down: true };
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => read.down && String(input).endsWith("/reports/query") ? Promise.resolve(Response.json({ code: "internal_error" }, { status: 500 })) : live(input, init)) as typeof fetch;
  return { heal: () => { read.down = false; }, restore: () => { globalThis.fetch = live; } };
}

test("a re-read that failed is asked again on the next check, also one that finds nothing new, until the new row lands", async () => {
  let arrived = false;
  const newcomer = fixtureId(9102);
  const page = await mount({ queryAnswer: (_request, answer) => arrived ? { ...answer, items: [{ ...answer.items[0], row_id: newcomer }, ...answer.items.slice(0, -1)] } : answer });
  const queries = () => page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  const read = brokenReportRead();
  try {
    arrived = true;
    await page.listChanged();
    await pause(60);
    assert.deepEqual(arrivedKeys(), [], "the read failed, so the change is still owed");
    await page.listChecked();
    await pause(60);
    assert.deepEqual(arrivedKeys(), [], "still failing, still owed");
    read.heal();
    await page.listChecked();
    await page.settle(() => arrivedKeys().length > 0);
    assert.deepEqual(arrivedKeys(), [newcomer]);
    const asked = queries();
    await page.listChecked();
    await pause(60);
    assert.equal(queries(), asked, "once the read landed, a check with nothing new asks nothing");
  } finally { read.restore(); }
});

test("a record that lands outside the page shown still makes Registros read again: the count is the server's and no row here is marked", async () => {
  let arrived = false;
  const page = await mount({ queryAnswer: (_request, answer) => arrived ? { ...answer, matching_count: answer.matching_count + 1 } : answer });
  const count = () => document.querySelector('[data-testid="records-count"]')?.textContent ?? "";
  const before = count();
  const keys = [...document.querySelectorAll("tbody tr[data-record-key]")].map((row) => row.getAttribute("data-record-key"));
  arrived = true;
  await page.listChanged();
  await page.settle(() => count() !== before);
  assert.deepEqual([...document.querySelectorAll("tbody tr[data-record-key]")].map((row) => row.getAttribute("data-record-key")), keys, "the rows of this page are the same");
  assert.deepEqual(arrivedKeys(), []);
});
