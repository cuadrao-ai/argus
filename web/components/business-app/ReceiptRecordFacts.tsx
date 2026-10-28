"use client";

import { CircleAlert, Pencil } from "lucide-react";
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessFact, BusinessFactField } from "@/lib/business-dossier";
import RncStatusBlock from "./RncStatusBlock";
import { useCategoryLabel } from "./business-ui";
import { presentBusinessFact, presentFiscalFact } from "./receipt-fact-presentation";
import { KIND_FIELDS, PAYMENT_FIELDS, fiscalFactRows, recordFactRows, type FactRow } from "./receipt-fact-rows";
import type { AttentionItem } from "./dossier-attention";
import { resolveLanguage } from "@/lib/language-features";

const FISCAL = ["rnc", "ncf", "ecf", "itbis"] as const;

/** One label/value row; the document type control uses it too, so the form reads as one list. */
export const FACT_ROW_CLASS = "grid grid-cols-[minmax(7.5rem,34%)_minmax(0,1fr)] items-start gap-x-4 border-t border-[#E8EBE6] py-1.5 first:border-t-0 dark:border-white/[0.07]";
export const FACT_LABEL_CLASS = "flex min-h-9 items-center gap-1.5 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70";

/** The texts a row's value may appear as in the original message: what it shows and what it stores. */
function matchAttribute(values: readonly (string | null | undefined)[]): string | undefined {
  const kept = [...new Set(values.filter((value): value is string => typeof value === "string" && value.trim().length > 1))];
  return kept.length ? JSON.stringify(kept) : undefined;
}

/** What the tag says about who stated an unverified value. */
const ORIGIN_TAG: Partial<Record<string, string>> = { qr_decoded: "qr_decoded", owner_stated: "owner_stated", member_set: "member_set", matched: "matched" };

/**
 * The record's facts as one form in three short sections: the activity
 * (headed by its kind), its fiscal facts and how it was paid. A row shows its
 * value as text that a preparer opens for editing with a click or Enter; an
 * unverified value says where it came from, and a row the attention list
 * names carries a marker.
 */
