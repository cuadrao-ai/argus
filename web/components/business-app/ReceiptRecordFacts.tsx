"use client";

import ReceiptAmounts from "./ReceiptAmounts";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessFact, BusinessFactField, RncRegistryStatus } from "@/lib/business-dossier";
import { formatRnc } from "@/lib/rnc-status";
import { quietButtonClass, useCategoryLabel } from "./business-ui";
import { dossierRowLabel, problemWords, rowProblems, type DossierProblem } from "./dossier-attention";
import { DossierCard, DossierRow, DossierRows, type RowEdit, type RowStatus } from "./dossier/DossierParts";
import { presentBusinessFact } from "./receipt-fact-presentation";
import { PAYMENT_FIELDS, doubtfulFields, recordFactRows, type ReviewRow } from "./receipt-fact-rows";
import { resolveLanguage } from "@/lib/language-features";

/** The texts a row's value may appear as in the original message: what it shows and what it stores. */
function matchAttribute(values: readonly (string | null | undefined)[]): string | undefined {
  const kept = [...new Set(values.filter((value): value is string => typeof value === "string" && value.trim().length > 1))];
  return kept.length ? JSON.stringify(kept) : undefined;
}

const REGISTRY_TONE: Record<RncRegistryStatus, "ok" | "warn" | "bad"> = { verificado: "ok", suspendido: "warn", cese_temporal: "warn", not_found: "warn", desconocido: "warn", dado_de_baja: "bad", anulado: "bad", rechazado: "bad" };

/** The row a problem jumped to; `n` counts the jumps, so a second jump to the same row washes it again. */
export type RowFlash = { row: ReviewRow; n: number };

/** How the form edits: what each row opens, and what the page says under it. Absent for a record nobody can edit now. */
export type FactsReview = {
  amountsPreview?: { net_amount: NonNullable<BusinessDossier["net_amount"]>; mismatch: { difference?: string | null } | null; status: "ready" | "pending" | "error" };
  /** How the row edits in place. */
  edit: (row: ReviewRow) => RowEdit;
  /** What a row's failed save says, and its way back. */
  note: (row: ReviewRow) => ReactNode;
  /** Marking a record that has no fiscal number as Sin recibo. `onMark` is absent for someone who cannot edit it now. */
  noReceipt: { onMark?: (marked: boolean) => void; busy: boolean; saved: boolean; note: ReactNode };
};

/**
 * The General tab: the record's facts as one form in grouped cards. Comprobante
 * holds who issued it, its fiscal number and its date; Reporte 606 the owner's
 * choices; Montos the amounts. Every row is the same grid: label, status slot,
 * value, action slot. The status slot carries every exception: a problem the
 * server names, what the DGII register says of the RNC, a doubtful read.
 *
 * With `review` a row opens its field in place. Without it the same rows only
 * show: there is one form, never a second read-only one.
 */
