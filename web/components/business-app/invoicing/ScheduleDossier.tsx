"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronLeft, Lock } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { FormField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import CustomerPicker from "./CustomerPicker";
import CustomerForm from "./CustomerForm";
import { customerSnapshot, type BusinessCustomer } from "./customer-preview-model";
import { InvoiceDate, InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import InvoiceDateField from "./InvoiceDateField";
import { hundredths, invoiceAmounts, validDraft, type InvoicePreview } from "./invoice-preview-model";
import { occurrenceDate, scheduleErrors, type InvoiceSchedule } from "./schedule-preview-model";
import styles from "./invoicing-preview.module.css";
import controlStyles from "../transacciones/records-filter-preview.module.css";

export default function ScheduleDossier({ initial, isNew, customers, invoices, onSave, onClose, onAddCustomer }: { initial: InvoiceSchedule; isNew: boolean; customers: BusinessCustomer[]; invoices: InvoicePreview[]; onSave: (schedule: InvoiceSchedule) => void; onClose: () => void; onAddCustomer: (customer: BusinessCustomer) => void }) {
  const { word, t } = useInvoiceWords();
  const [draft, setDraft] = useState(initial);
  const form = useRef<HTMLFormElement>(null);
  const [addingCustomer, setAddingCustomer] = useState<BusinessCustomer | null>(null);
  const [customerDirty, setCustomerDirty] = useState(false);
  const [leaving, setLeaving] = useState<"customer" | "schedule" | null>(null);
  const errors = scheduleErrors(draft, customers);
  const rules: FieldRules<string> = Object.fromEntries(["name", "customer", "template", "anchorDate"].map(key => [key, () => errors[key] ? word(`error_${errors[key]}`) : null]));
  const checks = useFieldChecks(rules, { name: draft.name, customer: draft.customerId, template: draft.template.id, anchorDate: draft.anchorDate });
  useEffect(() => { if (checks.attempt) form.current?.querySelector<HTMLElement>('[aria-invalid="true"], [data-field-error]' )?.focus(); }, [checks.attempt]);
  const dirty = customerDirty || JSON.stringify(draft) !== JSON.stringify(initial);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const selected = customers.find(customer => customer.id === draft.customerId);
  const sources = invoices.filter(invoice => invoice.issuance === "draft" && validDraft(invoice));
  const amount = invoiceAmounts(draft.template);
  const chooseCustomer = (customer: BusinessCustomer) => setDraft(current => ({ ...current, customerId: customer.id, template: { ...current.template, customer: customerSnapshot(customer) } }));
  const backFromCustomer = () => { if (customerDirty) setLeaving("customer"); else setAddingCustomer(null); };
  const close = () => addingCustomer ? backFromCustomer() : dirty ? setLeaving("schedule") : onClose();
  return <AdaptivePanel title={word(addingCustomer ? "customers_add" : isNew ? "schedules_create" : "schedules_edit")} summary={isNew ? undefined : initial.name} snaps={["full"]} initialSnap="full" closeLabel={t("common.close")} onClose={close}>
    <div className={styles.panelBody} data-testid="schedule-dossier">
      {leaving ? <div className={styles.notice}><p>{word(leaving === "customer" ? "customers_discard_help" : "schedules_discard_help")}</p><div className={styles.actions}><button className={quietButtonClass} onClick={() => setLeaving(null)}>{word("customers_keep_editing")}</button><button className={quietButtonClass} onClick={() => { if (leaving === "customer") { setAddingCustomer(null); setCustomerDirty(false); setLeaving(null); } else onClose(); }}>{word("discard")}</button></div></div> : null}
      {addingCustomer ? <><button className={quietButtonClass} onClick={backFromCustomer}><ChevronLeft size={17} />{word("schedules_back")}</button><CustomerForm initial={addingCustomer} onDirty={setCustomerDirty} onSave={customer => { onAddCustomer(customer); chooseCustomer(customer); setAddingCustomer(null); setCustomerDirty(false); setLeaving(null); }} /></> : <form ref={form} className={styles.formCard} noValidate onSubmit={event => { event.preventDefault(); if (checks.submit()) onSave(draft); }}>
        {!sources.length && !validDraft(draft.template) ? <div className={styles.notice}><p>{word("schedules_need_template")}</p><button type="button" className={quietButtonClass} onClick={close}>{word("schedules_return")}</button></div> : null}
        <FormField id="schedule-name" label={word("schedules_name")} placeholder={word("schedules_name_placeholder")} value={draft.name} maxLength={120} required error={checks.errorOf("name")} onBlur={() => checks.blur("name")} onChange={event => setDraft(current => ({ ...current, name: event.target.value }))} />
        <div className={styles.sectionHeading}><h3>{word("customer")}</h3><CustomerPicker customers={customers} selectedId={draft.customerId} onChoose={chooseCustomer} onAdd={() => setAddingCustomer({ id: crypto.randomUUID(), name: "", email: "", address: "", taxId: "", status: "active" })} /></div>
        <p>{selected?.name || word("choose_customer")}</p>
        {selected?.status === "archived" ? <p className={styles.notice}>{word("schedules_archived_customer")}</p> : null}
        {checks.errorOf("customer") ? <p tabIndex={-1} data-field-error className={styles.error} role="alert">{checks.errorOf("customer")}</p> : null}
        <div><h3>{word("schedules_template")}</h3><p className={styles.muted}>{word("schedules_template_help")}</p></div>
        <ToolbarPicker label={word("schedules_template")} value={draft.template.reference || word("schedules_choose_template")} wide>{closePicker => <>{sources.map(invoice => <button type="button" key={invoice.id} className={styles.option} onClick={() => { setDraft(current => ({ ...current, template: { ...invoice, items: invoice.items.map(item => ({ ...item })), customer: selected ? customerSnapshot(selected) : invoice.customer }, customerId: selected?.id ?? invoice.customer.id })); closePicker(); }}><span>{invoice.reference}<small className={styles.muted}> · {invoice.customer.name} · {invoice.currency}</small></span>{draft.template.id === invoice.id ? <Check size={16} /> : null}</button>)}{!sources.length ? <p className={styles.muted}>{word("schedules_need_template")}</p> : null}</>}</ToolbarPicker>
        {draft.template.items.some(item => item.description) ? <div className={styles.scheduleTemplate}><ul>{draft.template.items.map(item => <li key={item.id}>{item.description || "-"}<span>{item.quantity} × <InvoiceMoney amount={hundredths(item.price) ?? 0} currency={draft.template.currency} /></span></li>)}</ul>{amount ? <strong><InvoiceMoney amount={amount.total} currency={draft.template.currency} /></strong> : null}</div> : null}
        {checks.errorOf("template") ? <p tabIndex={-1} data-field-error className={styles.error} role="alert">{checks.errorOf("template")}</p> : null}
        <InvoiceDateField id="schedule-start" label={word("schedules_start")} value={draft.anchorDate} error={checks.errorOf("anchorDate")} onBlur={() => checks.blur("anchorDate")} onChange={anchorDate => setDraft(current => ({ ...current, anchorDate }))} />
        <h3>{word("schedules_frequency")}</h3><SegmentedControl label={word("schedules_frequency")} value={draft.frequency} onChange={frequency => setDraft(current => ({ ...current, frequency }))} fill segments={(["weekly", "monthly", "yearly"] as const).map(key => ({ key, label: word(`schedules_${key}`) }))} />
        {occurrenceDate(draft.anchorDate, draft.frequency, 0) ? <div><p className={styles.muted}>{word("schedules_dates_preview")}</p><ol className={styles.scheduleDates}>{[0, 1, 2].map(index => <li key={index}><InvoiceDate date={occurrenceDate(draft.anchorDate, draft.frequency, index)} /></li>)}</ol><p className={styles.muted}>{word("schedules_anchor_help")}</p></div> : null}
        <fieldset className={styles.scheduleModes}><legend>{word("schedules_action")}</legend><label className={controlStyles.choice}><input type="radio" name="schedule-mode" checked readOnly /><span>{word("schedules_mode_draft")}<small>{word("schedules_mode_draft_help")}</small></span></label><label className={controlStyles.choice}><input type="radio" name="schedule-mode" disabled /><span>{word("schedules_mode_auto")}<small>{word("schedules_mode_auto_help")}</small></span><Lock size={16} aria-hidden="true" /></label></fieldset>
        <footer className={styles.footer}><p className={styles.muted}>{word("schedules_local")}</p><button type="submit" className={`${primaryButtonClass} ${styles.formSubmit}`}>{word("schedules_save")}</button></footer>
      </form>}
    </div>
  </AdaptivePanel>;
}
