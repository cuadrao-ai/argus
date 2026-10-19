import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessFact } from "@/lib/business-dossier";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }];
const known = (value: string): BusinessFact<string> => ({ state: "known", value, origin: "matched", verified: true, source_ids: [] });
async function fixture(value: string | null) {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.fiscal);
  if (dossier.facts.fiscal) dossier.facts.fiscal.rnc = value === null ? { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } : known(value);
  return dossier;
}
async function setup(language = "es-419") {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const en = (await import("@/public/locales/en/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: es }, en: { translation: en } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  const close = async () => { await act(async () => root.unmount()); host.remove(); await GlobalRegistrator.unregister(); };
  return { act, root, host, close, i18n, I18nextProvider };
}
for (const [value, label, reason, formatted] of [
  [null, "Sin RNC", "El recibo no tiene RNC. Agrégalo para poder reportarlo en el 606.", null],
  ["123", "RNC con error", "El RNC debe tener 9 dígitos (empresa) u 11 (cédula). Revisa que esté bien escrito.", "123"],
  ["101123456", "RNC sin verificar", "Todavía no lo hemos verificado con la DGII.", "1-01-12345-6"],
  ["00112345678", "RNC sin verificar", "Todavía no lo hemos verificado con la DGII.", "001-1234567-8"],
  ["000000000", "RNC sin verificar", "Todavía no lo hemos verificado con la DGII.", "0-00-00000-0"],
] as const) test(`${label} for ${value}`, async () => {
  const env = await setup(); const { default: Facts } = await import("@/components/business-app/ReceiptRecordFacts");
  const dossier = await fixture(value);
  await env.act(async () => env.root.render(<env.I18nextProvider i18n={env.i18n}><Facts dossier={dossier} accounts={accounts} /></env.I18nextProvider>));
  const row = env.host.querySelector('[data-fact="rnc"]')!;
  const pill = row.querySelector('[role="status"]') as HTMLElement;
  assert.equal(pill.textContent, label); assert.equal(pill.getAttribute("aria-label"), `Estado del RNC: ${label}`);
  assert.ok(pill.querySelector('[aria-hidden="true"]')); assert.ok(row.textContent?.includes(reason));
  assert.equal(pill.style.color, value && value.length !== 3 ? "#735c14" : "#9e2f39");
  assert.equal(pill.style.backgroundColor, value && value.length !== 3 ? "#f2e8c9" : "#f6dfe0");
  if (formatted) assert.equal(row.querySelector(".tabular-nums")?.textContent, formatted);
  assert.equal(row.querySelector("button"), null); assert.equal(row.textContent?.includes("Verified"), false);
  await env.close();
});
test("optional actions use 44px targets, valid values have none", async () => {
  const env = await setup(); const { default: Block } = await import("@/components/business-app/RncStatusBlock"); let edits = 0;
  for (const [fact, label] of [[undefined, "Agregar RNC"], [known("123"), "Editar RNC"]] as const) {
    await env.act(async () => env.root.render(<env.I18nextProvider i18n={env.i18n}><Block fact={fact} onEditRnc={() => { edits += 1; }} /></env.I18nextProvider>));
    const button = env.host.querySelector("button")!; assert.equal(button.textContent, label); assert.ok(button.className.includes("min-h-11") && button.className.includes("min-w-11"));
    await env.act(async () => button.click());
  }
  assert.equal(edits, 2);
  await env.act(async () => env.root.render(<env.I18nextProvider i18n={env.i18n}><Block fact={known("101123456")} onEditRnc={() => { edits += 1; }} /></env.I18nextProvider>));
  assert.equal(env.host.querySelector("button"), null); await env.close();
});
async function mountReview(dossier: BusinessDossier, language = "es-419") {
  const env = await setup(language); const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace"); const { default: Review } = await import("@/components/business-app/ReceiptDossierReview"); let approvals = 0;
  let current = dossier;
  const context = { source: { mode: "fixture", dossier: async () => current, approveDraft: async () => { approvals += 1; return dossier; } }, reload: () => undefined, records: { inbox: [] }, openPanel: () => undefined } as unknown as BusinessContextValue;
  await env.act(async () => env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={context}><Review draftId={dossier.draft_id} /></BusinessContext.Provider></env.I18nextProvider>));
  const clickApprove = async () => { const button = [...env.host.querySelectorAll("button")].find((b) => b.textContent === (language === "es-419" ? "Aprobar" : "Approve expense")); assert.ok(button); await env.act(async () => button.click()); };
  return { ...env, clickApprove, approvals: () => approvals, refreshDossier: async (next: BusinessDossier) => {
    current = next;
    const button = [...env.host.querySelectorAll("button")].find((item) => item.textContent === "Consultar registro actual");
    assert.ok(button);
    await env.act(async () => button.click());
  } };
}
for (const [value, title, body] of [
  [null, "Este recibo no tiene RNC. ¿Aprobar de todos modos?", "Tendrás que agregar el RNC antes de exportar el 606."],
  ["123", "Este RNC tiene un error. ¿Aprobar de todos modos?", "Tendrás que corregirlo antes de exportar el 606."],
] as const) test(`cancel and continue ${title}`, async () => {
  const page = await mountReview(await fixture(value)); await page.clickApprove(); const dialog = document.querySelector('[role="alertdialog"]')!;
  assert.ok(dialog.textContent?.includes(title)); assert.ok(dialog.textContent?.includes(body)); assert.equal(page.approvals(), 0);
  await page.act(async () => [...dialog.querySelectorAll("button")].find((b) => b.textContent === "Cancelar")!.click()); assert.equal(document.querySelector('[role="alertdialog"]'), null); assert.equal(page.approvals(), 0);
  await page.clickApprove(); const confirm = [...document.querySelectorAll('[role="alertdialog"] button')].find((b) => b.textContent === "Aprobar") as HTMLButtonElement;
  await page.act(async () => { confirm.click(); confirm.click(); }); assert.equal(page.approvals(), 1); await page.close();
});
test("unverified and unrelated records approve directly", async () => {
  const unrelated = await fixture(null); unrelated.facts.fiscal = null; unrelated.fiscal_known = false;
  for (const dossier of [await fixture("000000000"), unrelated]) { const page = await mountReview(dossier); await page.clickApprove(); assert.equal(document.querySelector('[role="alertdialog"]'), null); assert.equal(page.approvals(), 1); await page.close(); }
});
test("read-only grants have no approval or RNC action", async () => {
  const dossier = await fixture(null); dossier.capabilities = ["read"]; const page = await mountReview(dossier);
  assert.equal([...page.host.querySelectorAll("button")].some((b) => /^(Aprobar|Agregar RNC|Editar RNC)$/.test(b.textContent ?? "")), false); assert.equal(page.approvals(), 0); await page.close();
});
for (const [value, label, title, body] of [
  [null, "No RNC", "This receipt has no RNC. Approve anyway?", "You'll need to add the RNC before exporting the 606."],
  ["123", "RNC has an error", "This RNC has an error. Approve anyway?", "You'll need to fix it before exporting the 606."],
] as const) test(`English ${label} warning`, async () => {
  const page = await mountReview(await fixture(value), "en"); assert.equal(page.host.querySelector('[data-fact="rnc"] [aria-label]')?.textContent, label); await page.clickApprove(); const dialog = document.querySelector('[role="alertdialog"]')!; assert.ok(dialog.textContent?.includes(title)); assert.ok(dialog.textContent?.includes(body)); await page.close();
});

test("unrelated receipts retain their counts and have no fiscal RNC row", async () => {
  const env = await setup();
  const { default: Facts } = await import("@/components/business-app/ReceiptRecordFacts");
  const dossier = await fixture(null);
  dossier.facts.fiscal = null;
  dossier.fiscal_known = false;
  dossier.facts.counterparty = known("Taller de prueba");
  await env.act(async () => env.root.render(<env.I18nextProvider i18n={env.i18n}><Facts dossier={dossier} accounts={accounts} /></env.I18nextProvider>));
  assert.equal(env.host.querySelector('[data-fact="rnc"]'), null);
  assert.equal(env.host.querySelector('[data-testid="receipt-facts-fiscal"]'), null);
  assert.equal(env.host.querySelector('[data-testid="receipt-review-counts"]'), null);
  await env.close();
});

test("a warning for an older revision never approves the refreshed record", async () => {
  const dossier = await fixture(null);
  const page = await mountReview(dossier);
  await page.clickApprove();
  await page.refreshDossier({ ...dossier, version: dossier.version + 1 });
  const confirm = [...document.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button')].find((button) => button.textContent === "Aprobar");
  assert.ok(confirm);
  await page.act(async () => confirm.click());
  assert.equal(page.approvals(), 0);
  assert.equal(document.querySelector('[role="alertdialog"]'), null);
  await page.close();
});
