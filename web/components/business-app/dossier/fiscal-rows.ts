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

/** The agreed order of a record's rows inside their cards, a purchase's then a sale's. Any other field follows, in the server's order. */
const ROW_ORDER: readonly string[] = [
  "id_type", "paid_on", "services_amount", "goods_amount", "itbis", "itbis_cost", "itbis_proportionality", "income_withholding_type", "itbis_withheld", "income_withheld", "selective_tax", "other_taxes",
  "billed_amount", "itbis_withheld_by_third_parties", "income_withheld_by_third_parties", "withheld_on",
];

/**
 * The server's fields this tab leaves out. General shows the RNC, the number
 * and the report's answers as its own rows, Montos owns the tip (the server
 * keeps the declaration's on it, whatever a save sends), and the server
 * refuses any perceived amount. A sale's payment buckets are General's one
 * pick, named by the dossier. Every save sends a hidden field back as it came.
 */
const LEFT_OUT: ReadonlySet<string> = new Set(["rnc", "ncf", "category", "payment_method", "income_type", "legal_tip", "itbis_perceived", "income_perceived"]);
/** NCF modificado belongs to a note: a regular purchase or sale modifies no comprobante. */
const NOTE_ROWS: ReadonlySet<string> = new Set(["modified_ncf"]);
/** What a folded card says, and how it offers its first row, as locale keys. */
export type FoldCopy = { empty: string; add: string };
/** The cards that sit behind one line while they hold nothing. */
const FOLDS: Partial<Record<FiscalGroup, FoldCopy>> = {
  retentions: { empty: "business.dossier.fiscal.no_retentions", add: "business.dossier.fiscal.add_retention" },
  other: { empty: "business.dossier.fiscal.no_other_taxes", add: "business.dossier.fiscal.add_tax" },
};

/** The form a record declares on: a sale the 607, a purchase the 606. Money with no document goes by its kind. */
export function recordForm(dossier: Pick<BusinessDossier, "document_type" | "facts">): FiscalForm {
  return dossier.document_type === "venta" || (!dossier.document_type && dossier.facts.kind.value === "income") ? "607" : "606";
}

/** The line a card sits behind: one that folds, while none of its fields holds anything saved or typed. Null for a card that stays open. */
export function foldOf(group: FiscalGroup, fields: readonly DgiiField[], values: Readonly<Record<string, string>>, broken: ReadonlySet<string>): FoldCopy | null {
  return fields.some((field) => values[field.name] || broken.has(field.name)) ? null : FOLDS[group] ?? null;
}

/**
 * The amounts the server calculates for a purchase, each closing the card it
 * sums. A sale has none, and an amount the server leaves blank shows no row.
 */
export function calculatedRows(calculated: BusinessDossier["dgii_calculated"]): { row: "billed_total" | "itbis_advance"; group: FiscalGroup; amount: string }[] {
  if (!calculated) return [];
  return [
    { row: "billed_total" as const, group: "amounts" as const, amount: calculated.billed_amount },
    ...(calculated.itbis_advance === null ? [] : [{ row: "itbis_advance" as const, group: "itbis" as const, amount: calculated.itbis_advance }]),
  ];
}

const rank = (name: string) => { const at = ROW_ORDER.indexOf(name); return at < 0 ? ROW_ORDER.length : at; };

/** The fields this tab shows, by card; a card with nothing to show is left out. `paymentForms` are the buckets of a sale's one payment pick. */
export function fiscalFieldGroups(fields: readonly DgiiField[], note: boolean, paymentForms: readonly string[] = []): { group: FiscalGroup; fields: DgiiField[] }[] {
  const shown = fields
    .filter((field) => !LEFT_OUT.has(field.name) && !paymentForms.includes(field.name) && (note || !NOTE_ROWS.has(field.name)))
    .sort((left, right) => rank(left.name) - rank(right.name));
  return ORDER
    .map((group) => ({ group, fields: shown.filter((field) => (GROUP_OF[field.name] ?? "other") === group) }))
    .filter((entry) => entry.fields.length > 0);
}
