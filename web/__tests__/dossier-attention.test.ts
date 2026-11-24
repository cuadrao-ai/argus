import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, test } from "bun:test";
import i18next from "i18next";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { dossierProblems } from "@/components/business-app/dossier-attention";
import { LISTO_GAPS, RNC_REGISTRY_STATUSES, type BusinessDossier, type ListoGap } from "@/lib/business-dossier";

/** The enum values the checked API document lists under one field of one schema, up to the first line that is not a value. */
function contractEnum(schema: string, field: string): string[] {
  const lines = readFileSync(join(import.meta.dir, "../../docs/api/openapi.yaml"), "utf8").split("\n");
  const values: string[] = [];
  for (const line of lines.slice(lines.indexOf(field, lines.indexOf(`    ${schema}:`)) + 1)) {
    const value = line.match(/^ +- ([a-z_]+)$/);
    if (value) values.push(value[1]);
    else if (values.length) break;
  }
  return values;
}

async function setup(locale = "es-419") {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: locale, fallbackLng: false, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  const fixtures = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const problems = (dossier: BusinessDossier) => dossierProblems(dossier, i18n.t.bind(i18n));
  return { fixtures, problems, t: i18n.t.bind(i18n) };
}

describe("why a record is not Listos", () => {
  test("every gap the web names is one the API's dossier may send", () => {
    const sent = contractEnum("BusinessDossier", "        listo_gaps:");
    assert.ok(sent.length, "the API document lists the dossier's gaps");
    assert.deepEqual(LISTO_GAPS.filter((gap) => !sent.includes(gap)), []);
  });

  test("the web's register statuses are the API's", () => {
    const statuses = contractEnum("RegistryStatus", "      enum:");
    assert.ok(statuses.length, "the API document lists the register statuses");
    assert.deepEqual([...statuses, "not_found"].sort(), [...RNC_REGISTRY_STATUSES].sort());
  });

  for (const locale of ["es-419", "en"]) {
    test(`every reason has its own title and text in ${locale}, and none is the old fallback`, async () => {
      const { fixtures, problems } = await setup(locale);
      const dossier = await fixtures.dossier(dossierFixtureIds.fiscal);
      const fallback = /necesita más revisión|needs further review/i;
      for (const reason of LISTO_GAPS) {
        const [problem] = problems({ ...dossier, listo_gaps: [reason], review_flags: [], duplicate_candidates: [] });
        assert.equal(problem.reason, reason);
        for (const words of [problem.title, problem.text, problem.where]) {
          assert.ok(words.trim(), `${reason} says something`);
          assert.ok(!words.includes("business."), `${reason} has a key in ${locale}: ${words}`);
          assert.doesNotMatch(words, fallback);
        }
      }
    });
  }

  test("the problems equal listo_gaps item for item, in the server's order", async () => {
    const { fixtures, problems } = await setup();
    const dossier = await fixtures.dossier(dossierFixtureIds.fiscal);
    const gaps: ListoGap[] = ["check_details", "duplicate", "missing_date", "check_details", "missing_rnc", "invalid_ncf", "review_flag", "unverified_sender"];
    assert.deepEqual(problems({ ...dossier, listo_gaps: gaps }).map((problem) => problem.reason), gaps);
    assert.deepEqual(problems({ ...dossier, listo_gaps: [] }), []);
    assert.deepEqual(problems({ ...dossier, listo_gaps: undefined, blockers: [{ code: "unknown_funding", field: "funding" }] }), [], "a blocker is not a reason: only the server's gaps are");
  });

  test("each problem points at the row that fixes it", async () => {
    const { fixtures, problems } = await setup();
    const dossier = await fixtures.dossier(dossierFixtureIds.fiscal);
    const reasons = {
      missing_rnc: { field: "rnc", words: "business.transactions.layout.workflow.missing.missing_rnc" },
      missing_ncf: { field: "ncf", words: "business.transactions.layout.workflow.missing.missing_ncf" },
      missing_amount: { field: "amount", words: "business.dossier.gap.missing_amount.title" },
    };
    const at = (reason: ListoGap, more: Partial<BusinessDossier> = {}) => problems({ ...dossier, reasons, review_flags: [], ...more, listo_gaps: [reason] })[0];
    assert.equal(at("missing_rnc", { reasons: { missing_rnc: { ...reasons.missing_rnc, field: "occurred_on" } } }).row, "occurred_on", "the payload names the row");
    assert.equal(at("missing_ncf").row, "fiscal_number");
    assert.equal(at("missing_rnc").row, "rnc");
    assert.equal(at("missing_rnc").where, "General · RNC");
    assert.equal(at("missing_ncf").title, "Falta el NCF");
    assert.equal(at("missing_ncf").text, "Escríbelo como aparece en el documento.");
    assert.equal(at("missing_amount").where, "General · Total");
    assert.equal(at("invalid_ncf").title, "Revisa el NCF");
    assert.equal(at("invalid_ncf").text, "El NCF no tiene el formato de la serie B o E.");
    assert.equal(at("invalid_rnc", { review_flags: [{ code: "rnc_check_digit", field: "rnc", confirm: true }] }).text, "El dígito verificador de este RNC no coincide. Puede tener un número mal escrito.");
    assert.equal(at("invalid_rnc").text, "El RNC debe tener 9 dígitos (empresa) u 11 (cédula). Revisa que esté bien escrito.");
    assert.equal(at("review_flag", { review_flags: [{ code: "rnc_check_digit", field: "rnc", confirm: true }, { code: "amounts_mismatch", field: "amount", confirm: false, difference: "12.00" }] }).row, "amount");
    assert.equal(at("check_details", { year_to_check: true }).row, "occurred_on");
    assert.equal(at("check_details", { year_to_check: false }).row, null);
    assert.equal(at("unverified_sender").where, "General");
  });

  test("Parece repetido says why the server thinks so and names the document to compare", async () => {
    const { fixtures, problems } = await setup();
    const dossier = await fixtures.dossier(dossierFixtureIds.fiscal);
    const candidate = { draft_id: "other-draft", version: 1, basis: "fiscal_number" as const, decisions: [] } as unknown as NonNullable<BusinessDossier["duplicate_candidates"]>[number];
    const [problem] = problems({ ...dossier, listo_gaps: ["duplicate"], duplicate_candidates: [candidate] });
    assert.equal(problem.title, "Parece repetido");
    assert.equal(problem.text, "Mismo RNC y NCF que otro documento.");
    assert.equal(problem.where, "General · Comparar");
    assert.equal(problem.compare, "other-draft");
  });
});
