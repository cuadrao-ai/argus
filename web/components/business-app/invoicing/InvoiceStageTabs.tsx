"use client";

import { useEffect, useRef } from "react";
import { useInvoiceWords } from "./InvoiceDocument";
import { matchesInvoice, type InvoiceFilter, type InvoicePreview } from "./invoice-preview-model";
import styles from "./invoicing-preview.module.css";

const STAGES: readonly InvoiceFilter[] = ["all", "draft", "outstanding", "paid", "void"];

export default function InvoiceStageTabs({ value, invoices, onChange }: { value: InvoiceFilter; invoices: InvoicePreview[]; onChange: (value: InvoiceFilter) => void }) {
  const { word } = useInvoiceWords();
  const tabs = useRef<HTMLDivElement>(null);
  useEffect(() => { tabs.current?.querySelector<HTMLButtonElement>(`#invoice-stage-${value}`)?.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }, [value]);
  return <div ref={tabs} className={styles.stageTabs} role="tablist" aria-label={word("views")}>{STAGES.map((stage, index) => <button key={stage} type="button" role="tab" id={`invoice-stage-${stage}`} aria-controls="invoice-stage-results" aria-selected={value === stage} tabIndex={value === stage ? 0 : -1} onClick={() => onChange(stage)} onKeyDown={event => {
    const next = event.key === "Home" ? 0 : event.key === "End" ? STAGES.length - 1 : event.key === "ArrowRight" ? (index + 1) % STAGES.length : event.key === "ArrowLeft" ? (index + STAGES.length - 1) % STAGES.length : null;
    if (next === null) return;
    event.preventDefault();
    onChange(STAGES[next]);
    tabs.current?.querySelector<HTMLButtonElement>(`#invoice-stage-${STAGES[next]}`)?.focus();
  }}>{word(stage)}<span>{invoices.filter(invoice => matchesInvoice(invoice, stage)).length}</span></button>)}</div>;
}
