import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { reportRequestSchema } from "@/lib/business-reports-api";
import { restoreReportLocation } from "@/lib/business-reporting-wire";
import { recordedReportAnswer } from "./fixtures/recorded-report-answer";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountConnectedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

const renderedColumnKeys = () => [...document.querySelectorAll("thead th")].map((node) => node.getAttribute("data-col"));
test("an old saved URL shows the server's upgrade: the net amount before the total, NCF and ITBIS hidden, and later edits kept", async () => {
  const order = recordedReportAnswer.presentation.order.filter((key) => key !== "fiscal_number" && key !== "net_amount" && key !== "itbis_amount");
  const presentation = { order: [order[0], ...order.slice(1).reverse()], hidden: ["date"], density: 40 as const };
  const request = reportRequestSchema.parse({ schema_version: 2, presentation });
  window.history.replaceState(null, "", `/biz?report=${encodeURIComponent(JSON.stringify(request))}`);
  const page = await mount();
  const expectedColumns = ["counterparty", "funding", "payment_form", "expense_type", "attachment", "note", "stage", "net_amount", "gross_amount"];
  assert.deepEqual(renderedColumnKeys(), expectedColumns);
  assert.equal(document.querySelector("table")?.getAttribute("data-density"), "compacto");
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  for (const key of ["fiscal_number", "itbis_amount"]) {
    const checkbox = document.querySelector<HTMLInputElement>(`[data-column-setting="${key}"] input[type="checkbox"]`);
    assert.equal(checkbox?.checked, false, `${key} must be available and hidden`);
  }
  await page.click(document.querySelector('[data-column-setting="fiscal_number"] input'));
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  assert.deepEqual(renderedColumnKeys(), [...expectedColumns, "fiscal_number"]);
  await page.click(document.querySelector('[data-testid="records-refresh"]'));
  await page.settle(() => document.querySelector('[data-testid="records-count"]') !== null);
  assert.deepEqual(renderedColumnKeys(), [...expectedColumns, "fiscal_number"]);
  const restored = restoreReportLocation(new URLSearchParams(window.location.search)).request;
  const upgraded = presentation.order.flatMap((key) => key === "gross_amount" ? ["net_amount", key] : [key]);
  assert.deepEqual(restored.schema_version === 2 && restored.presentation, { ...presentation, order: [...upgraded, "fiscal_number", "itbis_amount"], hidden: ["date", "itbis_amount"] });
});

for (const language of ["es-419", "en"] as const) test(`server defaults show eight columns and all optional columns remain available in ${language}`, async () => {
  const page = await mount({ language });
  assert.deepEqual(renderedColumnKeys(), ["counterparty", "date", "net_amount", "itbis_amount", "gross_amount", "stage", "note", "attachment"]);
  assert.ok(page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).every((call) => !Object.hasOwn(call.body as object, "presentation")), "fresh V1 and V2 requests leave defaults to the server");
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  for (const [key, label] of language === "en" ? [["expense_type", "Expense type"], ["payment_form", "Payment method"], ["funding", "Account"], ["fiscal_number", "NCF"], ["itbis_amount", "ITBIS"]] : [["expense_type", "Tipo de gasto"], ["payment_form", "Forma de pago"], ["funding", "Cuenta"], ["fiscal_number", "NCF"], ["itbis_amount", "ITBIS"]]) {
    const row = document.querySelector(`[data-column-setting="${key}"]`);
    assert.ok(row?.textContent?.includes(label));
    assert.equal(row?.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked, key === "itbis_amount");
  }
});

test("server layout changes render, saved views retain the effective layout, and Restore asks for fresh defaults", async () => {
  const chosen: typeof recordedReportAnswer.presentation = { ...recordedReportAnswer.presentation, order: ["counterparty", ...recordedReportAnswer.presentation.order.slice(1).reverse()], hidden: [], density: 40 as const };
  const page = await mount({ presentation: chosen });
  assert.deepEqual(renderedColumnKeys(), ["counterparty", "funding", "payment_form", "expense_type", "attachment", "note", "stage", "gross_amount", "itbis_amount", "net_amount", "date", "fiscal_number"]);
  assert.equal(document.querySelector("table")?.getAttribute("data-density"), "compacto");
  await page.click(page.button("Vistas")); await page.click(page.button("Guardar vista actual"));
  await page.type(document.querySelector('input[maxlength="120"]')!, "Mi diseño"); await page.click(page.button("Guardar"));
  await page.settle(() => page.fixture.views.length === 1 && !document.querySelector('input[maxlength="120"]'));
  assert.deepEqual((page.fixture.views[0].recipe as { presentation: unknown }).presentation, chosen);
  const fresh = { ...recordedReportAnswer.presentation, hidden: ["attachment" as const, "funding" as const], density: 56 as const };
  page.fixture.controls.presentation = fresh;
  await page.click(document.querySelector('[data-testid="records-refresh"]'));
  await page.settle(() => !renderedColumnKeys().includes("attachment"));
  await page.click(page.button("Vistas: Mi diseño")); await page.click([...document.querySelectorAll('[role="dialog"] button')].find((node) => node.textContent === "Mi diseño"));
  await page.settle(() => renderedColumnKeys()[1] === "funding");
  assert.deepEqual((page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).at(-1)!.body as { presentation: unknown }).presentation, chosen);
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  await page.click(page.button("Restaurar valores iniciales"));
  await page.settle(() => !renderedColumnKeys().includes("attachment") && document.querySelector("table")?.getAttribute("data-density") === "amplio");
  const restored = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).at(-1)!.body as object;
  assert.equal(Object.hasOwn(restored, "presentation"), false);
  assert.ok(renderedColumnKeys().includes("expense_type") && renderedColumnKeys().includes("payment_form"), "Restore uses the new server layout, not the preview fixture");
});

