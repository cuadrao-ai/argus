import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import ReceiptRecordFacts from "@/components/business-app/ReceiptRecordFacts";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { countsAsKnown, factStanding, recordFactRows, reviewCounts } from "@/components/business-app/receipt-fact-rows";
import type { BusinessDossier, BusinessFact } from "@/lib/business-dossier";

const known = (origin: BusinessFact<string>["origin"] & string, verified = false): BusinessFact<string> => ({ state: "known", value: "x", origin, verified, source_ids: [] });
const unknown: BusinessFact<string> = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
const ownerUnknown: BusinessFact<string> = { state: "owner_does_not_know", value: null, origin: "owner_stated", verified: false, source_ids: [] };

async function i18n(lng: "es-419" | "en") {
  const instance = i18next.createInstance();
  await instance.init({ lng, fallbackLng: false, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  return instance;
}

describe("where each fact stands", () => {
  test("verified, stated by a person and decoded from the QR count as known; a suggestion from the read, a default and a missing value do not", () => {
    assert.equal(factStanding(known("extracted", true)), "verified");
    assert.equal(factStanding(known("owner_stated")), "person");
    assert.equal(factStanding(known("member_set")), "person");
    assert.equal(factStanding(known("matched")), "person");
    assert.equal(factStanding(known("qr_decoded")), "qr");
    assert.equal(factStanding(known("extracted")), "suggestion");
    assert.equal(factStanding(known("default")), "default");
    assert.equal(factStanding(unknown), "missing");
    assert.equal(factStanding(ownerUnknown), "owner_unknown");
    for (const standing of ["verified", "person", "qr"] as const) assert.ok(countsAsKnown(standing));
    for (const standing of ["suggestion", "default", "owner_unknown", "missing"] as const) assert.ok(!countsAsKnown(standing));
  });

  test("rows lead with what is settled, then suggestions, then defaults, then what is missing; the counts name suggestions and gaps", () => {
    const facts = {
      kind: known("member_set"),
      counterparty: known("extracted"),
      occurred_on: known("qr_decoded"),
      amount: known("extracted"),
      currency: known("default"),
      category_id: unknown,
      funding: unknown,
      business_share: known("owner_stated", true),
      receipt_state: ownerUnknown,
      fiscal: null,
    } as unknown as BusinessDossier["facts"];
    const rows = recordFactRows(facts);
    assert.deepEqual(rows.map((row) => `${row.key}:${row.standing}`), [
      "business_share:verified",
      "kind:person",
      "occurred_on:qr",
      "counterparty:suggestion",
      "amount:suggestion",
      "currency:default",
      "receipt_state:owner_unknown",
      "category_id:missing",
      "funding:missing",
    ]);
    assert.deepEqual(reviewCounts(rows), { suggestions: 2, missing: 2 });
  });
});

describe("the record facts on the review page", () => {
  test("Spanish: a suggestion reads as one with a Confirmar button for a preparer, a QR value looks like the QR, a missing value says Falta, and the counts line names both", async () => {
    const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
    const dossier = await fixture.dossier(dossierFixtureIds.unknownAmount);
    const facts = {
      ...dossier.facts,
      counterparty: known("extracted"),
      amount: unknown,
      occurred_on: known("qr_decoded"),
      fiscal: { rnc: known("qr_decoded"), ncf: unknown, ecf: known("extracted"), itbis: unknown },
    } as unknown as BusinessDossier["facts"];
    const instance = await i18n("es-419");
    const confirmed: string[] = [];
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={instance}>
        <ReceiptRecordFacts dossier={{ ...dossier, facts }} accounts={[]} confirmable onConfirm={(key) => confirmed.push(key)} />
      </I18nextProvider>,
    );
    assert.ok(html.includes('data-fact="counterparty" data-standing="suggestion"'));
    assert.ok(html.includes("Sugerencia · sin verificar"));
    assert.ok(html.includes('data-testid="confirm-counterparty"') && html.includes(">Confirmar<"));
    assert.ok(html.includes('data-fact="occurred_on" data-standing="qr"'));
    assert.ok(html.includes("Del código QR · sin verificar"));
    assert.ok(html.includes('data-fact="amount" data-standing="missing"') && html.includes(">Falta<"));
    // Fiscal suggestions show their standing but have no in-place confirm (the review patch carries no fiscal fields).
    assert.ok(html.includes('data-fact="ecf" data-standing="suggestion"') && !html.includes('confirm-ecf'));
    assert.ok(html.includes("2 sugerencias por confirmar"));
    assert.ok(html.includes("Faltan") && html.includes("datos"));
    // Settled rows come before suggestions, which come before missing ones.
    assert.ok(html.indexOf('data-fact="occurred_on"') < html.indexOf('data-fact="counterparty"'));
    assert.ok(html.indexOf('data-fact="counterparty"') < html.indexOf('data-fact="amount"'));
    // The value cell still reads Desconocido for a missing value.
    assert.ok(html.includes("Desconocido"));
    assert.ok(!html.includes("verificada") && !html.includes("—"));
  });

  test("a reader who cannot prepare sees the standing without a Confirmar button; English words follow", async () => {
    const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
    const dossier = await fixture.dossier(dossierFixtureIds.unknownAmount);
    const facts = { ...dossier.facts, counterparty: known("extracted") } as unknown as BusinessDossier["facts"];
    const instance = await i18n("en");
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={instance}>
        <ReceiptRecordFacts dossier={{ ...dossier, facts }} accounts={[]} confirmable={false} onConfirm={() => undefined} />
      </I18nextProvider>,
    );
    assert.ok(html.includes("Suggestion · not verified"));
    assert.ok(!html.includes("confirm-counterparty"));
    assert.ok(html.includes("suggestion to confirm") || html.includes("suggestions to confirm"));
  });
});
