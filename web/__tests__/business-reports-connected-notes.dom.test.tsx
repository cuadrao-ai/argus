import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { fixtureId } from "./fixtures/business-report-http-fixture";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountAnnotatedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";

// Registros notes and the Adjunto panel on the connected report: the note editor, its limit and its refusals.
await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

test("current notes preserve 500 code points and replay uncertain writes with one effect", async () => {
  const page = await mount(); page.fixture.controls.noteUncertain = true;
  await page.click(document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`));
  const field = document.querySelector("textarea")!;
  const valid = "🟢".repeat(500);
  await page.type(field, valid + "x");
  assert.equal(field.value, valid + "x"); assert.equal((page.button("Guardar") as HTMLButtonElement).disabled, true);
  await page.type(field, valid); assert.match(document.querySelector('[role="dialog"]')!.textContent!, /500\/500/);
  await page.click(page.button("Guardar"));
  await page.settle(() => document.querySelector('[role="alert"]')?.textContent?.includes("confirmar") ?? false);
  await page.click(page.button("Reintentar"));
  await page.settle(() => !document.querySelector("textarea"));
  const writes = page.fixture.calls.filter((call) => call.path.endsWith("/current-note"));
  assert.equal(writes.length, 2); assert.equal(writes[0].headers.get("Idempotency-Key"), writes[1].headers.get("Idempotency-Key"));
  assert.deepEqual(writes[0].body, writes[1].body); assert.equal(page.fixture.records[0].revision, 4); assert.equal(page.fixture.records[0].note, valid);
});

test("a concurrent note edit keeps the losing text and uses the reviewed version only after explicit reload", async () => {
  const page = await mount();
  await page.click(document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`));
  await page.type(document.querySelector("textarea")!, "Mi borrador");
  page.fixture.records[0].revision = 5; page.fixture.records[0].note = "Nota de otra persona";
  await page.click(page.button("Guardar"));
  await page.settle(() => document.querySelector('[role="alert"]')?.textContent?.includes("registro cambió") ?? false);
  assert.equal(document.querySelector("textarea")!.value, "Mi borrador");
  await page.click(page.button("Recargar"));
  await page.settle(() => document.querySelector('[role="dialog"]')?.textContent?.includes("Nota de otra persona") ?? false);
  assert.equal(document.querySelector("textarea")!.value, "Mi borrador");
  await page.click(page.button("Guardar")); await page.settle(() => !document.querySelector("textarea"));
  const writes = page.fixture.calls.filter((call) => call.path.endsWith("/current-note"));
  assert.equal((writes[0].body as { expected_version: number }).expected_version, 3);
  assert.equal((writes[1].body as { expected_version: number }).expected_version, 5);
  assert.notEqual(writes[0].headers.get("Idempotency-Key"), writes[1].headers.get("Idempotency-Key"));
});

test("closing the mounted scope aborts a late annotation result without refreshing another screen", async () => {
  const page = await mount();
  const request = globalThis.fetch;
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = (async (input, init) => {
    const response = await request(input, init);
    if (String(input).endsWith('/current-note')) await held;
    return response;
  }) as typeof fetch;
  await page.click(document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`));
  await page.type(document.querySelector('textarea')!, 'Respuesta que llegó tarde');
  await page.click(page.button('Guardar'));
  await page.settle(() => page.fixture.calls.some((call) => call.path.endsWith('/current-note')));
  const queries = page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length;
  await cleanup();
  await act(async () => { release(); await Promise.resolve(); await Promise.resolve(); });
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length, queries);
  assert.equal(document.querySelector('textarea'), null);
});

test("an action refusal re-reads current authority and keeps a still-authorized viewer able to read", async () => {
  const page = await mount();
  await page.click(document.querySelector(`[data-record-note="draft:${fixtureId(1)}"]`));
  page.fixture.controls.readOnly = true;
  const queries = page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length;
  await page.click(page.button('Guardar'));
  await page.settle(() => document.querySelector('[role="dialog"]') === null && document.querySelector('[data-testid="records-count"]') !== null && page.fixture.calls.filter((call) => call.path.endsWith('/reports/query')).length > queries);
  assert.equal(document.querySelector('[data-record-note]'), null);
  await page.click(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  assert.equal(document.querySelector('input[type="file"]'), null);
  assert.equal((page.button('Original sintético.pdf') as HTMLButtonElement).disabled, true);
});

test("the Adjunto panel shows what works and announces no feature that is off", async () => {
  const page = await mount();
  await page.click(document.querySelector(`[data-record-attachment="draft:${fixtureId(1)}"]`));
  const panel = document.querySelector('[role="dialog"]')!;
  assert.match(panel.textContent ?? "", /Adjuntos vinculados/);
  assert.ok(panel.querySelector('input[type="file"]'), "the upload area stays");
  assert.doesNotMatch(panel.textContent ?? "", /no está disponible|Vincular documentos recibidos/);
});
