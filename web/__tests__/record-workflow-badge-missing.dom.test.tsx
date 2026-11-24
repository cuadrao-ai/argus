import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { ReportRecord } from "@/lib/business-reports-api";
import { createBusinessReportHttpFixture } from "./fixtures/business-report-http-fixture";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });

async function status(report: Partial<ReportRecord>, surface: "cell" | "table" | "phone" = "cell", lng = "es-419") {
  await cleanup();
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng, resources: { [lng]: { translation: (await import(`@/public/locales/${lng}/common.json`)).default } }, interpolation: { escapeValue: false } });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const Component = (await import("@/components/business-app/transacciones/RecordStatusCell")).default;
  const { RecordsTable, RecordsNarrowList } = await import("@/components/business-app/transacciones/TransaccionesRecords");
  const { sampleRecordsPreferences } = await import("@/components/business-app/transacciones/sample-records-preferences");
  const { businessReportRow } = await import("@/lib/business-reporting-wire");
  const row = businessReportRow({ ...createBusinessReportHttpFixture().records[0], ready: false, missing: [], ...report });
  const value = { chosen: { space_id: "s", capabilities: ["read"] }, panel: { kind: "transactions" }, records: { workspace: null }, openPanel: () => {} } as unknown as BusinessContextValue;
  const preferences = sampleRecordsPreferences();
  const stored = { ...preferences, order: ["missing", ...preferences.order], hidden: [] };
  const node = surface === "cell" ? <Component row={row} /> : surface === "phone" ? <RecordsNarrowList records={[row]} rowRef={() => {}} /> : <RecordsTable records={[row]} density="normal" rowRef={() => {}} preferences={stored} />;
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}>{node}</BusinessContext.Provider></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  return host;
}

const cases = [
  { name: "clean", report: { ready: true, missing: ["missing_ncf"], stage: "needs_review" }, expected: "" },
  { name: "one gap", report: { ready: false, missing: ["missing_rnc"], stage: "exported" }, expected: "Falta el RNC" },
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

test("two gaps expose every reason in server order through the existing tooltip", async () => {
  const host = await status({ ready: false, missing: ["missing_ncf", "missing_rnc"] });
  const trigger = host.querySelector<HTMLElement>('[tabindex="0"]');
  assert.ok(trigger);
  const { act } = await import("react");
  await act(async () => { trigger.focus(); await new Promise(resolve => setTimeout(resolve, 350)); });
  assert.equal(document.querySelector('[role="tooltip"]')?.textContent, "Falta el NCF · Falta el RNC");
});

test("unknown readiness keeps the Unknown mark", async () => {
  const host = await status({ ready: undefined, missing: ["missing_rnc"] });
  assert.equal(host.querySelector(".sr-only")?.textContent, "Estado no disponible");
  assert.equal(host.querySelector('[data-record-status]'), null);
});

test("unknown reason codes retain the existing registry-word fallback", async () => {
  assert.equal((await status({ ready: false, missing: ["unheard_of"] }, "cell", "en")).textContent, "A detail is missing");
});
