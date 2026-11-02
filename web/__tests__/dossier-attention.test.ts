import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import spanish from "@/public/locales/es-419/common.json";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { dossierAttention } from "@/components/business-app/dossier-attention";
import type { BusinessDossier } from "@/lib/business-dossier";

async function setup() {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", fallbackLng: false, resources: { "es-419": { translation: spanish } } });
  const fixtures = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const attention = (dossier: BusinessDossier) => dossierAttention(dossier, i18n.t.bind(i18n));
  return { fixtures, attention };
}

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
    assert.deepEqual(attention(blocked).map((item) => [item.field, item.text]), [["occurred_on", "Fecha de actividad"]]);
  });

  test("a blocker names its reason and its field; one without a field still shows", async () => {
    const { fixtures, attention } = await setup();
    const open = await fixtures.dossier(dossierFixtureIds.unknown);
    const items = attention({ ...open, blockers: [{ code: "unknown_funding", field: "funding" }, { code: "possible_duplicate", field: null }] });
    assert.deepEqual(items.map((item) => item.field), ["funding", null]);
    assert.equal(items[0].text, "Confirma cómo se pagó. · Cómo se pagó");
    assert.match(items[1].text, /ya guardaste/);
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
