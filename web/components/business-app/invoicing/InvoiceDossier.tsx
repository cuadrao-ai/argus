"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Check, Download, Mail, Link2, Plus } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { FormField, useFieldChecks } from "@/components/ui/FormField";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass } from "../business-ui";
import { todayIso } from "../business-format";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import InvoiceDocument, { InvoiceDate, InvoiceMoney, printInvoiceDocument, useInvoiceWords } from "./InvoiceDocument";
import { hundredths, invoiceAmounts, invoiceState, validIsoDate, type InvoiceCommand, type InvoicePayment, type InvoicePreview } from "./invoice-preview-model";
import styles from "./invoicing-preview.module.css";

export default function InvoiceDossier({ invoice, business, dispatch, onClose, onEdit }: { invoice: InvoicePreview; business: string; dispatch: (action: InvoiceCommand) => void; onClose: () => void; onEdit: () => void }) {
  const { word, t } = useInvoiceWords();
  const [view, setView] = useState<"detail" | "customer" | "delivery" | "payment">("detail");
  const amount = invoiceAmounts(invoice);
  const [printError, setPrintError] = useState(false);
  const title = view === "detail" ? invoice.reference : word(view === "customer" ? "customer_preview" : view === "payment" ? "record_payment" : "prepare_delivery");
  return <AdaptivePanel title={title} summary={`${invoice.customer.name} · ${business}`} width="record" modal={false} snaps={["full"]} initialSnap="full" closeLabel={t("common.close")} onClose={onClose} onBack={view === "detail" ? undefined : () => setView("detail")} backLabel={word("back_invoice")}>
    {view === "customer" ? <div className={styles.panelBody}><p className={styles.muted}>{word("customer_notice")}</p><InvoiceDocument invoice={invoice} business={business} /><button className={secondaryButtonClass} onClick={() => setPrintError(!printInvoiceDocument(invoice.reference))}><Download size={17} />{word("pdf")}</button>{printError ? <p role="alert" className={styles.error}>{word("print_blocked")}</p> : null}</div> : null}
    {view === "delivery" ? <Delivery invoice={invoice} onPrepare={preparation => { dispatch({ type: "prepare", id: invoice.id, preparation }); setView("detail"); }} /> : null}
    {view === "payment" ? <Payment invoice={invoice} onSave={payment => { dispatch({ type: "pay", id: invoice.id, payment }); setView("detail"); }} /> : null}
    {view === "detail" ? <div className={styles.panelBody}>
      <div className={styles.balance}><span>{word(invoice.issuance === "issued" ? "balance" : "document_total")}</span><strong>{amount ? <InvoiceMoney amount={invoice.issuance === "issued" ? amount.balance : amount.total} currency={invoice.currency} /> : "—"}</strong><span className={styles.badge} data-state={invoiceState(invoice)}>{word(`state_${invoiceState(invoice)}`)}</span></div>
      <dl className={styles.facts}><div><dt>{word("document_total")}</dt><dd>{amount ? <InvoiceMoney amount={amount.total} currency={invoice.currency} /> : "—"}</dd></div>{invoice.issuance === "issued" ? <div><dt>{word("collected")}</dt><dd>{amount ? <InvoiceMoney amount={amount.paid} currency={invoice.currency} /> : "—"}</dd></div> : null}<div><dt>{word("due_date")}</dt><dd><InvoiceDate date={invoice.dueOn} /></dd></div><div><dt>{word("issuance")}</dt><dd>{word(`issuance_${invoice.issuance}`)}</dd></div><div><dt>{word("delivery")}</dt><dd>{word(`delivery_${invoice.delivery}`)}</dd></div></dl>
      <div className={styles.actions}><button className={secondaryButtonClass} onClick={() => setView("customer")}><ArrowUpRight size={17} />{word("customer_preview")}</button>{invoice.issuance === "draft" ? <button className={quietButtonClass} onClick={onEdit}>{word("edit_draft")}</button> : null}</div>
      {invoice.issuance === "uncertain" ? <div className={styles.notice}><strong>{word("uncertain")}</strong><p>{word("uncertain_help")}</p><button className={secondaryButtonClass} disabled>{word("check_status")}</button><p className={styles.muted}>{word("status_dependency")}</p></div> : invoice.issuance === "draft" ? <div className={styles.footer}><p className={styles.muted}>{word("issue_help")}</p><button className={`${primaryButtonClass} ${styles.formSubmit}`} onClick={() => dispatch({ type: "issue", id: invoice.id })}>{word("issue_sample")}</button></div> : <div className={styles.actions}><button className={secondaryButtonClass} onClick={() => setView("delivery")}><Mail size={17} />{word(invoice.delivery === "failed" ? "review_delivery" : "prepare_delivery")}</button>{amount && amount.balance > 0 ? <button className={primaryButtonClass} onClick={() => setView("payment")}><Plus size={17} />{word("record_payment")}</button> : null}</div>}
      {invoice.delivery === "failed" ? <p className={styles.notice}>{word("delivery_help")}</p> : null}
      <section><h3>{word("payments")}</h3>{invoice.payments.length ? <ul className={styles.paymentList}>{invoice.payments.map(payment => <li key={payment.id}><span><Check size={16} /><span>{word(`method_${payment.method}`)}<small><InvoiceDate date={payment.date} />{payment.reference ? ` · ${payment.reference}` : ""}</small></span></span><InvoiceMoney amount={payment.amount} currency={payment.currency} /></li>)}</ul> : <p className={styles.muted}>{word("no_payments")}</p>}</section>
      <details className={styles.history}><summary>{word("timeline")}</summary><p>{word("draft_saved")}</p>{invoice.issuance === "issued" ? <p>{word("issuance_issued")}</p> : null}{invoice.delivery === "prepared" ? <p>{word("delivery_prepared")}</p> : null}{invoice.payments.map(payment => <p key={payment.id}><InvoiceDate date={payment.date} /> · {word("payment_recorded")} <InvoiceMoney amount={payment.amount} currency={payment.currency} /></p>)}</details>
    </div> : null}
  </AdaptivePanel>;
}

