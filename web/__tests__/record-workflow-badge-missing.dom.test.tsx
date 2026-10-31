import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";
import type { ReportRecord } from "@/lib/business-reports-api";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });

async function badge(lng: "en" | "es-419", report: Partial<ReportRecord>) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng, resources: { [lng]: { translation: (await import(`@/public/locales/${lng}/common.json`)).default } }, interpolation: { escapeValue: false } });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const RecordWorkflowBadge = (await import("@/components/business-app/transacciones/RecordWorkflowBadge")).default;
  const row = { id: "r", report: { stage: "needs_fiscal_data", ...report } } as unknown as RecordRow;
  const value = { chosen: { space_id: "s", capabilities: ["read"] } } as unknown as BusinessContextValue;
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><RecordWorkflowBadge row={row} /></BusinessContext.Provider></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  return host.querySelector('[data-record-workflow="fiscal"]')!.textContent;
}

test("the badge names the one missing item in the reader's language", async () => {
  assert.equal(await badge("en", { export_missing: "ncf_missing" }), "NCF is missing");
  assert.equal(await badge("es-419", { export_missing: "ncf_missing" }), "Falta el NCF");
  assert.equal(await badge("en", { export_missing: "rnc_invalid" }), "RNC has an error");
});

test("several missing items read as fiscal details missing", async () => {
  assert.equal(await badge("en", { export_missing: "rnc_invalid", export_missing_several: true }), "Fiscal details missing");
  assert.equal(await badge("es-419", { export_missing: "rnc_invalid", export_missing_several: true }), "Faltan datos fiscales");
});

test("an unmapped or absent code never shows the raw code", async () => {
  assert.equal(await badge("en", { export_missing: "fiscal_unheard_of" }), "A detail is missing");
  assert.equal(await badge("es-419", { export_missing: null }), "Falta un dato");
});
