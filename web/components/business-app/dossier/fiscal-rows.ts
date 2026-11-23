import type { DgiiField } from "@/lib/business-dgii";
import type { BusinessDossier } from "@/lib/business-dossier";

export type FiscalForm = "606" | "607";
export type FiscalGroup = "identity" | "amounts" | "itbis" | "retentions" | "other";

const ORDER: readonly FiscalGroup[] = ["identity", "amounts", "itbis", "retentions", "other"];

/** The 606 and 607 columns by what they say. The server owns the list, so a field not named here still shows, under "other". */
const GROUP_OF: Readonly<Record<string, FiscalGroup>> = {
  id_type: "identity",
  modified_ncf: "identity",
  paid_on: "identity",
  income_type: "identity",
  services_amount: "amounts",
  goods_amount: "amounts",
  billed_amount: "amounts",
  cash: "amounts",
  bank: "amounts",
  card: "amounts",
  credit: "amounts",
  gift: "amounts",
  barter: "amounts",
  other_payment: "amounts",
  itbis: "itbis",
  legal_tip: "amounts",
  itbis_proportionality: "itbis",
  itbis_cost: "itbis",
  itbis_perceived: "itbis",
  itbis_withheld: "retentions",
  itbis_withheld_by_third_parties: "retentions",
  income_withholding_type: "retentions",
  income_withheld: "retentions",
  income_withheld_by_third_parties: "retentions",
  income_perceived: "retentions",
  withheld_on: "retentions",
};

/** The agreed order of a purchase's rows inside their cards. Any other field follows, in the server's order. */
const ROW_ORDER: readonly string[] = ["id_type", "paid_on", "services_amount", "goods_amount", "itbis", "itbis_cost", "itbis_proportionality", "income_withholding_type", "itbis_withheld", "income_withheld", "selective_tax", "other_taxes"];

/** General shows these four as its own rows. */
const GENERAL_ROWS: readonly string[] = ["rnc", "ncf", "category", "payment_method"];
/**
 * The server's fields this tab leaves out, by form. On a purchase Montos owns
 * the tip, and the server refuses any perceived amount. A hidden field keeps
 * its saved value: every save sends it back as it came.
 */
const LEFT_OUT: Readonly<Record<FiscalForm, ReadonlySet<string>>> = {
  "606": new Set([...GENERAL_ROWS, "legal_tip", "itbis_perceived", "income_perceived"]),
  "607": new Set(GENERAL_ROWS),
};
/** A purchase's NCF modificado belongs to a credit note alone. */
const CREDIT_NOTE_ROWS: ReadonlySet<string> = new Set(["modified_ncf"]);
/** A purchase's Tipo de ID comes from the number in General. */
const READ_ONLY: Readonly<Record<FiscalForm, ReadonlySet<string>>> = { "606": new Set(["id_type"]), "607": new Set() };
/** What a folded card says, and how it offers its first row, as locale keys. */
export type FoldCopy = { empty: string; add: string };
/** The cards of a purchase that sit behind one line while they hold nothing. A sale's stay open. */
const FOLDS: Readonly<Record<FiscalForm, Partial<Record<FiscalGroup, FoldCopy>>>> = {
  "606": {
    retentions: { empty: "business.dossier.fiscal.no_retentions", add: "business.dossier.fiscal.add_retention" },
    other: { empty: "business.dossier.fiscal.no_other_taxes", add: "business.dossier.fiscal.add_tax" },
  },
  "607": {},
};

/**
 * Whether the record is a credit note or a refund, by what the server says of
 * it: the gap it names on an open one, or the reference a saved one holds.
 */
export function inCreditNoteFlow(dossier: Pick<BusinessDossier, "listo_gaps" | "dgii" | "inheritance">): boolean {
  return Boolean(dossier.listo_gaps?.includes("credit_note") || dossier.dgii?.actual_refund === true || dossier.dgii?.modified_ncf || dossier.inheritance?.modified_ncf);
}

export function isReadOnlyRow(form: FiscalForm, name: string): boolean {
  return READ_ONLY[form].has(name);
}

/** The line a card sits behind: one that folds, while none of its fields holds anything saved or typed. Null for a card that stays open. */
export function foldOf(form: FiscalForm, group: FiscalGroup, fields: readonly DgiiField[], values: Readonly<Record<string, string>>, broken: ReadonlySet<string>): FoldCopy | null {
  return fields.some((field) => values[field.name] || broken.has(field.name)) ? null : FOLDS[form][group] ?? null;
}

const rank = (name: string) => { const at = ROW_ORDER.indexOf(name); return at < 0 ? ROW_ORDER.length : at; };

/** The fields this tab shows, by card; a card with nothing to show is left out. */
export function fiscalFieldGroups(form: FiscalForm, fields: readonly DgiiField[], creditNote: boolean): { group: FiscalGroup; fields: DgiiField[] }[] {
  const shown = fields
    .filter((field) => !LEFT_OUT[form].has(field.name) && (form !== "606" || creditNote || !CREDIT_NOTE_ROWS.has(field.name)))
    .sort((left, right) => rank(left.name) - rank(right.name));
  return ORDER
    .map((group) => ({ group, fields: shown.filter((field) => (GROUP_OF[field.name] ?? "other") === group) }))
    .filter((entry) => entry.fields.length > 0);
}
