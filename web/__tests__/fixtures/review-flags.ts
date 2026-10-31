import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessFact, ReviewFlag, ReviewFlagCode } from "@/lib/business-dossier";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

/** Each flag as the dossier carries it, keyed by its code. */
export const REVIEW_FLAGS = {
  rnc_check_digit: { code: "rnc_check_digit", field: "rnc", confirm: true },
  ncf_malformed: { code: "ncf_malformed", field: "ncf", confirm: true },
  itbis_high: { code: "itbis_high", field: "itbis", confirm: false },
} satisfies { [Code in ReviewFlagCode]: ReviewFlag & { code: Code } };

/** Read values the server flags, each beside the nearest one it lets through (tests/business/test_review_flags.py). */
export const READ_VALUES = {
  rnc: { flagged: "199990022", clean: "199990021" },
  cedula: { flagged: "00113918204", clean: "00113918205" },
  ncf: { flagged: "B01000008", clean: "B0100000001" },
  totals: { flagged: { amount: "1181.01", itbis: "181.01" }, clean: { amount: "1181.00", itbis: "181.00" } },
};

const read = (value: string): BusinessFact<string> => ({ state: "known", value, origin: "extracted", verified: false, source_ids: [] });

/** A paper fiscal receipt as the server would read it: flagged values for the codes given, clean values for the rest. */
export async function flaggedReceipt(codes: readonly ReviewFlagCode[], accounts: BusinessAccount[]): Promise<BusinessDossier> {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.fiscal);
  const pick = <T>(code: ReviewFlagCode, values: { flagged: T; clean: T }) => codes.includes(code) ? values.flagged : values.clean;
  const totals = pick("itbis_high", READ_VALUES.totals);
  dossier.facts.amount = read(totals.amount);
  dossier.facts.fiscal = {
    rnc: read(pick("rnc_check_digit", READ_VALUES.rnc)),
    ncf: read(pick("ncf_malformed", READ_VALUES.ncf)),
    ecf: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] },
    itbis: read(totals.itbis),
  };
  dossier.fiscal_value = "ncf";
  dossier.ecf_checks = null;
  dossier.dgii_qr = null;
  dossier.review_flags = codes.map((code) => REVIEW_FLAGS[code]);
  return dossier;
}

/** The problem body the server refuses an action with: status, a title from the code, and the refusal's context. */
export function refusal(code: string, context?: { existing_record_id: string } | { flags: string[] }): Response {
  const body = { type: `https://api.argus.app/problems/${code.replaceAll("_", "-")}`, title: code.replaceAll("_", " ").replace(/^./, (first) => first.toUpperCase()), status: 422, detail: code, code, request_id: "req-review-flags", ...(context ? { context } : {}) };
  return Response.json(body, { status: 422 });
}