export default function ReceiptRecordFacts({ dossier, accounts, problems = [], flash = null, typeRow, review, choices }: {
  dossier: BusinessDossier;
  accounts: BusinessAccount[];
  /** Why the record is not Listos; each row a problem points at says it in its status slot. */
  problems?: readonly DossierProblem[];
  flash?: RowFlash | null;
  /** Compra or Venta, shown only while the record's kind needs a person: the Venta switch of Más changes a settled one. */
  typeRow?: ReactNode;
  review?: FactsReview;
  /** The owner's choices, as a card. */
  choices?: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const categoryLabel = useCategoryLabel();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const fiscal = dossier.facts.fiscal;
  const sale = dossier.document_type === "venta";
  const labels = {
    unknown: "",
    ownerUnknown: t("business.dossier.owner_unknown", "Owner doesn't know"),
    notRecorded: "",
    noCurrency: t("business.reception_preview.placeholder.reason.missing_currency", "Currency missing"),
    ownerFunds: t("business.dossier.owner_funds", "Owner's money"),
    businessAccount: t("business.dossier.business_account", "Business account"),
    value: (key: BusinessFactField, value: string) => {
      if (key === "category_id") return categoryLabel(value);
      const scope = key === "kind" ? "kind" : key === "receipt_state" ? "receipt" : null;
      return scope ? t(`business.dossier.${scope}.${value}`, value) : value;
    },
  };
  const rows = new Map(recordFactRows(dossier).map((row) => [row.key, row]));
  // Without an NCF and an e-CF the record has no fiscal receipt number: one field says so in place of two empty ones.
  const noFiscal = dossier.fiscal_known === true && !dossier.fiscal_value;
  const doubtful = doubtfulFields(dossier);
  const flashOf = (row: ReviewRow) => flash?.row === row ? flash.n : undefined;

  /** The status slot: a problem first, then a doubtful read, then what the row's own check says, then a suggestion nobody confirmed. */
  const statusOf = (row: ReviewRow, facts: readonly string[], fact: BusinessFact<unknown> | undefined, own?: RowStatus | null): RowStatus | null => {
    const found = rowProblems(problems, row);
    if (found.length) return { kind: "warn", text: problemWords(found) };
    if (facts.some((key) => doubtful.has(key))) return { kind: "warn", text: t("business.dossier.placeholder.doubtful_read", "check this") };
    if (own) return own;
    if (!fact || fact.state !== "known" || fact.verified) return null;
    const named = dossier.sources.filter((source) => fact.source_ids.includes(source.id));
    const kinds = new Set((named.length ? named : dossier.sources).map((source) => source.kind));
    return fact.origin === "extracted" && !kinds.has("attachment") && !kinds.has("message") ? { kind: "reading", text: t("business.dossier.origin_tag.suggested", "suggested") } : null;
  };
  const edit = (row: ReviewRow) => review?.edit(row);
  const attention = (row: ReviewRow) => rowProblems(problems, row).length > 0;

  const recordRow = (key: BusinessFactField) => {
    const label = key === "funding" && sale ? t("business.dossier.field.collection_method") : dossierRowLabel(t, key, dossier);
    const value = presentBusinessFact(key, dossier.facts, accounts, locale, labels);
    const fact = dossier.facts[key];
    return <DossierRow key={key} row={key} label={label} value={value} status={statusOf(key, [key], fact)} edit={edit(key)} below={review?.note(key)} flash={flashOf(key)} attention={attention(key)} match={matchAttribute([value, fact?.state === "known" && typeof fact.value === "string" ? fact.value : null])} />;
  };

  const registry = dossier.rnc_registry_status;
  const rncRow = <DossierRow
    row="rnc"
    label={dossierRowLabel(t, "rnc", dossier)}
    look="mono"
    value={fiscal?.rnc.state === "known" && fiscal.rnc.value.trim() ? formatRnc(fiscal.rnc.value) : ""}
    status={statusOf("rnc", ["rnc"], fiscal?.rnc, registry ? { kind: REGISTRY_TONE[registry], text: t([`business.dossier.rnc_registry.${registry}`, `business.dossier.placeholder.rnc_registry.${registry}`]) } : null)}
    edit={edit("rnc")}
    below={review?.note("rnc")}
    flash={flashOf("rnc")}
    attention={attention("rnc")}
    match={matchAttribute([fiscal?.rnc.value])}
  />;

  /** The NCF and the e-CF are one fiscal number: the row shows the one the receipt carries. */
  const fiscalKey = fiscal?.ecf.state === "known" ? "ecf" : "ncf";
  const state = dossier.facts.receipt_state;
  const marked = state.state === "known" && state.value === "no_receipt";
  const onMark = review?.noReceipt.onMark;
  const numberRow = <DossierRow
    row="fiscal_number"
    label={dossierRowLabel(t, "fiscal_number", dossier)}
    look={noFiscal ? "text" : "mono"}
    value={fiscal?.[fiscalKey].value ?? (noFiscal ? dossier.sin_comprobante && state.state === "known" ? t(`business.dossier.receipt.${state.value}`, state.value) : t("business.marks.no_fiscal_chip", "No fiscal receipt number") : "")}
    status={statusOf("fiscal_number", ["ncf", "ecf", "fiscal_number"], fiscal?.[fiscalKey])}
    edit={edit("fiscal_number")}
    saved={noFiscal && review?.noReceipt.saved}
    below={<>
      {noFiscal && onMark ? <button type="button" data-testid="mark-no-receipt" disabled={review.noReceipt.busy} className={quietButtonClass} onClick={() => onMark(!marked)}>{marked ? t("business.marks.undo", "Undo") : t("business.dossier.placeholder.mark_no_receipt", "Mark as no receipt")}</button> : null}
      {review?.note("fiscal_number")}
      {noFiscal ? review?.noReceipt.note : null}
    </>}
    flash={flashOf("fiscal_number")}
    attention={attention("fiscal_number")}
    match={matchAttribute([fiscal?.[fiscalKey].value])}
  />;

  const kind = dossier.facts.kind;
  const waits = (key: BusinessFactField) => Boolean(rows.get(key)?.blocked || rows.get(key)?.asked);
  // A clean purchase says its kind nowhere: the kind row and Compra/Venta show only while the kind needs a person.
  const kindWaits = kind.state !== "known" || waits("kind");
  const kindShown = !typeRow || kindWaits;
  const showsFiscal = Boolean(fiscal) || noFiscal || Boolean(edit("rnc")?.onOpen);
  // One payment fact on screen: forma de pago lives in the report card, and funding shows only while the server waits on it.
  const payment = PAYMENT_FIELDS.filter(waits);
  return (
    <div data-testid="receipt-current-facts" className="contents">
      <DossierCard title={t("business.dossier.card.comprobante")} testId="receipt-facts-comprobante">
        <DossierRows>
          {showsFiscal ? rncRow : null}
          {recordRow("counterparty")}
          {showsFiscal ? numberRow : null}
          {recordRow("occurred_on")}
          {kindWaits ? typeRow : null}
          {kindShown ? recordRow("kind") : null}
          {payment.map(recordRow)}
        </DossierRows>
      </DossierCard>
      {choices}
      <ReceiptAmounts dossier={dossier} review={review} problems={problems} flash={flash} />
    </div>
  );
}
