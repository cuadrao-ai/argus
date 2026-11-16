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

async function badge(lng: "en" | "es-419", report: Partial<ReportRecord>, reason = false) {
  await cleanup();
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng, resources: { [lng]: { translation: (await import(`@/public/locales/${lng}/common.json`)).default } }, interpolation: { escapeValue: false } });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const RecordWorkflowBadge = (await import("@/components/business-app/transacciones/RecordWorkflowBadge")).default;
  const Component = reason ? (await import("@/components/business-app/transacciones/RecordMissingReason")).default : RecordWorkflowBadge;
  const row = { id: "r", report: { ready: false, missing: [], stage: "needs_fiscal_data", fiscal_data: "missing", ...report } } as unknown as RecordRow;
  const value = { chosen: { space_id: "s", capabilities: ["read"] } } as unknown as BusinessContextValue;
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><Component row={row} /></BusinessContext.Provider></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  return host;
}

test("the chip uses ready alone, including an old exported row and an excluded ready row", async () => {
  for (const [ready, stage, expected] of [[false, "exported", "Faltan datos"], [true, "needs_review", "Listo"]] as const) {
    const host = await badge("es-419", { ready, stage, missing: ["rnc_invalid", "ncf_missing"] });
    const chip = host.querySelector("[data-record-workflow]")!;
    assert.equal(chip.textContent, expected);
    assert.equal(chip.closest("button"), null);
    assert.equal(chip.getAttribute("style"), "width: 120px;");
  }
});

test("Motivo shows the first reason and +N, with the full list on keyboard hover", async () => {
  const host = await badge("es-419", { ready: false, missing: ["rnc_invalid", "ncf_missing", "expense_type_missing"] }, true);
  const reason = host.querySelector<HTMLElement>("[data-record-missing]")!;
  assert.equal(reason.textContent, "RNC con error+2");
  const { act } = await import("react");
  await act(async () => { reason.focus(); await new Promise((resolve) => setTimeout(resolve, 350)); });
  assert.match(document.querySelector("[role=tooltip]")!.textContent!, /Falta el NCF/);
  assert.match(document.querySelector("[role=tooltip]")!.textContent!, /Falta el tipo de gasto/);
});

test("Listo has no Motivo, and unknown reason codes use the locale fallback", async () => {
  assert.equal((await badge("es-419", { ready: true, missing: ["ncf_missing"] }, true)).textContent, "");
  assert.equal((await badge("en", { ready: false, missing: ["unheard_of"] }, true)).textContent, "A detail is missing");
});