for (const outcome of ["ready", "failed"] as const) test(`Restore cannot save a stale custom layout while pending or ${outcome}`, async () => {
  const page = await mount({ initial: reportRequestSchema.parse({ schema_version: 2, presentation: { ...recordedReportAnswer.presentation, hidden: [], density: 40 } }) });
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = (async (input, init) => {
    if (String(input).endsWith("/reports/query")) {
      await gate;
      if (outcome === "failed") return new Response("{}", { status: 503 });
    }
    return page.fixture.request(input, init);
  }) as typeof fetch;
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  await page.click(page.button("Restaurar valores iniciales"));
  await page.click(page.button("Vistas"));
  try {
    assert.equal(page.button("Guardar vista actual")?.disabled, true, "saving must await the server's restored layout");
  } finally { await act(async () => release()); }
  if (outcome === "failed") {
    await page.settle(() => document.querySelector('[role="alert"]') !== null);
    assert.equal(page.button("Guardar vista actual")?.disabled, true, "failed Restore has no new layout to save");
  } else {
    await page.settle(() => page.button("Guardar vista actual")?.disabled === false);
  }
  assert.equal(page.fixture.views.length, 0);
});


test("a fresh connected table waits for server columns and offers no layout before the answer", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const page = await mount({ queryGate: gate, waitForAnswer: false });
  try {
    assert.equal(document.querySelector("th[data-col]"), null);
    assert.equal(document.querySelector('[data-testid="transacciones-view-options"]'), null);
    assert.equal(document.querySelector("[data-column-setting]"), null);
    await page.settle(() => document.querySelector('[data-testid="fullscreen-loading"]') !== null);
  } finally { await act(async () => release()); }
  await page.settle(() => document.querySelector('th[data-col="gross_amount"]') !== null);
});

for (const family of ["purchase", "sale"] as const) {
  for (const currency of ["DOP", "USD", "EUR"] as const) {
    test(`optional fiscal columns show exact row values for ${family} in ${currency}`, async () => {
      const page = await mount({ defaultCurrency: currency, initial: reportRequestSchema.parse({ schema_version: 2, filters: { record_families: [family], currencies: [currency] } }), edit: (rows) => {
        rows.forEach((row, index) => { row.family = family; if (family === "sale") row.dgii_606 = null; row.currency = currency; row.fiscal_number = index < 2 ? "B0100000001" : index === 2 ? "E310000000001" : null; row.itbis_amount = index === 0 ? "18.25" : index === 1 ? "0.00" : index === 3 ? "9007199254740993.01" : null; });
      } });
      assert.equal(document.querySelector('th[data-col="fiscal_number"]'), null);
      assert.ok(document.querySelector('th[data-col="itbis_amount"]'));
      await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
      for (const label of ["NCF"]) await page.click([...document.querySelectorAll('label')].find((item) => item.textContent?.trim() === label)?.querySelector('input'));
      await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
      const rows = [...document.querySelectorAll("tbody tr")];
      assert.equal(rows.length, 25);
      const visibleDuplicate = rows.filter((row) => row.querySelector('[data-col="fiscal_number"]')?.textContent === "B0100000001");
      assert.equal(visibleDuplicate.length, 2);
      assert.equal(new Set(visibleDuplicate.map((row) => row.getAttribute("data-record-key"))).size, 2);
      for (const row of rows) {
        const source = page.fixture.records.find((record) => record.row_id === row.getAttribute("data-record-key"))!;
        assert.ok(source);
        assert.equal(row.querySelector('[data-col="fiscal_number"]')?.textContent, source.fiscal_number ?? "-sin dato");
        const itbis = row.querySelector('[data-col="itbis_amount"]')!;
        if (source.itbis_amount === null) assert.equal(itbis.textContent, "-sin dato");
        else {
          const value = source.itbis_amount === "0.00" ? "0.00" : source.itbis_amount === "18.25" ? "18.25" : "9,007,199,254,740,993.01";
          assert.equal(itbis.textContent, value);
        }
        assert.ok(itbis.classList.contains("font-normal"));
        assert.ok(row.querySelector('[data-col="gross_amount"]')?.classList.contains("font-medium"));
      }
    });
  }
}


test("selected ITBIS stays unknown when row currency is missing", async () => {
  await mount({ presentation: { ...recordedReportAnswer.presentation, hidden: recordedReportAnswer.presentation.hidden.filter((key) => key !== "itbis_amount") }, queryAnswer: (_request, answer) => ({ ...answer, items: answer.items.map((row) => ({ ...row, currency: null, itbis_amount: "18.25" })) }) });
  const amounts = [...document.querySelectorAll('tbody [data-col="itbis_amount"]')];
  assert.equal(amounts.length, 25);
  assert.ok(amounts.every((cell) => cell.textContent === "-sin dato"));
});

test("column up and down buttons move the saved order and keep counterparty fixed", async () => {
  const page = await mount();
  await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
  const row = () => document.querySelector('[data-column-setting="date"]')!;
  await page.click(row().querySelector('[aria-label="Subir Fecha"]'));
  const restored = restoreReportLocation(new URLSearchParams(window.location.search)).request;
  assert.equal(restored.schema_version === 2 && restored.presentation?.order[1], "date");
  assert.equal(row().querySelector<HTMLButtonElement>('[aria-label="Subir Fecha"]')?.disabled, true);
  await page.click(row().querySelector('[aria-label="Bajar Fecha"]'));
  await page.click(row().querySelector('[aria-label="Bajar Fecha"]'));
  assert.equal(document.querySelector('[data-column-setting="counterparty"] button'), null);
  assert.deepEqual(renderedColumnKeys().slice(0, 3), ["counterparty", "net_amount", "date"]);
});
