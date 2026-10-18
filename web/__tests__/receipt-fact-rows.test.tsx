import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import ReceiptRecordFacts from "@/components/business-app/ReceiptRecordFacts";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { blockedFields, factStanding, fiscalFactRows, recordFactRows, reviewCounts, extractedConfirmationPatch } from "@/components/business-app/receipt-fact-rows";
import type { BusinessDossier, BusinessFact } from "@/lib/business-dossier";

const known = (origin: BusinessFact<string>["origin"] & string, verified = false): BusinessFact<string> => ({ state: "known", value: "x", origin, verified, source_ids: [] });
const unknown: BusinessFact<string> = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
const ownerUnknown: BusinessFact<string> = { state: "owner_does_not_know", value: null, origin: "owner_stated", verified: false, source_ids: [] };

async function i18n(lng: "es-419" | "en") {
  const instance = i18next.createInstance();
  await instance.init({ lng, fallbackLng: false, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  return instance;
}

async function fixture() {
  const fixtures = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  return fixtures.dossier(dossierFixtureIds.unknownAmount);
}

async function render(dossier: BusinessDossier, lng: "es-419" | "en" = "es-419", confirmable = true) {
  const instance = await i18n(lng);
  const confirmed: string[] = [];
  const html = renderToStaticMarkup(
    <I18nextProvider i18n={instance}>
      <ReceiptRecordFacts dossier={dossier} accounts={[]} onEdit={confirmable ? (key) => { confirmed.push(key); } : undefined} />
    </I18nextProvider>,
  );
  return { html, confirmed };
}

describe("where each fact stands", () => {
  test("every origin has its own standing; an origin the page does not know falls to a safe 'not verified'", () => {
    assert.equal(factStanding(known("extracted", true)), "verified");
    assert.equal(factStanding(known("owner_stated")), "person");
    assert.equal(factStanding(known("member_set")), "person");
    assert.equal(factStanding(known("matched")), "linked");
    assert.equal(factStanding(known("qr_decoded")), "qr");
    assert.equal(factStanding(known("extracted")), "suggestion");
    assert.equal(factStanding(known("default")), "default");
    assert.equal(factStanding({ ...known("extracted"), origin: "something_new" as never }), "unverified");
    assert.equal(factStanding(unknown), "empty");
    assert.equal(factStanding(ownerUnknown), "owner_unknown");
  });

  test("rows lead with missing data, then preserve the standing order; blockers and open questions mark their fields", () => {
    const dossier = {
      facts: { kind: known("member_set"), counterparty: known("extracted"), occurred_on: known("qr_decoded"), amount: known("extracted"), currency: known("default"), category_id: unknown, funding: unknown, business_share: known("owner_stated", true), receipt_state: ownerUnknown, fiscal: null },
      blockers: [{ code: "missing_fields", field: "amount" }, { code: "unknown_funding", field: "funding" }, { code: "unsupported_kind", field: null }],
      questions: [{ id: "q1", draft_id: "d", field: "receipt_state", asked_of: "owner", channel: "web", state: "open", prompt: "", allowed_answers: [], answer_source_id: null }],
    } as unknown as BusinessDossier;
    const rows = recordFactRows(dossier);
    assert.deepEqual(rows.map((row) => `${row.key}:${row.standing}${row.blocked ? ":blocked" : ""}${row.asked ? ":asked" : ""}`), [
      "category_id:empty",
      "funding:empty:blocked",
      "business_share:verified",
      "kind:person",
      "occurred_on:qr",
      "counterparty:suggestion",
      "amount:suggestion:blocked",
      "currency:default",
      "receipt_state:owner_unknown:asked",
    ]);
    // The numbers are the rows' own: a blocker with no field is the guidance card's; amount has a value
    // (a blocked suggestion) and receipt_state has an open question, so they are "to resolve", not missing.
    assert.deepEqual([...blockedFields(dossier)].sort(), ["amount", "funding"]);
    assert.deepEqual(reviewCounts(rows), { suggestions: 2, missing: 1, unresolved: 2 });
  });
});

describe("the counts line agrees with 'Antes de aprobar'", () => {
  test("all known and no blockers: no counts line at all", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, amount: known("owner_stated") }, blockers: [], questions: [] } as BusinessDossier;
    const { html } = await render(dossier);
    assert.ok(!html.includes('data-testid="receipt-review-counts"'));
    assert.ok(!html.includes("Falta"));
  });

  test("two fields the backend names as missing: 'Faltan 2 datos', each marked Falta with the decision marker; an empty field no blocker names is 'Sin dato'", async () => {
    const base = await fixture();
    const dossier = {
      ...base,
      facts: { ...base.facts, amount: unknown, funding: unknown, category_id: unknown },
      blockers: [{ code: "missing_fields", field: "amount" }, { code: "unknown_funding", field: "funding" }],
      questions: [],
    } as BusinessDossier;
    const { html } = await render(dossier);
    assert.ok(html.includes(">Faltan 2 datos<"));
    assert.ok(html.includes('data-fact="amount" data-standing="empty" data-blocked="true"'));
    assert.ok(html.includes('data-fact="funding" data-standing="empty" data-blocked="true"'));
    assert.equal((html.match(/>Falta</g) ?? []).length, 2);
    assert.equal((html.match(/Necesita una decisión antes de aprobar/g) ?? []).length, 2);
    assert.ok(html.includes('data-fact="category_id" data-standing="empty" class'));
    assert.ok(html.includes(">Sin dato<"));
  });

  test("NCF or e-CF: a fiscal receipt with one of them never counts the other as missing", async () => {
    const base = await fixture();
    const dossier = {
      ...base,
      facts: { ...base.facts, amount: known("owner_stated"), fiscal: { rnc: known("qr_decoded"), ncf: unknown, ecf: known("owner_stated"), itbis: unknown } },
      // The server's reading of the same facts: an e-CF is known.
      fiscal_value: "ecf",
      blockers: [],
      questions: [],
    } as unknown as BusinessDossier;
    const rows = fiscalFactRows(dossier.facts);
    assert.deepEqual(rows.map((row) => `${row.key}:${row.standing}`), ["ecf:person", "rnc:qr", "ncf:empty", "itbis:empty"]);
    assert.deepEqual(reviewCounts([...recordFactRows(dossier), ...rows]), { suggestions: 0, missing: 0, unresolved: 0 });
    const { html } = await render(dossier);
    assert.ok(!html.includes('data-testid="receipt-review-counts"'));
    assert.ok(!html.includes(">Falta<") && !html.includes("Faltan"));
    assert.ok(html.includes('data-fact="ncf" data-standing="empty"') && html.includes(">Sin dato<"));
  });

  test("a blocked field that has a value is 'por resolver', never 'Falta': the line equals the chips (amount is a blocked suggestion)", async () => {
    const base = await fixture();
    const dossier = {
      ...base,
      facts: { ...base.facts, amount: known("extracted"), funding: ownerUnknown, currency: known("owner_stated") },
      blockers: [{ code: "invalid_amount", field: "amount" }, { code: "unknown_funding", field: "funding" }, { code: "currency_mismatch", field: "currency" }],
      questions: [],
    } as unknown as BusinessDossier;
    const { html } = await render(dossier);
    assert.ok(html.includes(">1 sugerencia por confirmar · 3 datos por resolver<"));
    assert.ok(!html.includes("Falta"));
    assert.ok(html.includes('data-fact="amount" data-standing="suggestion" data-blocked="true"'));
    // Confirming the value a blocker refuses cannot succeed, so the blocked suggestion offers no Confirmar.
    assert.ok(!html.includes("confirm-amount"));
    assert.ok(html.includes('data-fact="funding" data-standing="owner_unknown" data-blocked="true"'));
    assert.ok(html.includes('data-fact="currency" data-standing="person" data-blocked="true"'));
    assert.equal((html.match(/Necesita una decisión antes de aprobar/g) ?? []).length, 3);
  });

  test("one suggestion and one missing field: '1 sugerencia por confirmar · Falta 1 dato'", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, counterparty: known("extracted"), amount: unknown }, blockers: [{ code: "missing_fields", field: "amount" }], questions: [] } as BusinessDossier;
    const { html } = await render(dossier);
    assert.ok(html.includes(">1 sugerencia por confirmar · Falta 1 dato<"));
  });
});

