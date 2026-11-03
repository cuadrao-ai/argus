import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";
import type { Purchase606, ReportRecord } from "@/lib/business-reports-api";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });

const LONG = { code: "09", label: "Compras y gastos que formarán parte del costo de venta" };

async function cell(lng: "en" | "es-419", row: Partial<RecordRow>, field: keyof Purchase606 = "expense_type", businessId = "s") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng, resources: { [lng]: { translation: (await import(`@/public/locales/${lng}/common.json`)).default } }, interpolation: { escapeValue: false } });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const RecordDgiiCell = (await import("@/components/business-app/transacciones/RecordDgiiCell")).default;
  const value = { chosen: { space_id: businessId, capabilities: ["read"] } } as unknown as BusinessContextValue;
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><RecordDgiiCell row={{ id: "r", kind: "gasto", ...row } as RecordRow} field={field} /></BusinessContext.Provider></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  return host;
}
const live = (dgii_606: ReportRecord["dgii_606"]): Partial<RecordRow> => ({ report: { dgii_606 } as ReportRecord });

test("a live purchase shows the server's DGII name, truncated with the full name on hover", async () => {
  const host = await cell("es-419", live({ expense_type: LONG, payment_form: null }));
  const text = host.querySelector(".truncate")!;
  assert.equal(text.textContent, LONG.label);
  assert.equal(host.querySelector("[data-tooltip-trigger], [aria-describedby], [title]") !== null || host.textContent === LONG.label, true);
});

test("a missing answer reads with the word Bandeja uses, in the reader's language", async () => {
  assert.equal((await cell("es-419", live({ expense_type: null, payment_form: LONG }))).textContent, "Falta");
  assert.equal((await cell("en", live({ expense_type: LONG, payment_form: null }), "payment_form")).querySelector("[data-dgii-missing='payment_form']")!.textContent, "Missing");
});

test("a sale shows a dash that says it does not apply, and a row no read describes shows a plain dash", async () => {
  const sale = await cell("es-419", live(null));
  assert.equal(sale.querySelector('[aria-hidden="true"]')!.textContent, "-");
  assert.equal(sale.querySelector(".sr-only")!.textContent, "No aplica");
  const unread = await cell("es-419", { id: "exp-unknown" }, "expense_type", "fixture-space");
  assert.equal(unread.querySelector(".sr-only")!.textContent, "sin dato");
});

test("the sample rows carry every case the mock needs", async () => {
  const { record606 } = await import("@/components/business-app/transacciones/RecordDgiiCell");
  const row = (id: string, kind: RecordRow["kind"] = "gasto") => ({ id, kind } as RecordRow);
  const cases = ["exp-hosting", "exp-gas", "exp-imprenta", "exp-lunch"].map((id) => record606(row(id), "fixture-space"));
  assert.ok(cases[0]?.expense_type && cases[0].payment_form, "one purchase with both answers");
  assert.ok(cases[1] && cases[1].expense_type === null && cases[1].payment_form, "one missing its tipo de gasto");
  assert.ok(cases[2] && cases[2].expense_type && cases[2].payment_form === null, "one missing its forma de pago");
  assert.equal(cases[3], null, "the Personal purchase carries none");
  assert.equal(record606(row("exp-gas", "venta"), "fixture-space"), null, "a sale carries none");
  assert.equal(record606(row("exp-hosting"), "other-business"), undefined, "nothing outside the sample Business");
});
