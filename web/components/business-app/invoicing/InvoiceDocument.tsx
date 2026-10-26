"use client";

import { useTranslation } from "react-i18next";
import { formatAmount } from "../business-format";
import { currencySymbol } from "@/lib/money-entry";
import { SavedIdentityMark } from "@/components/identity/IdentityMark";
import { useBusiness } from "../BusinessWorkspace";
import { BusinessMark } from "../BusinessSwitcher";
import { invoiceAmounts, invoiceSettlement, validIsoDate, type InvoicePreview } from "./invoice-preview-model";
import styles from "./invoicing-preview.module.css";

export function useInvoiceWords() {
  const { t, i18n } = useTranslation();
  return { word: (key: string, values?: Record<string, string | number>) => t(`business.invoicing_preview.${key}`, values), t, locale: i18n.language };
}
export function InvoiceMoney({ amount, currency, numberOnly = false }: { amount: number; currency: string; numberOnly?: boolean }) {
  const { locale } = useInvoiceWords();
  return <span className="cuadrao-amount whitespace-nowrap tabular-nums">{numberOnly ? null : `${currencySymbol(currency)} `}{formatAmount((amount / 100).toFixed(2), currency, locale)}</span>;
}
export function InvoiceDate({ date }: { date: string }) {
  const { locale } = useInvoiceWords();
  return <>{validIsoDate(date) ? new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T12:00:00Z`)) : "-"}</>;
}
export default function InvoiceDocument({ invoice, business, activeSection }: { invoice: InvoicePreview; business: string; activeSection?: "customer" | "items" | "terms" | "review" }) {
  const { word } = useInvoiceWords();
  const { chosen } = useBusiness();
  const amount = invoiceSettlement(invoice);
  return <article className={styles.document} data-editing={activeSection === "review" || undefined} data-testid="invoice-customer-document">
    <header className={styles.documentHeader}><div><div className={styles.issuer}><SavedIdentityMark scope={`business:${chosen?.space_id ?? ""}`} name={business} business fallback={<BusinessMark />} /><h2>{business}</h2></div><p>{word("sample_document")}</p></div><div><strong>{word("invoice")}</strong><p>{invoice.reference}</p></div></header>
    <section className={styles.documentFacts}><div data-editing={activeSection === "customer" || undefined}><p>{word("bill_to")}</p><strong>{invoice.customer.name || word("customer_placeholder")}</strong><p>{invoice.customer.email}</p><p>{invoice.customer.address}</p>{invoice.customer.taxId ? <p>{invoice.customer.taxId}</p> : null}</div><dl data-editing={activeSection === "terms" || undefined}><dt>{word("issue_date")}</dt><dd><InvoiceDate date={invoice.issuedOn} /></dd><dt>{word("due_date")}</dt><dd><InvoiceDate date={invoice.dueOn} /></dd><dt>{word("currency")}</dt><dd>{invoice.currency}</dd></dl></section>
    <div className={styles.documentItems} data-editing={activeSection === "items" || undefined}>{invoice.items.map(item => <div key={item.id}><span>{item.description || word("item_placeholder")}<small>{item.quantity || "0"} × {item.price || "0.00"}</small></span><span>{(() => { const line = invoiceAmounts({ items: [item], payments: [] }); return line ? <InvoiceMoney amount={line.total} currency={invoice.currency} /> : "-"; })()}</span></div>)}</div>
    <dl className={styles.documentTotals}>{(["subtotal", ...(amount?.discount ? ["discount" as const] : []), "tax", "total"] as const).map(key => <div key={key}><dt>{word(key === "tax" ? "tax_amount" : key === "total" ? "document_total" : key)}</dt><dd>{amount ? <InvoiceMoney amount={key === "discount" ? -amount[key] : amount[key]} currency={invoice.currency} /> : "-"}</dd></div>)}</dl>
    {invoice.issuance === "issued" && amount ? <dl className={styles.documentTotals}>{amount.credited > 0 ? <div><dt>{word("confirmed_credits")}</dt><dd><InvoiceMoney amount={amount.credited} currency={invoice.currency} /></dd></div> : null}{amount.debited > 0 ? <div><dt>{word("confirmed_debits")}</dt><dd><InvoiceMoney amount={amount.debited} currency={invoice.currency} /></dd></div> : null}<div><dt>{word("collected")}</dt><dd><InvoiceMoney amount={amount.paid} currency={invoice.currency} /></dd></div><div><dt>{word(amount.balance < 0 ? "credit_balance" : "balance")}</dt><dd><InvoiceMoney amount={Math.abs(amount.balance)} currency={invoice.currency} /></dd></div></dl> : null}
    {invoice.instructions ? <section data-editing={activeSection === "terms" || undefined}><h3>{word("instructions")}</h3><p className={styles.multiline}>{invoice.instructions}</p></section> : null}
    {invoice.terms ? <section data-editing={activeSection === "terms" || undefined}><h3>{word("terms")}</h3><p className={styles.multiline}>{invoice.terms}</p></section> : null}
    {invoice.notes ? <section data-editing={activeSection === "items" || undefined}><h3>{word("notes")}</h3><p className={styles.multiline}>{invoice.notes}</p></section> : null}
  </article>;
}

export function printInvoiceDocument(title: string) {
  const source = document.querySelector('[data-testid="invoice-customer-document"]');
  if (!source) return false;
  const popup = window.open("", "_blank", "width=820,height=900");
  if (!popup) return false;
  popup.opener = null;
  popup.document.title = title;
  const style = popup.document.createElement("style");
  style.textContent = "body{font:14px system-ui;color:#172b26;padding:32px}article{max-width:700px;margin:auto}header{display:flex;justify-content:space-between;border-bottom:1px solid #ddd;padding-bottom:24px}section{margin:24px 0}dl div{display:flex;justify-content:space-between;padding:8px 0}small{display:block;color:#56635e}dd{margin:0}p{white-space:pre-wrap}button{display:none}@page{margin:20mm}";
  popup.document.head.append(style);
  popup.document.body.append(source.cloneNode(true));
  popup.print();
  return true;
}
