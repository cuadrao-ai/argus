import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Cuenta corriente", currency: "DOP", type: "checking" }];
const unknown = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } as const;

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
  dossier.dgii = { form: "606", category: "01", payment_method: "01" };
  change(dossier);
  return dossier;
}

async function recordScreen(dossier: BusinessDossier) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { createInstance } = await import("i18next");
  const { I18nextProvider } = await import("react-i18next");
  const { dgiiChoiceLabel } = await import("@/lib/dgii-labels");
  const { default: Facts } = await import("@/components/business-app/ReceiptRecordFacts");
  const { default: OwnerChoices } = await import("@/components/business-app/ReceiptOwnerChoices");
  const catalog = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = createInstance().use(dgiiChoiceLabel);
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: catalog } }, postProcess: dgiiChoiceLabel.name, postProcessPassResolved: true, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const choices = <OwnerChoices dossier={dossier} fields={null} failed={false} disabled readOnly saves={{}} onChoose={() => {}} onRetry={() => {}} onCancel={() => {}} onReload={() => {}} />;
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Facts dossier={dossier} accounts={accounts} choices={choices} /></I18nextProvider>));
  const text = host.textContent ?? "";
  const screen = {
    headings: [...host.querySelectorAll("h3")].map((heading) => heading.textContent),
    rows: Object.fromEntries([...host.querySelectorAll("dl > div")].map((row) => [row.querySelector("dt")?.textContent, row.querySelector("dd")?.textContent])),
    count: (needle: string) => text.split(needle).length - 1,
  };
  await act(async () => root.unmount());
  host.remove();
  return screen;
}

test("an approved purchase with no paying account shows its forma de pago once, under Para el 606", async () => {
  const screen = await recordScreen(await approvedPurchase((record) => {
    record.facts.funding = unknown;
  }));
  assert.equal(screen.count("01 - Efectivo"), 1);
  assert.equal(screen.rows["Forma de pago"], "01 - Efectivo");
  assert.equal(screen.count("Cómo se pagó"), 0);
  assert.deepEqual(screen.headings.slice(-2), ["Para el 606", "Pago"]);
  assert.equal(screen.rows["Parte del negocio"], "Todo para el negocio");
});

test("a known paying account shows as Cómo se pagó, beside the forma de pago", async () => {
  const screen = await recordScreen(await approvedPurchase(() => {}));
  assert.match(screen.rows["Cómo se pagó"] ?? "", /^Cuenta corriente/);
  assert.equal(screen.count("01 - Efectivo"), 1);
});

test("a Pago section with nothing known hides its heading", async () => {
  const screen = await recordScreen(await approvedPurchase((record) => {
    record.facts.funding = unknown;
    record.facts.business_share = unknown;
  }));
  assert.equal(screen.headings.at(-1), "Para el 606");
  assert.equal(screen.headings.includes("Pago"), false);
  assert.equal(screen.count("Parte del negocio"), 0);
});
