import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { fixtureId } from "./fixtures/business-report-http-fixture";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountAnnotatedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

for (const width of [1440, 390]) test(`Notas and Adjunto open the matching dossier card at ${width}px`, async () => {
  const page = await mount({ width });
  const draftId = fixtureId(1);
  for (const [column, detailsCard] of [["note", "note"], ["attachment", "support"]] as const) {
    await page.click(document.querySelector(`[data-record-${column}="draft:${draftId}"]`));
    assert.deepEqual(page.opened.at(-1), { kind: "draft", draftId, list: "transactions", detailsCard });
    assert.equal(document.querySelector('[role="dialog"]'), null);
  }
  assert.equal(page.opened.length, 2);
  assert.equal(page.fixture.calls.some((call) => /current-note|supporting-files|\/source$/.test(call.path)), false);
});

test("a reader can open a recorded note and existing attachments without edit permissions", async () => {
  const page = await mount({ readOnly: true, edit: (rows) => { rows[0].note = "Solo lectura"; } });
  const draftId = fixtureId(1);
  const note = document.querySelector(`button[data-record-note="draft:${draftId}"]`);
  assert.equal(note?.textContent, "Solo lectura");
  await page.click(note);
  await page.click(document.querySelector(`button[data-record-attachment="draft:${draftId}"]`));
  assert.deepEqual(page.opened, ["note", "support"].map((detailsCard) => ({ kind: "draft", draftId, list: "transactions", detailsCard })));
});

test("a report revision refreshes the visible note after a dossier save", async () => {
  const updatedNote = "Nota actualizada";
  const page = await mount();
  page.fixture.records[0].note = updatedNote;
  await page.reloaded();
  await page.settle(() => document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`)?.textContent === updatedNote);
});

test("Registros still searches an accent-folded current note and the linked filename", async () => {
  const page = await mount({ edit: (rows) => { rows[0].note = "Carpeta de José"; } });
  const search = document.querySelector<HTMLInputElement>('input[type="search"]');
  assert.ok(search);
  for (const query of ["carpeta de jose", "original sintetico.pdf"]) {
    await page.type(search, query);
    await page.settle(() => document.querySelector('[data-testid="records-count"]')?.textContent?.includes("1 de 1") ?? false);
    assert.equal(document.querySelector("tbody tr")?.getAttribute("data-record-key"), `draft:${fixtureId(1)}`);
  }
});

test("a reader sees no note or attachment action for a row without those facts", async () => {
  const page = await mount({ readOnly: true, edit: (rows) => { rows[2].note = null; } });
  const row = document.querySelector(`[data-record-key="draft:${fixtureId(3)}"]`);
  assert.ok(row);
  assert.equal(row.querySelector("[data-record-note], [data-record-attachment]"), null);
  assert.equal(page.opened.length, 0);
});
