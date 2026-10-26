"use client";

import { useEffect, useRef, useState } from "react";
import { FormField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { primaryButtonClass } from "../business-ui";
import { useInvoiceWords } from "./InvoiceDocument";
import { customerErrors, type BusinessCustomer } from "./customer-preview-model";
import styles from "./invoicing-preview.module.css";

export default function CustomerForm({ initial, onSave, onDirty }: { initial: BusinessCustomer; onSave: (customer: BusinessCustomer) => void; onDirty?: (dirty: boolean) => void }) {
  const { word } = useInvoiceWords();
  const [draft, setDraft] = useState(initial);
  const form = useRef<HTMLFormElement>(null);
  const errors = customerErrors(draft);
  const keys = ["name", "email", "taxId", "address"] as const;
  const rules: FieldRules<string> = Object.fromEntries(keys.map(key => [key, () => errors[key] ? word(`error_${errors[key]}`) : null]));
  const checks = useFieldChecks(rules, draft);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  useEffect(() => { onDirty?.(dirty); }, [dirty, onDirty]);
  useEffect(() => { if (checks.attempt) form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(); }, [checks.attempt]);
  return <form ref={form} className={styles.formCard} noValidate onSubmit={event => { event.preventDefault(); if (checks.submit()) onSave({ ...draft, name: draft.name.trim(), email: draft.email.trim(), taxId: draft.taxId.trim(), address: draft.address.trim() }); }}>
    {keys.map(key => <FormField key={key} id={`customer-${key}`} label={word(`customer_${key}`)} value={draft[key]} type={key === "email" ? "email" : "text"} inputMode={key === "taxId" ? "numeric" : undefined} required={key === "name"} maxLength={key === "email" ? 254 : key === "address" ? 240 : 120} autoComplete="off" placeholder={word(`placeholder_${key}`)} error={checks.errorOf(key)} reserveMessages={key === "address" ? [] : [word(key === "name" ? "error_required" : key === "email" ? "error_email" : "error_tax_id")]} onBlur={() => checks.blur(key)} onChange={event => setDraft(current => ({ ...current, [key]: event.target.value }))} />)}
    <footer className={styles.footer}><p className={styles.muted}>{word("customers_local")}</p><button type="submit" className={`${primaryButtonClass} ${styles.customerSubmit}`}>{word("customers_save")}</button></footer>
  </form>;
}
