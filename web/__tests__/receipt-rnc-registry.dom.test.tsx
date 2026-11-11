import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessFact, ReviewFlag } from "@/lib/business-dossier";
import type { RegistryAnswer, TaxId } from "@/lib/business-dgii";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }];
const ACTIVE = "131000014";
const SUSPENDED = "131000022";
const ACTIVE_NAME = "IMPRESOS DEL CARIBE DE PRUEBA, SRL";
const SUSPENDED_NAME = "REPUESTOS DE PRUEBA DEL CIBAO, SRL";
const known = (value: string): BusinessFact<string> => ({ state: "known", value, origin: "matched", verified: true, source_ids: [] });
const answer = (value: string, verification: RegistryAnswer["verification"], name = ACTIVE_NAME, status = "ACTIVO"): RegistryAnswer => ({
  tax_id: { type: "rnc", value },
  verification,
  record: verification === "sin_verificar" ? null : { rnc: value, name, trade_name: null, status, file_date: "2026-10-20" },
  checked_at: "2026-11-09T12:00:00Z",
});

type Ask = { taxId: TaxId; signal?: AbortSignal; resolve: (answer: RegistryAnswer) => void; reject: (error: unknown) => void };
/** A registry that answers only when the test says so, and keeps every question it was asked. */
function registry() {
  const asks: Ask[] = [];
  const lookupRegistry = (taxId: TaxId, signal?: AbortSignal) => new Promise<RegistryAnswer>((resolve, reject) => asks.push({ taxId, signal, resolve, reject }));
  return { asks, lookupRegistry };
}

async function fixture(value: string | null, flags: ReviewFlag[] = []) {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.fiscal);
  if (dossier.facts.fiscal) dossier.facts.fiscal.rnc = value === null ? { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } : known(value);
  return { ...dossier, review_flags: flags };
}

async function setup(lookupRegistry?: ReturnType<typeof registry>["lookupRegistry"]) {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: Facts } = await import("@/components/business-app/ReceiptRecordFacts");
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  const context = (dossier: BusinessDossier) => ({ source: { mode: "live", lookupRegistry, dossier: async () => dossier, dgiiFields: async () => ({ "606": [], "607": [] }) }, reload: () => undefined, records: { inbox: [] }, openPanel: () => undefined }) as unknown as BusinessContextValue;
  const settle = async () => { for (let turn = 0; turn < 4; turn += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
  const facts = async (dossier: BusinessDossier) => { await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context(dossier)}><Facts dossier={dossier} accounts={accounts} /></BusinessContext.Provider></I18nextProvider>)); await settle(); };
  const review = async (dossier: BusinessDossier) => { await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context(dossier)}><Review draftId={dossier.draft_id} /></BusinessContext.Provider></I18nextProvider>)); await settle(); };
  const row = () => host.querySelector<HTMLElement>('[data-fact="rnc"]')!;
  const block = () => row().querySelector<HTMLElement>('[data-testid="rnc-registry"]');
  const reply = async (ask: Ask, value: RegistryAnswer | Error) => { await act(async () => { if (value instanceof Error) ask.reject(value); else ask.resolve(value); }); await settle(); };
  const close = async () => { await act(async () => root.unmount()); host.remove(); await GlobalRegistrator.unregister(); };
  return { act, host, facts, review, row, block, reply, close };
}

test("the review screen asks the registry about a valid supplier RNC, pulses while it waits, then says Verificado", async () => {
  const { asks, lookupRegistry } = registry();
  const page = await setup(lookupRegistry);
  try {
    await page.review(await fixture("1-31-00001-4"));
    assert.deepEqual(asks.map((ask) => ask.taxId), [{ type: "rnc", value: ACTIVE }]);
    assert.equal(page.row().querySelector(".tabular-nums")?.textContent, "1-31-00001-4");
    assert.equal(page.block()?.getAttribute("aria-busy"), "true");
    assert.ok(page.block()?.querySelector(".animate-pulse"), "the wait is the pulse Ajustes shows");
    await page.reply(asks[0], answer(ACTIVE, "verificado"));
    const block = page.block()!;
    assert.equal(block.dataset.legalNameStatus, "verified");
    assert.equal(block.getAttribute("aria-live"), "polite");
    assert.ok(block.querySelector("svg"), "Verificado carries its check");
    assert.deepEqual([...block.children].map((child) => child.textContent), ["Verificado", "Según la DGII", ACTIVE_NAME]);
    assert.equal(asks.length, 1);
  } finally { await page.close(); }
});

test("a supplier the DGII lists as not active shows No activo, the DGII's own status and the registered name", async () => {
  const { asks, lookupRegistry } = registry();
  const page = await setup(lookupRegistry);
  try {
    await page.facts(await fixture(SUSPENDED));
    await page.reply(asks[0], answer(SUSPENDED, "no_activo", SUSPENDED_NAME, "SUSPENDIDO"));
    const block = page.block()!;
    assert.equal(block.dataset.legalNameStatus, "inactive");
    assert.equal(block.querySelector("svg"), null);
    assert.deepEqual([...block.children].map((child) => child.textContent), ["No activo", "Según la DGII: SUSPENDIDO", SUSPENDED_NAME]);
  } finally { await page.close(); }
});

