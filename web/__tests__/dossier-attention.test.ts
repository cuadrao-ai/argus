import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { dossierAttention } from "@/components/business-app/dossier-attention";
import type { BusinessDossier } from "@/lib/business-dossier";

async function setup(locale = "es-419") {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: locale, fallbackLng: false, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  const fixtures = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const attention = (dossier: BusinessDossier) => dossierAttention(dossier, i18n.t.bind(i18n), i18n.language);
  return { fixtures, attention, t: i18n.t.bind(i18n) };
}

const duplicateCandidate = (open: BusinessDossier, draftId: string, basis: "read_facts" | "fiscal_number") => ({ draft_id: draftId, version: 1, basis, decisions: [], comparison: { document: { draft_id: open.draft_id, counterparty: null, occurred_on: null, amount: null, currency: null, fiscal_number: null, file: null, received_at: null, approved_at: null, state: "open" as const }, other: { draft_id: draftId, counterparty: null, occurred_on: null, amount: null, currency: null, fiscal_number: null, file: null, received_at: null, approved_at: null, state: "open" as const }, differences: [], recommendation: null } });

describe("what stops approval on a dossier", () => {
  test("only the server's blockers count: read values, e-CF checks and a disagreeing fiscal number do not", async () => {
    const { fixtures, attention } = await setup();
    const fiscal = await fixtures.dossier(dossierFixtureIds.fiscal);
    assert.ok(fiscal.ecf_checks, "the sample carries a failed check and an e-CF that contradicts its NCF");
    assert.equal(fiscal.facts.counterparty.origin, "extracted", "the sample carries a read value nobody confirmed");
    assert.deepEqual(attention(fiscal), []);
  });

  test("a missing fact names its row and needs no sentence", async () => {
    const { fixtures, attention } = await setup();
    const blocked = await fixtures.dossier(dossierFixtureIds.fiscalBlocked);
    assert.deepEqual(attention(blocked).map((item) => [item.field, item.text]), [["occurred_on", "Fecha del comprobante"]]);
  });

  test("a blocker names its reason and its field; one without a field still shows", async () => {
    const { fixtures, attention } = await setup();
    const open = await fixtures.dossier(dossierFixtureIds.unknown);
    const items = attention({ ...open, blockers: [{ code: "unknown_funding", field: "funding" }, { code: "possible_duplicate", field: null }] });
    assert.deepEqual(items.map((item) => item.field), ["funding", null]);
    assert.equal(items[0].text, "Confirma cómo se pagó. · Cómo se pagó");
    assert.equal(items[1].text, "Parece repetido");
    assert.deepEqual(items[1].duplicates, [], "nothing to compare without a candidate");
  });

  test("the duplicate is one item, where its blocker is, with a line and a document per candidate", async () => {
    const { fixtures, attention } = await setup();
    const open = await fixtures.dossier(dossierFixtureIds.unknown);
    const candidate = (draftId: string, basis: "read_facts" | "fiscal_number") => duplicateCandidate(open, draftId, basis);
    const items = attention({ ...open, review_state: "open", blockers: [{ code: "possible_duplicate", field: null }, { code: "unknown_funding", field: "funding" }], duplicate_candidates: [candidate("a", "read_facts"), candidate("b", "fiscal_number")] });
    assert.deepEqual(items.map((item) => item.text.startsWith("Parece repetido")), [true, false]);
    assert.deepEqual(items[0].duplicates, [
      { draftId: "a", text: spanish.business.receipts.duplicate_resolution.basis.read_facts },
      { draftId: "b", text: spanish.business.receipts.duplicate_resolution.basis.fiscal_number },
    ]);
    // An RNC and NCF pair adds no blocker, and still shows, after what blocks.
    const fiscal = attention({ ...open, review_state: "open", blockers: [{ code: "unknown_funding", field: "funding" }], duplicate_candidates: [candidate("b", "fiscal_number")] });
    assert.deepEqual(fiscal.map((item) => item.text === "Parece repetido"), [false, true]);
    assert.equal(attention({ ...open, review_state: "accepted", blockers: [], duplicate_candidates: [candidate("b", "fiscal_number")] }).length, 0, "a closed document compares nothing");
  });

  test.each([
    ["es-419", "recibo", "fiscal_number"],
    ["es-419", "venta", "fiscal_number_sale_placeholder"],
    ["en", "recibo", "fiscal_number"],
    ["en", "venta", "fiscal_number_sale_placeholder"],
  ] as const)("%s renders the %s fiscal basis from %s", async (locale, documentType, key) => {
    const { fixtures, attention, t } = await setup(locale);
    const open = await fixtures.dossier(dossierFixtureIds.unknown);
    const candidate = duplicateCandidate(open, "other", "fiscal_number");
    const [item] = attention({ ...open, document_type: documentType, review_state: "open", blockers: [], duplicate_candidates: [candidate] });
    assert.deepEqual(item.duplicates, [{ draftId: "other", text: t(`business.receipts.duplicate_resolution.basis.${key}`) }]);
    assert.equal(candidate.basis, "fiscal_number");
  });

  test("a blocker with no copy of its own still says something", async () => {
    const { fixtures, attention } = await setup();
    const open = await fixtures.dossier(dossierFixtureIds.unknown);
    const [item] = attention({ ...open, blockers: [{ code: "business_questions_unresolved", field: null }] });
    assert.equal(item.text, spanish.business.dossier.blocker_fallback);
  });

  test("nothing stops a recorded record, and a clean open one has an empty list", async () => {
    const { fixtures, attention } = await setup();
    const ready = await fixtures.dossier(dossierFixtureIds.ready);
    const approved = await fixtures.approveDraft(ready.draft_id, ready.version);
    assert.deepEqual(attention({ ...approved, blockers: [{ code: "business_draft_not_open", field: null }] }), []);
    assert.deepEqual(attention({ ...ready, blockers: [] }), []);
  });
});
