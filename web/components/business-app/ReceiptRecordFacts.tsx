"use client";

import { CircleAlert } from "lucide-react";
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessFactField } from "@/lib/business-dossier";
import RncStatusBlock from "./RncStatusBlock";
import { useCategoryLabel } from "./business-ui";
import { SURFACE_CARD } from "./foundation/surfaces";
import { presentBusinessFact, presentFiscalFact } from "./receipt-fact-presentation";
import { ACTIVITY_FIELDS as ACTIVITY, MORE_FIELDS as MORE, fiscalFactRows, recordFactRows, reviewCounts, type FactRow } from "./receipt-fact-rows";
const FISCAL = ["rnc", "ncf", "itbis", "ecf"] as const;

const labelClass = "text-[13px] font-medium leading-[18px] text-[#172b26] dark:text-white";
const sourceClass = "text-[13px] leading-[18px] text-[#56635e] dark:text-white/70";

/**
 * The record's fields as labelled cards. A field shows its value or nothing:
 * the read's source is said once per card, and only a field the backend
 * blocks on carries a line of its own.
 */
export default function ReceiptRecordFacts({ dossier, accounts, onEdit, onEditRnc, editor, cards = true }: {
  dossier: BusinessDossier;
  accounts: BusinessAccount[];
  onEdit?: (key: BusinessFactField) => void;
  onEditRnc?: () => void;
  editor?: (key: BusinessFactField) => ReactNode;
  /** False inside a surface that is already a card. */
  cards?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const ids = useId();
  const categoryLabel = useCategoryLabel();
  const locale = i18n.resolvedLanguage ?? "en";
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
  const counts = reviewCounts([...rows.values(), ...fiscalRows.values()]);
  // Without an NCF and an e-CF the record has no fiscal receipt number: one field says so in place of two empty ones.
  const noFiscal = dossier.fiscal_known === true && !dossier.fiscal_value;
  const read = (found: (FactRow<string> | undefined)[]) => found.some((row) => row?.standing === "suggestion");
  const card = cards ? `${SURFACE_CARD} space-y-4` : "space-y-4 pt-4";

  const field = (key: string, label: string, content: ReactNode, row?: FactRow<string>) => (
    <div key={key} data-fact={key} data-standing={row?.standing} data-blocked={row?.blocked || row?.asked ? "true" : undefined} className="space-y-2">
      <dt className={labelClass}>{label}</dt>
      <dd className={`break-words text-[15px] leading-[22px] text-[#172b26] dark:text-white ${key === "amount" || key === "itbis" ? "[font-variant-numeric:tabular-nums]" : ""}`}>
        {key === "amount" || key === "itbis" ? <span className="cuadrao-amount">{content}</span> : content}
        {row?.blocked || row?.asked ? (
          <span className="mt-2 flex items-center gap-1 text-[13px] leading-[18px] text-[#9e2f39] dark:text-[#ec9aa0]">
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
    const control = editor?.(key) ?? (onEdit ? (
      <button
        type="button"
        onClick={() => onEdit(key)}
        aria-label={`${t("business.dossier.edit", "Edit details")} · ${label}`}
        className="flex min-h-11 w-full items-center rounded-[12px] border border-[#7d8a84] bg-[#FFFEFA] px-3 text-left text-[16px] text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:bg-[#141517] dark:text-white"
      >
        {value}
      </button>
    ) : key === "occurred_on" && !value ? (
      <input disabled readOnly aria-label={label} placeholder={t("business.date_picker.placeholder", "dd/mm/aaaa")} value="" className="block min-h-11 w-full rounded-[12px] border border-[#7d8a84] bg-transparent px-3 text-[16px] disabled:opacity-50" />
    ) : value);
    return field(key, label, control, rows.get(key));
  };

  const section = (id: string, fields: ReactNode, fromReceipt: boolean, title?: string) => (
    <section key={id} data-testid={`receipt-facts-${id}`} aria-labelledby={title ? `${ids}-${id}` : undefined} className={card}>
      {title ? <h3 id={`${ids}-${id}`} className="font-display text-[18px] font-medium leading-6 text-[#172b26] dark:text-white">{title}</h3> : null}
      <dl className="space-y-4">{fields}</dl>
      {fromReceipt ? <p className={sourceClass}>{t("business.dossier.read_from_receipt", "Read from the receipt")}</p> : null}
    </section>
  );

  return (
    <div data-testid="receipt-current-facts" className="space-y-4 desktop:space-y-6">
      {counts.suggestions > 0 || counts.missing > 0 || counts.unresolved > 0 ? (
        <p role="status" data-testid="receipt-review-counts" className={sourceClass}>
          {[
            counts.suggestions > 0 ? t("business.dossier.suggestions_pending", { count: counts.suggestions, defaultValue: "{{count}} suggestions to confirm" }) : null,
            counts.missing > 0 ? t("business.dossier.missing_pending", { count: counts.missing, defaultValue: "{{count}} details missing" }) : null,
            counts.unresolved > 0 ? t("business.dossier.unresolved_pending", { count: counts.unresolved, defaultValue: "{{count}} details to resolve" }) : null,
          ].filter(Boolean).join(" · ")}
        </p>
      ) : null}
      {section("activity", ACTIVITY.map(recordField), read(ACTIVITY.map((key) => rows.get(key))))}
      {fiscal || noFiscal ? section(
        "fiscal",
        FISCAL.filter((key) => !noFiscal || (key !== "ncf" && key !== "ecf")).flatMap((key) => {
          if (key === "rnc") return [field("rnc", t("business.dossier.field.rnc", "RNC"), <RncStatusBlock fact={fiscal?.rnc} onEditRnc={onEditRnc} />)];
          const shown = field(key, t(`business.dossier.field.${key}`, key), presentFiscalFact(key, dossier.facts, locale, labels), fiscalRows.get(key));
          return key === "itbis" && noFiscal
            ? [field("fiscal_number", `${t("business.dossier.field.ncf", "NCF")} / ${t("business.dossier.field.ecf", "e-CF")}`, t("business.marks.no_fiscal_chip", "No fiscal receipt number")), shown]
            : [shown];
        }),
        read([...fiscalRows.values()]),
        t("business.dossier.fiscal_details", "Fiscal details"),
      ) : null}
      {section("more", MORE.map(recordField), read(MORE.map((key) => rows.get(key))))}
    </div>
  );
}
