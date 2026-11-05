"use client";
import { useTranslation } from "react-i18next";
import type { InvoiceDraft } from "@/lib/business-invoices-api";
import { fieldLabelClass } from "@/components/ui/form-field";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import type { InvoiceItem, InvoicePreview } from "./invoice-preview-model";
import styles from "./invoicing-preview.module.css";

function FiscalChoice<T extends string | number>({ name, value, values, label, onChange, error }: { name: string; value: T | null; values: readonly T[]; label: (value: T) => string; onChange: (value: T) => void; error?: string }) {
  const { t } = useTranslation();
  return <div className={fieldLabelClass}>
    <span>{t(`business.invoicing.${name}`)}</span>
    <ToolbarPicker label={t(`business.invoicing.${name}`)} value={value === null ? t("business.invoicing.unset") : label(value)}>{close => values.map(option => <button type="button" key={option} className={styles.option} aria-pressed={value === option} onClick={() => { onChange(option); close(); }}>{label(option)}</button>)}</ToolbarPicker>
    {error ? <p role="alert" className={styles.error}>{t(`business.invoicing.${error === "required" ? "field_required" : "field_unsupported"}`)}</p> : null}
  </div>;
}
export function InvoiceItemFiscalFields({ item, onChange, errors }: { item: InvoiceItem; onChange: (patch: Pick<InvoiceItem, "classification" | "taxTreatment">) => void; errors: Record<string, string> }) {
  const { t } = useTranslation();
  return <div className={styles.fields}>
    <FiscalChoice name="classification" value={item.classification ?? null} values={["goods", "services"]} label={value => t(`business.invoicing.${value}`)} onChange={classification => onChange({ classification, taxTreatment: item.taxTreatment })} error={errors[`items.${item.id}.classification`]} />
    <FiscalChoice name="tax_treatment" value={item.taxTreatment ?? null} values={["taxable", "exempt"]} label={value => t(`business.invoicing.${value}`)} onChange={taxTreatment => onChange({ classification: item.classification, taxTreatment })} error={errors[`items.${item.id}.tax_treatment`]} />
  </div>;
}
export function InvoiceTermsFiscalFields({ value, onChange, errors }: { value: InvoicePreview["fiscalInput"]; onChange: (value: NonNullable<InvoicePreview["fiscalInput"]>) => void; errors: Record<string, string> }) {
  const { t } = useTranslation();
  const input = value ?? { payment_type: null, income_type: null, tax_inclusion: null };
  const income: readonly NonNullable<InvoiceDraft["income_type"]>[] = [1, 2, 3, 4, 5, 6];
  return <>
    <FiscalChoice name="payment_type" value={input.payment_type} values={["cash", "credit", "free"]} label={value => t(`business.invoicing.${value}`)} onChange={payment_type => onChange({ ...input, payment_type })} error={errors.payment_type} />
    <p className={styles.muted}>{t("business.invoicing.payment_help")}</p>
    <FiscalChoice name="income_type" value={input.income_type} values={income} label={value => t(`business.invoicing.income_${value}`)} onChange={income_type => onChange({ ...input, income_type })} error={errors.income_type} />
    <FiscalChoice name="tax_inclusion" value={input.tax_inclusion} values={["excluded", "included"]} label={value => t(`business.invoicing.${value}`)} onChange={tax_inclusion => onChange({ ...input, tax_inclusion })} error={errors.tax_inclusion} />
    {input.tax_inclusion === "included" ? <p className={styles.muted}>{t("business.invoicing.included_help")}</p> : null}
  </>;
}
