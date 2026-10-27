"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { FormField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { customerInputLimits } from "@/lib/business-invoices-api";
import { CUSTOMER_FIELD_LIMITS } from "./customer-validation";
import { primaryButtonClass } from "../business-ui";
import { useInvoiceWords } from "./InvoiceDocument";
import { customerErrors, type BusinessCustomer } from "./customer-preview-model";
import styles from "./invoicing-preview.module.css";

export default function CustomerForm({ initial, onSave, onDirty, connection }: { connection?: { busy: boolean; blocked: boolean; status: ReactNode; fieldErrors?: Record<string, string> }; initial: BusinessCustomer; onSave: (customer: BusinessCustomer) => void; onDirty?: (dirty: boolean) => void }) {
  const { word, t } = useInvoiceWords();
  const [draft, setDraft] = useState(initial);
  const form = useRef<HTMLFormElement>(null);
  const limits = connection ? customerInputLimits : CUSTOMER_FIELD_LIMITS;
  const errors = customerErrors(draft, false, limits);
  const keys = ["name", "email", "taxId", "address"] as const;
  const rules: FieldRules<string> = Object.fromEntries(keys.map(key => [key, () => connection && (connection.fieldErrors?.[key === "taxId" ? "tax_id" : key] || errors[key]?.endsWith("_length")) ? t("business.invoicing.invalid") : errors[key] ? word(`error_${errors[key]}`) : null]));
  const checks = useFieldChecks(rules, draft);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  useEffect(() => { onDirty?.(dirty); }, [dirty, onDirty]);
  useEffect(() => { if (checks.attempt) form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(); }, [checks.attempt]);
  return <form ref={form} className={styles.formCard} noValidate onSubmit={event => { event.preventDefault(); if (checks.submit()) onSave({ ...draft, name: draft.name.trim(), email: draft.email.trim(), taxId: draft.taxId.trim(), address: draft.address.trim() }); }}>
    {connection?.status}
    <fieldset className="contents" disabled={connection?.busy || connection?.blocked}>
    {keys.map(key => <FormField key={key} id={`customer-${key}`} label={word(`customer_${key}`)} value={draft[key]} type={key === "email" ? "email" : "text"} inputMode={key === "taxId" ? "numeric" : undefined} required={key === "name"} maxLength={limits[key]} autoComplete="off" placeholder={word(`placeholder_${key}`)} error={checks.errorOf(key)} reserveMessages={key === "address" ? [] : [word(key === "name" ? "error_required" : key === "email" ? "error_email" : "error_tax_id")]} onBlur={() => checks.blur(key)} onChange={event => setDraft(current => ({ ...current, [key]: event.target.value }))} />)}
    <footer className={styles.footer}>{connection ? null : <p className={styles.muted}>{word("customers_local")}</p>}<button type="submit" className={`${primaryButtonClass} ${styles.customerSubmit}`}>{word("customers_save")}</button></footer>
    </fieldset>
  </form>;
}