test("a supplier the list does not hold shows the Sin verificar tag and no other line", async () => {
  const { asks, lookupRegistry } = registry();
  const page = await setup(lookupRegistry);
  try {
    await page.facts(await fixture(ACTIVE));
    await page.reply(asks[0], answer(ACTIVE, "sin_verificar"));
    assert.equal(page.block()?.dataset.legalNameStatus, "unverified");
    assert.equal(page.block()?.textContent, "Sin verificar");
    assert.equal(page.row().textContent?.includes("DGII"), false);
  } finally { await page.close(); }
});

test("a cédula is asked as a cédula", async () => {
  const { asks, lookupRegistry } = registry();
  const page = await setup(lookupRegistry);
  try {
    await page.facts(await fixture("001-1234567-8"));
    assert.deepEqual(asks.map((ask) => ask.taxId), [{ type: "cedula", value: "00112345678" }]);
  } finally { await page.close(); }
});

test("a failed check shows its reference and Reintentar asks again", async () => {
  const { asks, lookupRegistry } = registry();
  const page = await setup(lookupRegistry);
  try {
    await page.review(await fixture(ACTIVE));
    await page.reply(asks[0], Object.assign(new Error("down"), { requestId: "ref-rnc-0001" }));
    const block = page.block()!;
    assert.equal(block.dataset.legalNameStatus, "failed");
    assert.ok(block.querySelector('[role="alert"]')?.textContent?.includes("Ha ocurrido un error"));
    assert.equal(block.querySelector('[data-testid="error-reference"]')?.getAttribute("title"), "ref-rnc-0001");
    const retry = [...block.querySelectorAll("button")].find((button) => button.textContent === "Reintentar");
    assert.ok(retry);
    await page.act(async () => retry.click());
    assert.equal(asks.length, 2);
    assert.equal(page.block()?.getAttribute("aria-busy"), "true");
    await page.reply(asks[1], answer(ACTIVE, "verificado"));
    assert.equal(page.block()?.dataset.legalNameStatus, "verified");
    assert.ok(page.block()?.textContent?.includes(ACTIVE_NAME));
  } finally { await page.close(); }
});

test("an answer for the RNC that was there before is ignored once the RNC changes", async () => {
  const { asks, lookupRegistry } = registry();
  const page = await setup(lookupRegistry);
  try {
    await page.facts(await fixture(ACTIVE));
    await page.facts(await fixture(SUSPENDED));
    assert.deepEqual(asks.map((ask) => ask.taxId.value), [ACTIVE, SUSPENDED]);
    assert.equal(asks[0].signal?.aborted, true, "the first question is aborted");
    await page.reply(asks[0], answer(ACTIVE, "verificado"));
    assert.equal(page.block()?.getAttribute("aria-busy"), "true", "the old answer does not land on the new number");
    assert.equal(page.row().textContent?.includes(ACTIVE_NAME), false);
    await page.reply(asks[1], answer(SUSPENDED, "no_activo", SUSPENDED_NAME, "SUSPENDIDO"));
    assert.equal(page.block()?.dataset.legalNameStatus, "inactive");
    assert.ok(page.block()?.textContent?.includes(SUSPENDED_NAME));
  } finally { await page.close(); }
});

for (const [name, value, flags, status, label] of [
  ["a missing RNC", null, [], "missing", "Sin RNC"],
  ["a wrong length", "123", [], "invalid_length", "RNC con error"],
  ["a wrong check digit", "123456789", [{ code: "rnc_check_digit" }], "check_digit", "RNC con error"],
] as const) test(`${name} never asks the registry and shows what it showed before`, async () => {
  const { asks, lookupRegistry } = registry();
  const page = await setup(lookupRegistry);
  try {
    await page.facts(await fixture(value, flags as unknown as ReviewFlag[]));
    assert.equal(asks.length, 0);
    assert.equal(page.block(), null);
    const pill = page.row().querySelector<HTMLElement>('[role="status"]')!;
    assert.equal(page.row().querySelector('[data-testid="rnc-status"]')?.getAttribute("data-rnc-status"), status);
    assert.equal(pill.textContent, label);
    assert.equal(pill.getAttribute("aria-label"), `Estado del RNC: ${label}`);
    assert.equal(pill.style.color, "#9e2f39");
    assert.equal(pill.style.backgroundColor, "#f6dfe0");
  } finally { await page.close(); }
});

test("an all-zero number is in no list: no question, only Sin verificar", async () => {
  const { asks, lookupRegistry } = registry();
  const page = await setup(lookupRegistry);
  try {
    await page.facts(await fixture("000000000"));
    assert.equal(asks.length, 0);
    assert.equal(page.block()?.textContent, "Sin verificar");
  } finally { await page.close(); }
});

test("a source with no registry shows Sin verificar and no failure", async () => {
  const page = await setup();
  try {
    await page.facts(await fixture(ACTIVE));
    assert.equal(page.block()?.dataset.legalNameStatus, "unverified");
    assert.equal(page.block()?.textContent, "Sin verificar");
    assert.equal(page.row().querySelector('[role="alert"]'), null);
  } finally { await page.close(); }
});
