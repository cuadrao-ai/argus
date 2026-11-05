"use client";

import { useEffect, useState } from "react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { quietButtonClass } from "../business-ui";
import { InvoiceDate, InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import { CustomerMark } from "./CustomerPicker";
import CustomerForm from "./CustomerForm";
import { customerActivity, type BusinessCustomer, type CustomerCommand } from "./customer-preview-model";
import { invoiceState, type InvoicePreview } from "./invoice-preview-model";
import { nextCustomerSchedule, nextOccurrence, type InvoiceSchedule } from "./schedule-preview-model";
import styles from "./invoicing-preview.module.css";

export default function CustomerDossier({ customer, isNew, invoices, schedules, onSchedule, onClose, onSave, onStatus, onInvoice }: { customer: BusinessCustomer; isNew: boolean; invoices: InvoicePreview[]; schedules: InvoiceSchedule[]; onSchedule: (id: string) => void; onClose: () => void; onSave: (customer: BusinessCustomer) => void; onStatus: (command: CustomerCommand) => void; onInvoice: (id: string) => void }) {
  const { word, t } = useInvoiceWords();
  const [view, setView] = useState<"details" | "edit" | "archive">(isNew ? "edit" : "details");
  const [dirty, setDirty] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const activity = customerActivity(invoices, customer.id);
  const nextSchedule = customer.status === "active" ? nextCustomerSchedule(schedules, customer.id) : undefined;
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const close = () => dirty ? setLeaving(true) : onClose();
  return <AdaptivePanel title={isNew ? word("customers_add") : customer.name} summary={word(`customers_${customer.status}`)} snaps={["full"]} initialSnap="full" closeLabel={t("common.close")} onClose={close}>
    <div className={styles.panelBody} data-testid="customer-dossier">
      <div className={styles.customerHeader}><CustomerMark name={customer.name} /><div><h3>{word("customers_details")}</h3><p className={styles.muted}>{word("customers_snapshot_help")}</p></div></div>
      {leaving ? <div className={styles.notice}><p>{word("customers_discard_help")}</p><div className={styles.actions}><button className={quietButtonClass} onClick={() => setLeaving(false)}>{word("customers_keep_editing")}</button><button className={quietButtonClass} onClick={onClose}>{word("discard")}</button></div></div> : null}
      {view === "edit" ? <CustomerForm initial={customer} onDirty={setDirty} onSave={saved => { onSave(saved); setDirty(false); setLeaving(false); setView("details"); }} /> : <>
        <dl className={`${styles.facts} ${styles.customerFacts}`}>{(["email", "taxId", "address"] as const).map(key => <div key={key}><dt>{word(`customer_${key}`)}</dt><dd>{customer[key] || "-"}</dd></div>)}</dl>
        <div className={styles.actions}><button className={quietButtonClass} onClick={() => setView("edit")}>{word("customers_edit")}</button>{customer.status === "archived" ? <button className={quietButtonClass} onClick={() => onStatus({ type: "status", id: customer.id, status: "active" })}>{word("customers_restore")}</button> : <button className={quietButtonClass} onClick={() => setView(view === "archive" ? "details" : "archive")}>{word("customers_archive")}</button>}</div>
        {view === "archive" ? <div className={styles.notice}><p>{word("customers_archive_help")}</p><button className={quietButtonClass} onClick={() => { onStatus({ type: "status", id: customer.id, status: "archived" }); setView("details"); }}>{word("customers_archive_confirm")}</button></div> : null}
        <section className={styles.customerSection}><h3>{word("customers_balance")}</h3><p className={styles.muted}>{word("customers_issued_only")}</p>{activity.totals.length ? activity.totals.map(group => <div key={group.currency}><h4>{group.currency}</h4><dl className={styles.facts}><div><dt>{word("adjusted_total")}</dt><dd><InvoiceMoney amount={group.total} currency={group.currency} /></dd></div><div><dt>{word("collected")}</dt><dd><InvoiceMoney amount={group.paid} currency={group.currency} /></dd></div><div><dt>{word(group.balance < 0 ? "credit_balance" : "balance")}</dt><dd><InvoiceMoney amount={Math.abs(group.balance)} currency={group.currency} /></dd></div></dl></div>) : <p className={styles.muted}>{word("customers_no_issued")}</p>}</section>
        <section className={styles.customerSection}><h3>{word("customers_invoices")}</h3>{activity.invoices.length ? activity.invoices.map(invoice => <button className={styles.customerLinked} key={invoice.id} onClick={() => onInvoice(invoice.id)}><span>{invoice.reference}<small><InvoiceDate date={invoice.issuedOn} /></small></span><span className={styles.badge} data-state={invoiceState(invoice)}>{word(`state_${invoiceState(invoice)}`)}</span></button>) : <p className={styles.muted}>{word("customers_no_invoices")}</p>}</section>
        <section className={styles.customerSection}><h3>{word("customers_payments")}</h3>{activity.payments.length ? <ul className={styles.paymentList}>{activity.payments.map(payment => <li key={`${payment.invoiceId}:${payment.id}`}><button className={styles.rowLink} onClick={() => onInvoice(payment.invoiceId)}>{payment.invoiceReference}<small><InvoiceDate date={payment.date} /> · {word(`method_${payment.method}`)}{payment.reference ? ` · ${payment.reference}` : ""}</small></button><InvoiceMoney amount={payment.amount} currency={payment.currency} /></li>)}</ul> : <p className={styles.muted}>{word("customers_no_payments")}</p>}</section>
        <section className={styles.customerSection}><h3>{word("schedules_next")}</h3>{nextSchedule ? <button className={styles.customerLinked} onClick={() => onSchedule(nextSchedule.id)}><span>{nextSchedule.name}<small>{word("schedules_mode_draft")}</small></span><InvoiceDate date={nextOccurrence(nextSchedule)} /></button> : <p className={styles.muted}>{word("schedules_none_customer")}</p>}</section>
      </>}
    </div>
  </AdaptivePanel>;
}
