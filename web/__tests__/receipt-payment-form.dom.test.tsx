import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Cuenta corriente", currency: "DOP", type: "checking" }];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function approvedPurchase(change: (dossier: BusinessDossier) => void) {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.fiscal);
  dossier.review_state = "accepted";
  dossier.capabilities = ["read"];
  change(dossier);
  return dossier;
}

async function paymentRow(dossier: BusinessDossier, language: "es-419" | "en" = "es-419") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { createInstance } = await import("i18next");
  const { I18nextProvider } = await import("react-i18next");
  const { dgiiChoiceLabel } = await import("@/lib/dgii-labels");
  const { default: Facts } = await import("@/components/business-app/ReceiptRecordFacts");
  const catalog = language === "en" ? (await import("@/public/locales/en/common.json")).default : (await import("@/public/locales/es-419/common.json")).default;
  const i18n = createInstance().use(dgiiChoiceLabel);
  await i18n.init({ lng: language, resources: { [language]: { translation: catalog } }, postProcess: dgiiChoiceLabel.name, postProcessPassResolved: true, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Facts dossier={dossier} accounts={accounts} /></I18nextProvider>));
  const row = host.querySelector('[data-testid="receipt-facts-payment"] [data-fact="funding"]');
  const shown = { label: row?.querySelector("dt")?.textContent, value: row?.querySelector("dd")?.textContent };
  await act(async () => root.unmount());
  host.remove();
  return shown;
}

test("an approved purchase says how it was paid with the 606 forma de pago the export writes", async () => {
  const dossier = await approvedPurchase((record) => {
    record.facts.funding = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
    record.dgii = { form: "606", category: "01", payment_method: "01" };
  });
  assert.deepEqual(await paymentRow(dossier), { label: "Cómo se pagó", value: "01 - Efectivo" });
  assert.deepEqual(await paymentRow(dossier, "en"), { label: "How it was paid", value: "01 - Cash" });
});

test("the forma de pago wins over a funding account the record also carries", async () => {
  const dossier = await approvedPurchase((record) => {
    record.dgii = { form: "606", category: "02", payment_method: "03" };
  });
  assert.equal(dossier.facts.funding.state, "known");
  assert.deepEqual(await paymentRow(dossier), { label: "Cómo se pagó", value: "03 - Tarjeta crédito/débito" });
});

test("a purchase with no forma de pago yet shows it as missing, never as an account or a default", async () => {
  const dossier = await approvedPurchase((record) => {
    record.dgii = { form: "606", category: "01", payment_method: null };
  });
  assert.deepEqual(await paymentRow(dossier), { label: "Cómo se pagó", value: "-" });
});
