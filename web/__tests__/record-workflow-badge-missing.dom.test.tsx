import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { ReportRecord } from "@/lib/business-reports-api";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";
import { createBusinessReportHttpFixture } from "./fixtures/business-report-http-fixture";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });

async function status(report: Partial<ReportRecord>, surface: "cell" | "table" | "phone" | "legacy-table" | "legacy-list" = "cell", lng = "es-419", actionable = true, edit: (row: RecordRow) => RecordRow = (row) => row) {
  await cleanup();
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng, resources: { [lng]: { translation: (await import(`@/public/locales/${lng}/common.json`)).default } }, interpolation: { escapeValue: false } });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const Component = (await import("@/components/business-app/transacciones/RecordStatusCell")).default;
  const { RecordsTable, RecordsNarrowList, RecordsList } = await import("@/components/business-app/transacciones/TransaccionesRecords");
  const { sampleRecordsPreferences } = await import("@/components/business-app/transacciones/sample-records-preferences");
  const { businessReportRow } = await import("@/lib/business-reporting-wire");
  const row = edit(businessReportRow({ ...createBusinessReportHttpFixture().records[0], ready: false, missing: [], ...report }));
  if (!actionable) row.opens = null;
  const value = { chosen: { space_id: "s", capabilities: ["read"] }, panel: { kind: "transactions" }, records: { workspace: null }, openPanel: () => {} } as unknown as BusinessContextValue;
  const preferences = sampleRecordsPreferences();
  const stored = { ...preferences, order: ["missing", ...preferences.order], hidden: [] };
  const node = surface === "cell" ? <Component row={row} />
    : surface === "phone" ? <RecordsNarrowList records={[row]} rowRef={() => {}} />
    : surface === "legacy-list" ? <RecordsList records={[row]} rowRef={() => {}} />
    : <RecordsTable records={[row]} density="normal" rowRef={() => {}} preferences={surface === "table" ? stored : undefined} />;
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}>{node}</BusinessContext.Provider></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  return host;
}

const cases = [
  { name: "clean", report: { ready: true, missing: ["missing_ncf"], stage: "needs_review" }, expected: "" },
  { name: "one gap", report: { ready: false, missing: ["missing_rnc"], stage: "exported" }, expected: "Falta 1 dato" },
  { name: "two gaps", report: { ready: false, missing: ["missing_ncf", "missing_rnc"] }, expected: "Faltan 2 datos" },
] as const;

for (const { name, report, expected } of cases) {
  test(`${name}: status renders only the server readiness and ordered codes`, async () => {
    const host = await status({ ...report, missing: [...report.missing] });
    assert.equal(host.textContent, expected);
    if (report.ready) assert.equal(host.childElementCount, 0);
    else assert.equal(host.querySelector('[style="width: 120px;"]')?.className, "workflow stage fiscal");
  });
  test(`${name}: phone and stored-layout table show the same status`, async () => {
    const table = await status({ ...report, missing: [...report.missing] }, "table");
    assert.equal(table.querySelector('[data-col="stage"]:is(td)')?.textContent, expected);
    assert.equal(table.querySelector('[data-col="missing"]'), null);
    assert.equal(table.querySelector('[data-record-missing-list]'), null);
    assert.ok(!table.textContent?.includes("Motivo"));
    const phone = await status({ ...report, missing: [...report.missing] }, "phone");
    assert.equal(phone.querySelector('[data-record-status]')?.textContent ?? "", expected);
    assert.ok(!phone.textContent?.includes("Listo"));
  });
}

test("only Estado names missing data in a Registros row", async () => {
  const host = await status({
    missing: ["expense_type_missing", "payment_method_missing"],
    dgii_606: { expense_type: null, payment_form: null },
  }, "table");
  const row = host.querySelector("tbody tr")!;
  assert.equal(row.querySelector('td[data-col="stage"]')?.textContent, "Faltan 2 datos");
  for (const cell of row.querySelectorAll('td:not([data-col="stage"])')) {
    assert.doesNotMatch(cell.textContent ?? "", /Falta/);
  }
  for (const column of ["expense_type", "payment_form"]) {
    assert.equal(row.querySelector(`td[data-col="${column}"] [aria-hidden="true"]`)?.textContent, "-");
  }
});

test("two gaps expose every reason in server order through the existing tooltip", async () => {
  const host = await status({ ready: false, missing: ["missing_ncf", "missing_rnc"] });
  const trigger = host.querySelector<HTMLElement>('[tabindex="0"]');
  assert.ok(trigger);
  const { act } = await import("react");
  await act(async () => { trigger.focus(); await new Promise(resolve => setTimeout(resolve, 350)); });
  assert.equal(document.querySelector('[role="tooltip"]')?.textContent, "Falta el NCF · Falta el RNC");
});

test("one gap shows its count and exposes its reason only through the tooltip", async () => {
  const host = await status({ ready: false, missing: ["missing_rnc"] });
  assert.equal(host.textContent, "Falta 1 dato");
  const trigger = host.querySelector<HTMLElement>('[tabindex="0"]');
  assert.ok(trigger);
  const { act } = await import("react");
  await act(async () => { trigger.focus(); await new Promise(resolve => setTimeout(resolve, 350)); });
  assert.equal(document.querySelector('[role="tooltip"]')?.textContent, "Falta el RNC");
});