describe("the record facts on the review page", () => {
  test("Spanish: AI-read, QR, person-set and linked values each read as what they are; each read value has receipt provenance and one-tap editing for a preparer", async () => {
    const base = await fixture();
    const dossier = {
      ...base,
      facts: { ...base.facts, counterparty: known("extracted"), occurred_on: known("qr_decoded"), category_id: known("matched"), amount: unknown, fiscal: { rnc: known("qr_decoded"), ncf: unknown, ecf: known("extracted"), itbis: unknown } },
      // The server's reading of the same facts: an e-CF is known.
      fiscal_value: "ecf",
      blockers: [{ code: "missing_fields", field: "amount" }],
      questions: [],
    } as unknown as BusinessDossier;
    const { html } = await render(dossier);
    assert.ok(html.includes('data-fact="counterparty" data-standing="suggestion"'));
    assert.equal((html.match(/Leído del recibo/g) ?? []).length, 2);
    assert.ok(!html.includes('data-testid="receipt-read-banner"'));
    assert.ok(!html.includes("Leído de la fuente · sugerencia sin verificar"));
    assert.ok(html.includes("Editar detalles · Comercio"));
    assert.ok(!html.includes("confirm-counterparty") && !html.includes("lucide-sparkles"));
    assert.ok(html.includes('data-fact="occurred_on" data-standing="qr"') && html.includes("Del código QR · sin verificar"));
    assert.ok(html.includes('data-fact="category_id" data-standing="linked"') && html.includes("Vinculado a la fuente · sin verificar"));
    assert.ok(html.includes("Indicado por el dueño · sin verificar"));
    assert.ok(html.includes('data-fact="ecf" data-standing="suggestion"') && !html.includes("confirm-ecf"));
    assert.ok(html.indexOf('data-fact="occurred_on"') < html.indexOf('data-fact="counterparty"'));
    assert.ok(html.indexOf('data-fact="amount"') < html.indexOf('data-fact="counterparty"'));
    assert.ok(html.includes("Desconocido"));
    assert.ok(!html.includes("verificada") && !html.includes("—"));
  });

  test("an RNC nobody knows reads RNC desconocido, never a number", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, fiscal: { rnc: unknown, ncf: known("extracted"), ecf: unknown, itbis: unknown } }, fiscal_value: "ncf", fiscal_known: true } as unknown as BusinessDossier;
    const { html } = await render(dossier);
    assert.ok(/data-fact="rnc"[^]*?RNC desconocido/.test(html));
    assert.ok(!/0{9}/.test(html));
    const english = await render(dossier, "en", false);
    assert.ok(english.html.includes("Unknown RNC"));
  });

  test("no banner when nothing read from the source waits for a person", async () => {
    const base = await fixture();
    const { html } = await render({ ...base, facts: { ...base.facts, counterparty: known("owner_stated") } } as BusinessDossier);
    assert.ok(!html.includes('data-testid="receipt-read-banner"'));
  });

  test("a field the owner does not know still carries the decision marker when a question on it is open", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, funding: ownerUnknown }, blockers: [], questions: [{ id: "q", draft_id: base.draft_id, field: "funding", asked_of: "accountant", channel: "web", state: "open", prompt: "¿Cómo se pagó?", allowed_answers: ["known"], answer_source_id: null }] } as unknown as BusinessDossier;
    const { html } = await render(dossier);
    assert.ok(html.includes('data-fact="funding" data-standing="owner_unknown" data-blocked="true"'));
    assert.ok(html.includes("Necesita una decisión antes de aprobar"));
  });

  test("a reader who cannot prepare sees the standing without a Confirmar button; English words follow", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, counterparty: known("extracted") } } as BusinessDossier;
    const { html } = await render(dossier, "en", false);
    assert.equal((html.match(/Read from source · not verified/g) ?? []).length, 1);
    assert.ok(!html.includes("Read from the source · suggestion, not verified"));
    assert.ok(!html.includes("confirm-counterparty"));
    assert.ok(html.includes("suggestion to confirm") || html.includes("suggestions to confirm"));
  });
});

test("bulk confirmation excludes edits, gaps, defaults, verified facts and unresolved questions", async () => {
  const base = await fixture();
  const dossier = { ...base, facts: { ...base.facts, amount: known("extracted"), counterparty: known("extracted"), occurred_on: unknown, currency: known("default"), category_id: known("extracted", true), kind: known("extracted"), receipt_state: known("extracted") }, blockers: [{ code: "invalid_amount", field: "amount" }], questions: [{ field: "receipt_state", state: "open" }] } as unknown as BusinessDossier;
  const patch = extractedConfirmationPatch(dossier, { counterparty: { state: "unknown", value: null } });
  assert.deepEqual(patch, { kind: { state: "known", value: "x" } });
});
