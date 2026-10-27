"use client";

import { useEffect, useRef, useState } from "react";
import { FormField, useFieldChecks } from "@/components/ui/FormField";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import { InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import { correctionErrors, correctionStatus, hundredths, invoiceSettlement, type InvoiceCommand, type InvoiceCorrection, type InvoiceCorrectionKind, type InvoicePreview } from "./invoice-preview-model";
import styles from "./invoicing-preview.module.css";

type CorrectionInput = Pick<InvoiceCorrection, "id" | "kind" | "reason" | "amount">;

export default function InvoiceCorrectionForm({ invoice, onSave }: { invoice: InvoicePreview; onSave: (correction: CorrectionInput) => void }) {
  const { word } = useInvoiceWords();
  const [kind, setKind] = useState<InvoiceCorrectionKind>("full_cancellation");
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const form = useRef<HTMLFormElement>(null);
  const submitted = useRef(false);
  const settlement = invoiceSettlement(invoice);
  const minor = kind === "full_cancellation" ? settlement?.creditable ?? 0 : hundredths(amount);
  const errors = correctionErrors(invoice, { kind, reason, amount: minor ?? 0 });
  const checks = useFieldChecks({ reason: () => errors.reason ? word(`error_${errors.reason}`) : null, amount: () => errors.amount ? word(`error_${errors.amount}`) : null }, { reason, amount: kind === "full_cancellation" ? String(minor) : amount });
  const pending = invoice.corrections.some(correction => correctionStatus(correction) === "pending");
  useEffect(() => { if (checks.attempt) form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(); }, [checks.attempt]);
  return <form ref={form} className={styles.panelBody} noValidate onSubmit={event => {
    event.preventDefault();
    if (!checks.submit() || errors.invoice || pending || submitted.current || minor === null) return;
    submitted.current = true;
    onSave({ id: crypto.randomUUID(), kind, reason: reason.trim(), amount: minor });
  }}>
    <ToolbarPicker label={word("correction_type")} value={word(`correction_${kind}`)}>{close => (["full_cancellation", "partial_credit", "debit_adjustment"] as const).map(value => <button type="button" key={value} className={styles.option} onClick={() => { setKind(value); close(); }}>{word(`correction_${value}`)}</button>)}</ToolbarPicker>
    <p className={styles.muted}>{word(kind === "full_cancellation" ? "cancellation_help" : kind === "partial_credit" ? "partial_credit_help" : "debit_help")}</p>
    <p>{word("creditable_amount")} <InvoiceMoney amount={settlement?.creditable ?? 0} currency={invoice.currency} /></p>
    {kind === "full_cancellation" ? <p>{word("amount")} <InvoiceMoney amount={minor ?? 0} currency={invoice.currency} /></p> : <FormField id="invoice-correction-amount" label={`${word("amount")} · ${invoice.currency}`} required value={amount} maxLength={10} inputMode="decimal" placeholder="0.00" error={checks.errorOf("amount")} reserveMessages={[word("error_correction_amount")]} onBlur={() => checks.blur("amount")} onChange={event => setAmount(event.target.value)} />}
    <FormField id="invoice-correction-reason" label={word("correction_reason")} required value={reason} maxLength={500} error={checks.errorOf("reason")} reserveMessages={[word("error_correction_reason")]} onBlur={() => checks.blur("reason")} onChange={event => setReason(event.target.value)} />
    <span className={styles.counter}>{reason.length}/500</span>
    {errors.invoice || pending ? <p className={styles.error} role="alert">{word(pending ? "correction_pending_help" : "error_correction_unavailable")}</p> : null}
    <div className={styles.footer}><p className={styles.muted}>{word("correction_local")}</p><button className={`${primaryButtonClass} ${styles.formSubmit}`} type="submit" disabled={Boolean(errors.invoice) || pending}>{word("prepare_correction")}</button></div>
  </form>;
}

export function InvoiceCorrectionHistory({ invoice, dispatch }: { invoice: InvoicePreview; dispatch: (action: InvoiceCommand) => void }) {
  const { word } = useInvoiceWords();
  if (!invoice.corrections.length) return null;
  const pending = invoice.corrections.some(correction => correctionStatus(correction) === "pending");
  return <section className={styles.corrections} aria-label={word("corrections")}><h3>{word("corrections")}</h3>{invoice.corrections.map(correction => {
    const status = correctionStatus(correction);
    const canRetry = status === "failed" && !pending && Object.keys(correctionErrors(invoice, correction)).length === 0;
    return <article key={correction.id}><header><strong>{word(`correction_${correction.kind}`)}</strong><span className={styles.badge} data-state={status}>{word(`correction_${status}`)}</span></header><InvoiceMoney amount={correction.amount} currency={invoice.currency} /><p>{correction.reason}</p><p className={styles.muted}>{word(`correction_${status}_help`)}</p>{correction.attempts.length > 1 ? <p className={styles.muted}>{word("correction_attempts", { count: correction.attempts.length })}</p> : null}{canRetry ? <button className={quietButtonClass} onClick={() => dispatch({ type: "retry_correction", id: invoice.id, correctionId: correction.id })}>{word("retry_correction")}</button> : null}</article>;
  })}</section>;
}
