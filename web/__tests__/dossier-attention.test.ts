import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import spanish from "@/public/locales/es-419/common.json";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { dossierAttention } from "@/components/business-app/dossier-attention";
import { fiscalFactRows, recordFactRows } from "@/components/business-app/receipt-fact-rows";
import type { BusinessDossier } from "@/lib/business-dossier";

async function setup() {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", fallbackLng: false, resources: { "es-419": { translation: spanish } } });
  const fixtures = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const attention = (dossier: BusinessDossier) => dossierAttention(dossier, [...recordFactRows(dossier), ...fiscalFactRows(dossier.facts)], i18n.t.bind(i18n));
  return { fixtures, attention };
}

describe("what needs the person on a dossier", () => {
  test("the fiscal case: the unconfirmed merchant, the ITBIS the XML disagrees on in the e-CF card's words, and the NCF the e-CF file contradicts", async () => {
    const { fixtures, attention } = await setup();
    const items = attention(await fixtures.dossier(dossierFixtureIds.fiscal));
    assert.deepEqual(items.map((item) => [item.kind, item.field]), [["check_failed", "itbis"], ["suggestion", "counterparty"], ["contradiction", "fiscal"]]);
    assert.equal(items[0].text, "Revisar: la lectura difiere del XML en ITBIS");
    assert.doesNotMatch(items.map((item) => item.text).join(" "), /read=|xml=/, "the server's raw detail never reaches the person");
    assert.equal(items[1].text, "Comercio o persona: sugerencia por confirmar");
    assert.match(items[2].text, /no coinciden.*E310000000777/);
  });

  test("a blocker names its reason and its field; one without a field still shows", async () => {
    const { fixtures, attention } = await setup();
    const open = await fixtures.dossier(dossierFixtureIds.unknown);
    const items = attention({ ...open, blockers: [{ code: "unknown_funding", field: "funding" }, { code: "possible_duplicate", field: null }] });
    const blockers = items.filter((item) => item.kind === "blocker");
    assert.deepEqual(blockers.map((item) => item.field), ["funding", null]);
    assert.equal(blockers[0].text, "Confirma cómo se pagó. · Cómo se pagó");
    assert.match(blockers[1].text, /ya guardaste/);
  });

  test("a suggested field the server already blocks on is listed once, as the blocker", async () => {
    const { fixtures, attention } = await setup();
    const fiscal = await fixtures.dossier(dossierFixtureIds.fiscal);
    const items = attention({ ...fiscal, blockers: [{ code: "unresolved_facts", field: "counterparty" }] });
    assert.deepEqual(items.filter((item) => item.field === "counterparty").map((item) => item.kind), ["blocker"]);
  });

  test("an e-CF the owner says they do not know, while the file names one, is one contradiction", async () => {
    const { fixtures, attention } = await setup();
    const fiscal = await fixtures.dossier(dossierFixtureIds.fiscal);
    const items = attention({ ...fiscal, fiscal_value: "ecf" });
    assert.deepEqual(items.filter((item) => item.kind === "contradiction").map((item) => item.field), ["fiscal"]);
    assert.equal(attention({ ...fiscal, fiscal_value: "ecf", facts: { ...fiscal.facts, fiscal: { ...fiscal.facts.fiscal!, ecf: { state: "known", value: "E310000000777", origin: "extracted", verified: false, source_ids: [] } } } }).filter((item) => item.kind === "contradiction").length, 0);
  });

  test("nothing needs the person on a recorded record, and a clean open one has an empty list", async () => {
    const { fixtures, attention } = await setup();
    const ready = await fixtures.dossier(dossierFixtureIds.ready);
    const approved = await fixtures.approveDraft(ready.draft_id, ready.version);
    assert.deepEqual(attention({ ...approved, blockers: [{ code: "business_draft_not_open", field: null }] }), []);
    const stated = Object.fromEntries(Object.entries(ready.facts).map(([key, fact]) => [key, fact && "origin" in fact ? { ...fact, origin: "owner_stated" } : fact]));
    assert.deepEqual(attention({ ...ready, blockers: [], ecf_checks: null, facts: stated as BusinessDossier["facts"] }), []);
  });
});
