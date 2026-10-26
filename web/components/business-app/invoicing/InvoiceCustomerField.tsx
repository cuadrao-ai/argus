"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AlertCircle, Check, ChevronDown, Info, Plus } from "lucide-react";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { fieldClass, fieldLabelClass, fieldNoteClass, fieldNoteTone } from "@/components/ui/form-field";
import { CustomerMark } from "./CustomerPicker";
import { useInvoiceWords } from "./InvoiceDocument";
import { matchesCustomer, type BusinessCustomer } from "./customer-preview-model";
import styles from "./invoicing-preview.module.css";

export default function InvoiceCustomerField({ customers, selectedId, selectedName, error, onChoose, onAdd }: { customers: BusinessCustomer[]; selectedId: string; selectedName: string; error: string | null; onChoose: (customer: BusinessCustomer) => void; onAdd: (name: string) => void }) {
  const { word } = useInvoiceWords();
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const results = customers.filter(customer => customer.status === "active" && matchesCustomer(customer, query));
  const activeIndex = Math.min(active, results.length);
  useEffect(() => {
    if (open) document.getElementById(`${id}-${activeIndex}`)?.scrollIntoView?.({ block: "nearest" });
  }, [id, open, activeIndex, query]);
  const close = () => setOpen(false);
  useOverlayLayer({ isOpen: open, overlayId: id, containerRef: root, onEscape: close, onOutsidePointerDown: close });
  const show = () => { setQuery(""); setActive(0); setOpen(true); };
  const choose = (index: number) => {
    if (index === results.length) onAdd(query.trim());
    else onChoose(results[index]);
    close();
    input.current?.focus();
  };
  return <div ref={root} className={styles.customerField} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) close(); }}>
    <label className={fieldLabelClass} htmlFor="invoice-customer-search">{word("customer_name")}</label>
    <div className={styles.customerFieldInput}>
      <input ref={input} id="invoice-customer-search" role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={open ? id : undefined} aria-activedescendant={open ? `${id}-${activeIndex}` : undefined} aria-describedby={`${id}-hint${error ? ` ${id}-error` : ""}`} aria-invalid={!!error} className={fieldClass} placeholder={word("placeholder_name")} autoComplete="off" maxLength={120} value={open ? query : selectedName} onClick={() => { if (!open) show(); }} onChange={event => { setQuery(event.target.value); setActive(0); setOpen(true); }} onKeyDown={event => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); if (!open) show(); else setActive(current => (current + (event.key === "ArrowDown" ? 1 : results.length)) % (results.length + 1)); }
        if (event.key === "Enter") { event.preventDefault(); if (open) choose(activeIndex); else show(); }
      }} />
      <button type="button" className={styles.customerFieldChevron} aria-label={word("choose_customer")} aria-expanded={open} onClick={() => { if (open) close(); else show(); input.current?.focus(); }}><ChevronDown size={17} aria-hidden="true" /></button>
      {open ? <div id={id} role="listbox" aria-label={word("choose_customer")} className={styles.customerFieldMenu}>
        {results.map((customer, index) => <button type="button" role="option" id={`${id}-${index}`} aria-selected={customer.id === selectedId} tabIndex={-1} data-active={activeIndex === index} key={customer.id} className={styles.option} onMouseDown={event => event.preventDefault()} onClick={() => choose(index)}><CustomerMark name={customer.name} /><span className={styles.customerIdentity}>{customer.name}<small>{customer.email || customer.taxId}</small></span>{customer.id === selectedId ? <Check size={16} aria-hidden="true" /> : null}</button>)}
        {!results.length ? <p className={styles.muted}>{word("customers_no_matches")}</p> : null}
        <button type="button" role="option" id={`${id}-${results.length}`} aria-selected={false} tabIndex={-1} data-active={activeIndex === results.length} className={styles.option} onMouseDown={event => event.preventDefault()} onClick={() => choose(results.length)}><Plus size={17} aria-hidden="true" /><span>{word("customers_add")}{query.trim() ? ` · ${query.trim()}` : ""}</span></button>
      </div> : null}
    </div>
    <p id={`${id}-hint`} className={`${fieldNoteClass} ${fieldNoteTone.hint}`}><Info size={15} className="mt-1 shrink-0" aria-hidden="true" />{word("customers_autofill_hint")}</p>
    {error ? <p id={`${id}-error`} role="alert" className={`${fieldNoteClass} ${fieldNoteTone.error}`}><AlertCircle size={15} className="mt-1 shrink-0" aria-hidden="true" />{error}</p> : null}
  </div>;
}
