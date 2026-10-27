"use client";

import { InvoiceDate, InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import { invoiceAmounts, invoiceEmailDraft, type InvoicePreview } from "./invoice-preview-model";
import styles from "./invoicing-preview.module.css";

export default function InvoiceEmailPreview({ invoice, business }: { invoice: InvoicePreview; business: string }) {
  const { word } = useInvoiceWords();
  const email = invoiceEmailDraft(invoice);
  const amount = invoiceAmounts(invoice);
  return <article className={styles.emailPreview} data-testid="invoice-email-preview">
    <dl className={styles.emailHeaders}><dt>{word("email_to")}</dt><dd>{email.to || word("placeholder_email")}</dd>{email.cc ? <><dt>{word("email_cc_short")}</dt><dd>{email.cc}</dd></> : null}<dt>{word("email_subject")}</dt><dd>{word("email_subject_value", { business, reference: invoice.reference })}</dd></dl>
    <div className={styles.emailBody}>
      <p className={styles.muted}>{business}</p><h3>{word("invoice")} {invoice.reference}</h3>
      <strong className={styles.emailAmount}>{amount ? <InvoiceMoney amount={amount.total} currency={invoice.currency} /> : "-"}</strong>
      <p className={styles.muted}>{word("due_date")} · <InvoiceDate date={invoice.dueOn} /></p>
      <p>{word("email_greeting", { name: invoice.customer.name || word("customer_placeholder") })}</p>
      <p className={styles.multiline}>{email.message || word("email_message_placeholder")}</p>
      <div className={styles.emailAttachment}><span>{word("invoice")} {invoice.reference}</span><span>PDF</span></div>
    </div>
  </article>;
}