for (const [lng, pill, chip] of [["es-419", "Falta 1 dato", /Falta NCF/], ["en", "1 detail missing", /NCF missing|\[placeholder\]/]] as const) {
  for (const surface of ["table", "phone", "legacy-table", "legacy-list"] as const) {
    test(`${lng} ${surface}: a purchase missing its NCF says so only in Estado, never in an NCF chip`, async () => {
      const { recordFiscalMark } = await import("@/components/business-app/business-ui");
      const readWithoutNcf = { sin_comprobante: false, fiscal_known: true, fiscal_value: null };
      const host = await status({ ready: false, missing: ["missing_ncf"] }, surface, lng, true, (row) => ({ ...row, marks: { ...row.marks, fiscal: recordFiscalMark(readWithoutNcf) } }));
      assert.equal(host.querySelector("[data-mark]"), null);
      assert.doesNotMatch(host.textContent ?? "", chip);
      if (surface === "table" || surface === "phone") assert.equal(host.querySelector("[data-record-status]")?.textContent, pill);
    });
  }
}

test("unknown readiness keeps the Unknown mark", async () => {
  const host = await status({ ready: undefined, missing: ["missing_rnc"] });
  assert.equal(host.querySelector(".sr-only")?.textContent, "Estado no disponible");
  assert.equal(host.querySelector('[data-record-status]'), null);
});

test("unknown reason codes retain the existing registry-word fallback", async () => {
  const host = await status({ ready: false, missing: ["unheard_of"] }, "cell", "en");
  assert.equal(host.textContent, "1 detail missing");
  const trigger = host.querySelector<HTMLElement>('[tabindex="0"]')!;
  const { act } = await import("react");
  await act(async () => { trigger.focus(); await new Promise(resolve => setTimeout(resolve, 350)); });
  assert.equal(document.querySelector('[role="tooltip"]')?.textContent, "A detail is missing");
});

for (const surface of ["phone", "table"] as const) {
  for (const missing of [["credit_note_payment_form"], ["missing_ncf", "missing_rnc"]]) {
    const description = missing.length === 1 ? "Una nota de crédito usa forma de pago 06" : "Falta el NCF · Falta el RNC";
    test(`${surface}: an actionable row owns focus and the full ${missing.length}-reason description`, async () => {
      const host = await status({ ready: false, missing }, surface);
      const control = host.querySelector<HTMLElement>(surface === "phone" ? 'li[data-record-id] > button' : 'tr[data-record-id]');
      assert.ok(control);
      assert.equal(control.tabIndex, 0);
      const chip = control.querySelector<HTMLElement>('[data-record-status]');
      assert.ok(chip);
      assert.equal(chip.textContent, missing.length === 1 ? "Falta 1 dato" : "Faltan 2 datos");
      const cell = surface === "table" ? control.querySelector('[data-col="stage"]')! : control;
      assert.ok(!cell.querySelector('button, a[href], input, select, textarea, [tabindex]'), "the status must not add a focusable element inside the row control");
      assert.equal(control.getAttribute("aria-description"), description);
      const { act } = await import("react");
      await act(async () => { control.focus(); });
      assert.ok(document.activeElement === control);
      assert.equal(control.getAttribute("aria-description"), description);
      await act(async () => { chip.parentElement!.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); await new Promise(resolve => setTimeout(resolve, 350)); });
      assert.equal(document.querySelector('[role="tooltip"]')?.textContent, description);
    });
    test(`${surface}: ${surface === "table" ? "a grid row without a dossier action owns status focus" : "a plain row keeps its keyboard tooltip"}, ${missing.length} reasons`, async () => {
      const host = await status({ ready: false, missing }, surface, "es-419", false);
      const chip = host.querySelector<HTMLElement>('[data-record-status]');
      assert.equal(chip?.textContent, missing.length === 1 ? "Falta 1 dato" : "Faltan 2 datos");
      if (surface === "table") {
        const control = chip!.closest<HTMLElement>("tr")!;
        assert.equal(control.tabIndex, 0);
        assert.equal(control.getAttribute("aria-description"), description);
        assert.ok(!control.querySelector('[data-col="stage"] [tabindex]'));
        const { act } = await import("react");
        await act(async () => { control.focus(); });
        assert.ok(document.activeElement === control);
        return;
      }
      const trigger = chip?.closest<HTMLElement>('[tabindex="0"]');
      assert.ok(trigger);
      assert.notEqual(trigger.tagName, "TR");
      assert.equal(trigger.closest("button, a[href], [role=button]"), null);
      const { act } = await import("react");
      await act(async () => { trigger.focus(); await new Promise(resolve => setTimeout(resolve, 350)); });
      assert.ok(document.activeElement === trigger);
      assert.equal(document.querySelector('[role="tooltip"]')?.textContent, description);
    });
  }
}
