"use client";

import { useRef, useState, useEffect } from "react";
import { Plus, Search } from "lucide-react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { primaryButtonClass } from "../business-ui";
import { useInvoiceWords } from "./InvoiceDocument";
import { CustomerMark } from "./CustomerPicker";
import { matchesCustomer, type BusinessCustomer } from "./customer-preview-model";
import styles from "./invoicing-preview.module.css";

export default function CustomersView({ customers, panelOpen, onSelect, onAdd }: { customers: BusinessCustomer[]; panelOpen: boolean; onSelect: (id: string) => void; onAdd: () => void }) {
  const { word, locale } = useInvoiceWords();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<BusinessCustomer["status"]>("active");
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const focus = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !panelOpen) { event.preventDefault(); event.stopImmediatePropagation(); search.current?.focus(); } };
    window.addEventListener("keydown", focus, true);
    return () => window.removeEventListener("keydown", focus, true);
  }, [panelOpen]);
  const rows = customers.filter(customer => customer.status === status && matchesCustomer(customer, query)).sort((a, b) => a.name.localeCompare(b.name, locale));
  return <div data-testid="customers-view">
    <div className={`${styles.toolbar} ${styles.customerToolbar}`}><label className={styles.search}><Search size={17} aria-hidden="true" /><input ref={search} type="search" aria-label={word("customers_search")} placeholder={word("customers_search")} value={query} onChange={event => setQuery(event.target.value)} /></label><SegmentedControl label={word("customers_status")} value={status} onChange={setStatus} segments={(["active", "archived"] as const).map(key => ({ key, label: word(`customers_${key}`), count: customers.filter(customer => customer.status === key).length }))} /><button className={`${primaryButtonClass} ${styles.create}`} disabled={panelOpen} onClick={onAdd}><Plus size={18} aria-hidden="true" />{word("customers_add")}</button></div>
    <div className={styles.customerList}>{rows.map(customer => <button key={customer.id} className={styles.customerRow} disabled={panelOpen} onClick={() => onSelect(customer.id)}><CustomerMark name={customer.name} /><span className={styles.customerIdentity}><strong>{customer.name}</strong><small>{customer.email || customer.taxId || word("customers_no_contact")}</small></span><span className={styles.customerTax}>{customer.taxId}</span></button>)}</div>
    {!rows.length ? <div className={styles.empty}><h3>{word(query ? "customers_no_matches" : status === "archived" ? "customers_no_archived" : "customers_empty")}</h3><p className={styles.muted}>{word(status === "archived" ? "customers_archived_help" : "customers_empty_help")}</p></div> : null}
  </div>;
}
