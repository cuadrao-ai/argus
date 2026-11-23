import type { TFunction } from "i18next";

/**
 * A fiscal field's one name on every tab: the board's, then the 607's for a
 * sale, and the DGII column's for a field neither names.
 */
export function fiscalFieldLabel(t: TFunction, form: "606" | "607", name: string): string {
  return t([`business.dossier.fiscal.field.${name}`, ...(form === "607" ? [`business.dgii.field_607.${name}`] : []), `business.dgii.field.${name}`], { defaultValue: name });
}