function Payment({ invoice, onSave }: { invoice: InvoicePreview; onSave: (payment: InvoicePayment) => void }) {
  const { word } = useInvoiceWords();
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIso());
  const [method, setMethod] = useState<InvoicePayment["method"]>("transfer");
  const [reference, setReference] = useState("");
  const form = useRef<HTMLFormElement>(null);
  const balance = invoiceAmounts(invoice)?.balance ?? 0;
  const minor = hundredths(amount);
  const checks = useFieldChecks({ amount: () => minor !== null && minor > 0 && minor <= balance ? null : word("error_payment_amount"), date: () => validIsoDate(date) && date <= todayIso() ? null : word("error_payment_date") }, { amount, date });
  useEffect(() => { if (checks.attempt) form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(); }, [checks.attempt]);
  return <form ref={form} noValidate className={styles.panelBody} onSubmit={event => { event.preventDefault(); if (checks.submit() && minor !== null) onSave({ id: crypto.randomUUID(), amount: minor, date, currency: invoice.currency, method, reference: reference.trim() }); }}>
    <p>{word("balance")}: <InvoiceMoney amount={balance} currency={invoice.currency} /></p>
    <FormField id="invoice-payment-amount" label={`${word("amount")} · ${invoice.currency}`} value={amount} inputMode="decimal" maxLength={10} placeholder="0.00" error={checks.errorOf("amount")} reserveMessages={[word("error_payment_amount")]} onBlur={() => checks.blur("amount")} onChange={event => setAmount(event.target.value)} />
    <FormField id="invoice-payment-date" label={word("payment_date")} value={date} maxLength={10} placeholder={word("date_placeholder")} error={checks.errorOf("date")} reserveMessages={[word("error_payment_date")]} onBlur={() => checks.blur("date")} onChange={event => setDate(event.target.value)} />
    <ToolbarPicker label={word("method")} value={word(`method_${method}`)}>{close => (["transfer", "cash", "other"] as const).map(value => <button type="button" key={value} className={styles.option} onClick={() => { setMethod(value); close(); }}>{word(`method_${value}`)}</button>)}</ToolbarPicker>
    <FormField id="invoice-payment-reference" label={word("payment_reference")} maxLength={100} value={reference} reserveMessages={[]} placeholder={word("reference_placeholder")} onChange={event => setReference(event.target.value)} />
    <p className={styles.muted}>{word("payment_help")}</p>
    <div className={styles.footer}><button type="submit" className={`${primaryButtonClass} ${styles.formSubmit}`}>{word("record_payment")}</button></div>
  </form>;
}

function Delivery({ invoice, onPrepare }: { invoice: InvoicePreview; onPrepare: (preparation: NonNullable<InvoicePreview["deliveryPreparation"]>) => void }) {
  const { word } = useInvoiceWords();
  const [channel, setChannel] = useState<"email" | "link">(invoice.deliveryPreparation?.channel ?? "email");
  const [email, setEmail] = useState(invoice.deliveryPreparation?.email ?? invoice.customer.email);
  const form = useRef<HTMLFormElement>(null);
  const checks = useFieldChecks({ email: () => channel === "link" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? null : word("error_email") }, { email });
  useEffect(() => { if (checks.attempt) form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(); }, [checks.attempt]);
  return <form ref={form} noValidate className={styles.panelBody} onSubmit={event => { event.preventDefault(); if (checks.submit()) onPrepare({ channel, email: email.trim() }); }}>
    <SegmentedControl label={word("delivery")} value={channel} onChange={setChannel} fill segments={[{ key: "email", label: word("email"), icon: Mail }, { key: "link", label: word("link"), icon: Link2 }]} />
    {channel === "email" ? <FormField id="invoice-recipient" label={word("recipient")} required type="email" maxLength={254} value={email} error={checks.errorOf("email")} reserveMessages={[word("error_email")]} onBlur={() => checks.blur("email")} onChange={event => setEmail(event.target.value)} /> : <div className={styles.notice}><Link2 size={22} /><p>{word("link_help")}</p></div>}
    <p>{word("delivery_preview", { name: invoice.customer.name, reference: invoice.reference })}</p><p className={styles.muted}>{word("delivery_local")}</p>
    <div className={styles.footer}><button className={`${primaryButtonClass} ${styles.formSubmit}`} type="submit">{word("save_delivery")}</button></div>
  </form>;
}
