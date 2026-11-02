import type { DgiiField } from "@/lib/business-dgii";

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

/** The form's fields by group, each group in the server's order; a group with nothing to show is left out. */
export function fiscalFieldGroups(fields: readonly DgiiField[]): { group: FiscalGroup; fields: DgiiField[] }[] {
  return ORDER
    .map((group) => ({ group, fields: fields.filter((field) => (GROUP_OF[field.name] ?? "other") === group) }))
    .filter((entry) => entry.fields.length > 0);
}