export default function ReceiptRecordFacts({ dossier, accounts, attention = [], typeRow, onEdit, onEditRnc, editor }: {
  dossier: BusinessDossier;
  accounts: BusinessAccount[];
  /** What needs the person; each row an item points at carries a marker. */
  attention?: readonly AttentionItem[];
  /** Compra or Venta, which says the kind: the kind row then shows only while it needs a person. */
  typeRow?: ReactNode;
  onEdit?: (key: BusinessFactField) => void;
  onEditRnc?: () => void;
  editor?: (key: BusinessFactField) => ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const ids = useId();
  const categoryLabel = useCategoryLabel();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const fiscal = dossier.facts.fiscal;
  const labels = {
    unknown: "",
    ownerUnknown: t("business.dossier.owner_unknown", "Owner doesn't know"),
    notRecorded: "",
    yes: t("business.marks.yes", "Yes"),
    no: t("business.marks.no", "No"),
    ownerFunds: t("business.dossier.owner_funds", "Owner's money"),
    businessAccount: t("business.dossier.business_account", "Business account"),
    value: (key: BusinessFactField, value: string) => {
      if (key === "category_id") return categoryLabel(value);
      const scope = key === "kind" ? "kind" : key === "business_share" ? "share" : key === "receipt_state" ? "receipt" : null;
      return scope ? t(`business.dossier.${scope}.${value}`, value) : value;
    },
  };
  const rows = new Map(recordFactRows(dossier).map((row) => [row.key, row]));
  const fiscalRows = new Map(fiscalFactRows(dossier.facts).map((row) => [row.key, row]));
  // Without an NCF and an e-CF the record has no fiscal receipt number: one field says so in place of two empty ones.
  const noFiscal = dossier.fiscal_known === true && !dossier.fiscal_value;
  const flagged = (key: string) => attention.some((item) => item.field === key || (item.field === "fiscal" && (key === "ncf" || key === "ecf" || key === "fiscal_number")));

  const origin = (fact: BusinessFact<unknown> | undefined): ReactNode => {
    if (!fact || fact.state !== "known" || fact.verified || !fact.origin) return null;
    let tag = ORIGIN_TAG[fact.origin];
    if (fact.origin === "extracted") {
      const named = dossier.sources.filter((source) => fact.source_ids.includes(source.id));
      const kinds = new Set((named.length ? named : dossier.sources).map((source) => source.kind));
      tag = kinds.has("attachment") ? "from_receipt" : kinds.has("message") ? "from_message" : "suggested";
    }
    if (!tag) return null;
    return <span data-origin={fact.origin} title={t(`business.dossier.origin.${fact.origin}`, "")} className="ml-1.5 text-[13px] leading-[18px] text-[#56635e] dark:text-white/65">· {t(`business.dossier.origin_tag.${tag}`, tag)}</span>;
  };

  const field = (key: string, label: string, content: ReactNode, row?: FactRow<string>, tag?: ReactNode, match: readonly (string | null | undefined)[] = []) => (
    <div key={key} data-fact={key} data-standing={row?.standing} data-blocked={row?.blocked || row?.asked ? "true" : undefined} data-attention={flagged(key) ? "true" : undefined} data-match={matchAttribute(match)} className={FACT_ROW_CLASS}>
      <dt className={FACT_LABEL_CLASS}>
        {flagged(key) ? <span aria-hidden="true" data-testid="attention-marker" className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#c27a1e] dark:bg-[#e8b26f]" /> : null}
        {label}
      </dt>
      <dd className={`min-w-0 break-words py-[7px] text-[15px] leading-[22px] text-[#172b26] dark:text-white ${key === "amount" || key === "itbis" ? "[font-variant-numeric:tabular-nums]" : ""}`}>
        {key === "amount" || key === "itbis" ? <span className="cuadrao-amount">{content}</span> : content}
        {tag}
        {row?.blocked || row?.asked ? (
          <span className="mt-1 flex items-center gap-1 text-[13px] leading-[18px] text-[#9e2f39] dark:text-[#ec9aa0]">
            <CircleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {key === "occurred_on" && row?.standing === "empty" ? t("business.dossier.approve_reason.date", "Add the date to approve") : t("business.dossier.needs_resolution", "Needs a decision before approval")}
          </span>
        ) : null}
      </dd>
    </div>
  );

  const recordField = (key: BusinessFactField) => {
    const label = t(`business.dossier.field.${key}`, key);
    const value = presentBusinessFact(key, dossier.facts, accounts, locale, labels);
    const row = rows.get(key);
    const opened = editor?.(key);
    const tag = opened ? null : origin(dossier.facts[key]);
    const control = opened ?? (onEdit ? (
      <button
        type="button"
        onClick={() => onEdit(key)}
        aria-label={`${t("business.dossier.edit", "Edit details")} · ${label}`}
        className="group -mx-2 -my-[7px] flex min-h-9 w-[calc(100%+1rem)] items-center gap-2 rounded-item px-2 text-left hover:bg-black/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.06]"
      >
        <span className="min-w-0 flex-1">
          {value}
          {value ? tag : null}
        </span>
        <Pencil className={`h-3.5 w-3.5 shrink-0 text-[#56635e] group-hover:opacity-100 group-focus-visible:opacity-100 dark:text-white/60 ${value ? "opacity-0" : "opacity-70"}`} aria-hidden="true" />
      </button>
    ) : key === "occurred_on" && !value ? (
      <input disabled readOnly aria-label={label} placeholder={t("business.date_picker.placeholder", "dd/mm/aaaa")} value="" className="block min-h-11 w-full rounded-item border border-[#7d8a84] bg-transparent px-3 text-[16px] disabled:opacity-50" />
    ) : value);
    const fact = dossier.facts[key];
    return field(key, label, control, row, opened || onEdit ? null : tag, [value, fact.state === "known" && typeof fact.value === "string" ? fact.value : null]);
  };

  const section = (id: string, title: string, fields: ReactNode) => (
    <section key={id} data-testid={`receipt-facts-${id}`} aria-labelledby={`${ids}-${id}`}>
      <h3 id={`${ids}-${id}`} className="text-[12px] font-medium uppercase leading-4 tracking-[0.06em] text-[#56635e] dark:text-white/60">{title}</h3>
      <dl className="mt-1">{fields}</dl>
    </section>
  );

  const kind = dossier.facts.kind;
  const kindRow = rows.get("kind");
  // A Compra/Venta control already says the kind; the kind row returns while it needs a person.
  const kindShown = !typeRow || kind.state !== "known" || kindRow?.blocked || kindRow?.asked || flagged("kind");
  const fiscalFields = (fiscal || noFiscal ? FISCAL.filter((key) => !noFiscal || (key !== "ncf" && key !== "ecf")) : []).flatMap((key) => {
    if (key === "rnc") return [field("rnc", t("business.dossier.field.rnc", "RNC"), <RncStatusBlock fact={fiscal?.rnc} onEditRnc={onEditRnc} />, undefined, origin(fiscal?.rnc), [fiscal?.rnc.value])];
    const shownValue = presentFiscalFact(key, dossier.facts, locale, labels);
    const shown = field(key, t(`business.dossier.field.${key}`, key), shownValue, fiscalRows.get(key), origin(fiscal?.[key]), [shownValue, fiscal?.[key].value]);
    return key === "itbis" && noFiscal
      ? [field("fiscal_number", `${t("business.dossier.field.ncf", "NCF")} / ${t("business.dossier.field.ecf", "e-CF")}`, t("business.marks.no_fiscal_chip", "No fiscal receipt number")), shown]
      : [shown];
  });

  return (
    <div data-testid="receipt-current-facts" className="space-y-5">
      {section("activity", kind.state === "known" ? t(`business.dossier.kind.${kind.value}`, kind.value) : t("business.dossier.field.kind", "Activity"), <>
        {typeRow}
        {KIND_FIELDS.filter((key) => key !== "kind" || kindShown).map(recordField)}
      </>)}
      {section("fiscal", t("business.dossier.section.fiscal", "Fiscal"), <>
        {recordField("receipt_state")}
        {fiscalFields}
      </>)}
      {section("payment", t("business.dossier.section.payment", "Payment"), PAYMENT_FIELDS.map(recordField))}
    </div>
  );
}
