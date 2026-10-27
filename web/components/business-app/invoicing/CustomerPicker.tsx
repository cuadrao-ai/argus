"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Plus, Search } from "lucide-react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import { IdentityMark } from "@/components/identity/IdentityMark";
import { useInvoiceWords } from "./InvoiceDocument";
import { matchesCustomer, type BusinessCustomer } from "./customer-preview-model";
import styles from "./invoicing-preview.module.css";

export function CustomerMark({ name }: { name: string }) {
  return <IdentityMark name={name} appearance={{ kind: "avatar", mark: "initials", token: "slate" }} size={40} />;
}
export default function CustomerPicker({ customers, selectedId, onChoose, onAdd }: { customers: BusinessCustomer[]; selectedId?: string; onChoose: (customer: BusinessCustomer) => void; onAdd: () => void }) {
  const { word } = useInvoiceWords();
  const [query, setQuery] = useState("");
  const results = customers.filter(customer => customer.status === "active" && matchesCustomer(customer, query));
  return <ToolbarPicker label={word("choose_customer")} value={word("choose_customer")} wide>{close => <div className={styles.customerChoices}>
    <CustomerSearch query={query} onChange={setQuery} />
    <div className={styles.customerOptions}>{results.map(customer => <button type="button" key={customer.id} className={styles.option} onClick={() => { onChoose(customer); setQuery(""); close(); }}><CustomerMark name={customer.name} /><span className={styles.customerIdentity}>{customer.name}<small>{customer.email || customer.taxId}</small></span>{customer.id === selectedId ? <Check size={16} aria-hidden="true" /> : null}</button>)}</div>
    {!results.length ? <p className={styles.muted}>{word("customers_no_matches")}</p> : null}
    <button type="button" className={styles.option} onClick={() => { close(); setQuery(""); onAdd(); }}><Plus size={17} aria-hidden="true" />{word("customers_add")}</button>
  </div>}</ToolbarPicker>;
}

function CustomerSearch({ query, onChange }: { query: string; onChange: (query: string) => void }) {
  const { word } = useInvoiceWords();
  const { isBelowTablet: phone } = useResponsiveLayout();
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (phone) return;
    const frame = requestAnimationFrame(() => input.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [phone]);
  return <label className={styles.search}><Search size={17} aria-hidden="true" /><input ref={input} type="search" value={query} aria-label={word("customers_search")} placeholder={word("customers_search")} onChange={event => onChange(event.target.value)} onKeyDown={event => { if (event.key === "Enter") event.preventDefault(); }} /></label>;
}
