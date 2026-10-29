"use client";

import { useRef, useState, useEffect } from "react";
import { Plus, Search, SlidersHorizontal } from "lucide-react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import { useLendListSearch, useSearchInBar } from "../foundation/list-search";
import { InvoiceDate, InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import { CustomerMark } from "./CustomerPicker";
import { customerRecentActivity, matchesCustomer, type BusinessCustomer } from "./customer-preview-model";
import { nextCustomerSchedule, nextOccurrence, type InvoiceSchedule } from "./schedule-preview-model";
import type { InvoicePreview } from "./invoice-preview-model";
import WorkspaceEmptyState from "./WorkspaceEmptyState";
import styles from "./invoicing-preview.module.css";
import controlStyles from "../transacciones/records-filter-preview.module.css";

export default function CustomersView({ customers, invoices, schedules, panelOpen, onSelect, onAdd }: { customers: BusinessCustomer[]; invoices: InvoicePreview[]; schedules: InvoiceSchedule[]; panelOpen: boolean; onSelect: (id: string) => void; onAdd: () => void }) {
  const { word, locale } = useInvoiceWords();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<BusinessCustomer["status"]>("active");
  const [showCreated, setShowCreated] = useState(false);
  const search = useRef<HTMLInputElement>(null);
  const searchInBar = useSearchInBar();
  useLendListSearch("customers", searchInBar ? { query, setQuery } : null);
  // With the search in the top bar, ⌘K is the bar's.
  useEffect(() => {
    if (searchInBar) return;
    const focus = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !panelOpen) { event.preventDefault(); event.stopImmediatePropagation(); search.current?.focus(); } };
    window.addEventListener("keydown", focus, true);
    return () => window.removeEventListener("keydown", focus, true);
  }, [panelOpen, searchInBar]);
  const rows = customers.filter(customer => customer.status === status && matchesCustomer(customer, query)).sort((a, b) => a.name.localeCompare(b.name, locale));
  return <div data-testid="customers-view">
    <div className={`${styles.toolbar} ${styles.customerToolbar}`}>
      {searchInBar ? null : <label className={styles.search}><Search size={17} aria-hidden="true" /><input ref={search} type="search" aria-label={word("customers_search")} placeholder={word("customers_search")} value={query} onChange={event => setQuery(event.target.value)} /></label>}
      <SegmentedControl label={word("customers_status")} value={status} onChange={setStatus} segments={(["active", "archived"] as const).map(key => ({ key, label: word(`customers_${key}`), count: customers.filter(customer => customer.status === key).length }))} />
      <button className={`${primaryButtonClass} ${styles.create}`} disabled={panelOpen} onClick={onAdd}><Plus size={18} aria-hidden="true" />{word("customers_add")}</button>
      <ToolbarPicker label={word("settings")} value={word("settings")} icon={<SlidersHorizontal size={16} />} flip>{() => <label className={controlStyles.choice}><input type="checkbox" checked={showCreated} onChange={event => setShowCreated(event.target.checked)} /><span>{word("customers_created")}</span></label>}</ToolbarPicker>
    </div>
    {rows.length ? <div className={styles.tableFrame}>
      <table className={`${styles.table} ${styles.customerTable}`}><thead><tr><th>{word("customer")}</th><th>{word("customers_last_activity")}</th><th>{word("customers_last_invoice")}</th><th>{word("customers_last_payment")}</th><th>{word("schedules_next")}</th>{showCreated ? <th>{word("customers_created")}</th> : null}</tr></thead><tbody>{rows.map(customer => {
        const recent = customerRecentActivity(customer, invoices);
        const next = customer.status === "active" ? nextCustomerSchedule(schedules, customer.id) : undefined;
        return <tr key={customer.id} onClick={() => !panelOpen && onSelect(customer.id)}><td><button className={styles.customerTableIdentity} disabled={panelOpen} onClick={() => onSelect(customer.id)}><CustomerMark name={customer.name} /><span className={styles.customerIdentity}><strong>{customer.name}</strong><small>{customer.email || customer.taxId || word("customers_no_contact")}</small></span></button></td><td>{recent.latest ? <><InvoiceDate date={recent.latest.date} /><small className={styles.cellDetail}>{word(`activity_${recent.latest.kind}`)}</small></> : "-"}</td><td>{recent.lastInvoice ? <><InvoiceDate date={recent.lastInvoice.issuedOn} /><small className={styles.cellDetail}>{recent.lastInvoice.reference}</small></> : "-"}</td><td>{recent.lastPayment ? <><InvoiceDate date={recent.lastPayment.date} /><small className={styles.cellDetail}><InvoiceMoney amount={recent.lastPayment.amount} currency={recent.lastPayment.currency} /></small></> : "-"}</td><td>{next ? <><InvoiceDate date={nextOccurrence(next)} /><small className={styles.cellDetail}>{word("schedules_mode_draft")}</small></> : "-"}</td>{showCreated ? <td>{customer.createdAt ? <InvoiceDate date={customer.createdAt.slice(0, 10)} /> : "-"}</td> : null}</tr>;
      })}</tbody></table>
      <div className={styles.customerPhone}>{rows.map(customer => { const recent = customerRecentActivity(customer, invoices); const next = customer.status === "active" ? nextCustomerSchedule(schedules, customer.id) : undefined; return <button key={customer.id} className={styles.customerRow} disabled={panelOpen} onClick={() => onSelect(customer.id)}><CustomerMark name={customer.name} /><span className={styles.customerIdentity}><strong>{customer.name}</strong><small>{customer.email || customer.taxId || word("customers_no_contact")}</small>{next ? <small>{word("schedules_next")} <InvoiceDate date={nextOccurrence(next)} /></small> : recent.latest ? <small>{word(`activity_${recent.latest.kind}`)} · <InvoiceDate date={recent.latest.date} /></small> : null}{showCreated ? <small>{word("customers_created")} {customer.createdAt ? <InvoiceDate date={customer.createdAt.slice(0, 10)} /> : "-"}</small> : null}</span></button>; })}</div>
    </div> : <WorkspaceEmptyState compact={status === "archived" || !!query} art="customer" title={word(query ? "customers_no_matches" : status === "archived" ? "customers_no_archived" : "customers_empty")} description={word(query ? "no_results_help" : status === "archived" ? "customers_archived_help" : "customers_empty_help")} action={query ? <button className={quietButtonClass} onClick={() => setQuery("")}>{word("clear_search")}</button> : status === "active" ? <button className={primaryButtonClass} onClick={onAdd}><Plus size={18} />{word("customers_add")}</button> : undefined} />}
  </div>;
}
