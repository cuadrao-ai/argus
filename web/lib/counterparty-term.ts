export type Translate = (key: string, options?: Record<string, unknown>) => string;

export type RecordFamily = "purchase" | "sale";

/** A Compra (`recibo`) is a purchase and a Venta a sale; money with no document is neither. */
export function documentFamily(type: "recibo" | "venta" | null | undefined): RecordFamily | null {
  return type === "venta" ? "sale" : type === "recibo" ? "purchase" : null;
}

/** The other party's name on a record of this family: Emisor on a purchase, Cliente on a sale. */
export function counterpartyTerm(t: Translate, family: RecordFamily | null | undefined): string {
  return t("business.terms.counterparty", { context: family ?? undefined });
}

/** A record fact's name. The counterparty's follows the record's family. */
export function factLabel(t: Translate, key: string, family: RecordFamily | null | undefined): string {
  return key === "counterparty" ? counterpartyTerm(t, family) : t(`business.dossier.field.${key}`, { defaultValue: key });
}
