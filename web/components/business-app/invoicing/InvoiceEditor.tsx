"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, Plus, Trash2 } from "lucide-react";
import { FormField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import InvoiceDateField from "./InvoiceDateField";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { fieldClass, fieldLabelClass } from "@/components/ui/form-field";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import InvoiceDocument, { useInvoiceWords } from "./InvoiceDocument";
import { CURRENCIES, invoiceDraftErrors, validDraft, type InvoiceCustomer, type InvoicePreview } from "./invoice-preview-model";
import CustomerPicker from "./CustomerPicker";
import CustomerForm from "./CustomerForm";
import { customerSnapshot, type BusinessCustomer } from "./customer-preview-model";
import styles from "./invoicing-preview.module.css";

export default function InvoiceEditor({ initial, business, customers, onAddCustomer, onSave, onClose }: { initial: InvoicePreview; business: string; customers: BusinessCustomer[]; onAddCustomer: (customer: BusinessCustomer) => void; onSave: (invoice: InvoicePreview) => void; onClose: () => void }) {
  const { word, t } = useInvoiceWords();
  const [draft, setDraft] = useState(initial);
  const form = useRef<HTMLFormElement>(null);
  const [addingCustomer, setAddingCustomer] = useState<BusinessCustomer | null>(null);
  const [customerDirty, setCustomerDirty] = useState(false);
  const [discardCustomer, setDiscardCustomer] = useState(false);
  const [view, setView] = useState<"edit" | "preview">("edit");
  const [expanded, setExpanded] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const values: Record<string, string> = { ...draft.customer, issuedOn: draft.issuedOn, dueOn: draft.dueOn, items: String(draft.items.length) };
  for (const item of draft.items) for (const key of ["description", "quantity", "price", "tax"] as const) values[`${item.id}-${key}`] = item[key];
  const errors = invoiceDraftErrors(draft);
  const rules: FieldRules<string> = Object.fromEntries(Object.keys(values).map(key => [key, () => errors[key] ? word(`error_${errors[key]}`) : null]));
  const checks = useFieldChecks(rules, values);
  const feedback = (key: string) => ({ id: `invoice-${key}`, error: checks.errorOf(key), onBlur: () => checks.blur(key), reserveMessages: [word(`error_${errors[key] ?? (key === "name" || key.endsWith("description") ? "required" : "date")}`)] });
  useEffect(() => { if (checks.attempt) form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(); }, [checks.attempt]);
  const changed = customerDirty || JSON.stringify(draft) !== JSON.stringify(initial);
  useEffect(() => {
    if (!changed) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changed]);
  const field = (key: "issuedOn" | "dueOn" | "terms" | "notes" | "instructions", value: string) => setDraft(current => ({ ...current, [key]: value }));
  const customer = (key: keyof InvoiceCustomer, value: string) => setDraft(current => ({ ...current, customer: { ...current.customer, [key]: value } }));
  const save = () => { if (checks.submit() && validDraft(draft)) onSave(draft); else { setLeaving(false); setView("edit"); } };
  return <>
  <AdaptivePanel title={word(addingCustomer ? "customers_add" : "draft_title")} summary={`${business} · ${draft.reference}`} width="lg" snaps={["full"]} initialSnap="full" closeLabel={t("common.close")} onClose={() => addingCustomer ? customerDirty ? setDiscardCustomer(true) : setAddingCustomer(null) : changed ? setLeaving(true) : onClose()} expansion={{ expanded, onToggle: () => setExpanded(value => !value), expandLabel: word("expand_editor"), collapseLabel: word("collapse_editor") }}>
  {addingCustomer ? <div className={styles.panelBody}><button className={quietButtonClass} onClick={() => customerDirty ? setDiscardCustomer(true) : setAddingCustomer(null)}><ChevronLeft size={17} />{word("customers_back_draft")}</button>{discardCustomer ? <div className={styles.notice}><p>{word("customers_discard_help")}</p><button className={quietButtonClass} onClick={() => setDiscardCustomer(false)}>{word("customers_keep_editing")}</button><button className={quietButtonClass} onClick={() => { setAddingCustomer(null); setCustomerDirty(false); setDiscardCustomer(false); }}>{word("discard")}</button></div> : null}<CustomerForm initial={addingCustomer} onDirty={setCustomerDirty} onSave={saved => { onAddCustomer(saved); setDraft(current => ({ ...current, customer: customerSnapshot(saved) })); setAddingCustomer(null); setCustomerDirty(false); setDiscardCustomer(false); }} /></div> : null}
  <section hidden={!!addingCustomer} data-testid="invoice-editor" className={styles.editor} data-expanded={expanded} data-view={view}>
    <div className={styles.editorSwitch}><SegmentedControl label={word("editor_view")} value={view} onChange={setView} fill segments={[{ key: "edit", label: word("edit") }, { key: "preview", label: word("preview") }]} /></div>
    <div className={styles.editorGrid}>
      <form ref={form} noValidate className={styles.formCard} onSubmit={event => { event.preventDefault(); save(); }}>
        <p className={styles.muted}>{changed ? word("unsaved") : word("state_draft")}</p>
        <ToolbarPicker label={word("document_type")} value={word(`document_${draft.documentType}`)}>{close => (["E32", "E31"] as const).map(documentType => <button type="button" key={documentType} className={styles.option} onClick={() => { setDraft(current => ({ ...current, documentType })); close(); }}>{word(`document_${documentType}`)}</button>)}</ToolbarPicker>
        <div className={styles.sectionHeading} id="invoice-id"><h3>{word("customer")}</h3><CustomerPicker customers={customers} selectedId={draft.customer.id} onChoose={item => setDraft(current => ({ ...current, customer: customerSnapshot(item) }))} onAdd={() => setAddingCustomer({ id: crypto.randomUUID(), name: "", email: "", address: "", taxId: "", status: "active" })} /></div>
        {checks.errorOf("id") ? <p className={styles.error} role="alert">{checks.errorOf("id")}</p> : null}
        <p className={styles.muted}>{word("customers_invoice_snapshot")}</p>
        <div className={styles.fields}>{(["name", "email", "taxId", "address"] as const).map(key => <FormField key={key} {...feedback(key)} reserveMessages={key === "name" || key === "email" || key === "taxId" && draft.documentType === "E31" ? [word(key === "name" ? "error_required" : key === "email" ? "error_email" : "error_tax_id")] : []} label={word(key === "taxId" && draft.documentType === "E31" ? "customer_taxId_required" : `customer_${key}`)} value={draft.customer[key]} type={key === "email" ? "email" : "text"} required={key === "name" || key === "taxId" && draft.documentType === "E31"} maxLength={key === "address" ? 240 : key === "email" ? 254 : 120} autoComplete="off" placeholder={word(`placeholder_${key}`)} onChange={event => customer(key, event.target.value)} />)}</div>
        <div className={styles.fields}>{(["issuedOn", "dueOn"] as const).map(key => <InvoiceDateField key={key} id={`invoice-${key}`} label={word(key === "issuedOn" ? "issue_date" : "due_date")} value={draft[key]} error={checks.errorOf(key)} onBlur={() => checks.blur(key)} onChange={value => field(key, value)} />)}</div>
        <ToolbarPicker label={word("currency")} value={draft.currency}>{close => CURRENCIES.map(currency => <button key={currency} type="button" className={styles.option} onClick={() => { setDraft(current => ({ ...current, currency })); close(); }}>{currency}</button>)}</ToolbarPicker>
        <h3>{word("items")}</h3>
        {draft.items.map((item, index) => <fieldset className={styles.item} key={item.id}><legend className="sr-only">{word("item_number", { count: index + 1 })}</legend>
          <div className={styles.itemDescription}><FormField {...feedback(`${item.id}-description`)} label={word("description")} required maxLength={160} value={item.description} placeholder={word("item_placeholder")} onChange={event => setDraft(current => ({ ...current, items: current.items.map(row => row.id === item.id ? { ...row, description: event.target.value } : row) }))} /></div>
          {(["quantity", "price", "tax"] as const).map(key => <FormField key={key} {...feedback(`${item.id}-${key}`)} reserveMessages={[word(`error_${key}`)]} label={word(key)} required inputMode="decimal" maxLength={10} value={item[key]} aria-label={`${word(key)} ${index + 1}`} onChange={event => setDraft(current => ({ ...current, items: current.items.map(row => row.id === item.id ? { ...row, [key]: event.target.value } : row) }))} />)}
          <button type="button" className={styles.iconButton} disabled={draft.items.length === 1} aria-label={word("remove_item", { count: index + 1 })} onClick={() => setDraft(current => ({ ...current, items: current.items.filter(row => row.id !== item.id) }))}><Trash2 size={17} /></button>
        </fieldset>)}
        <button type="button" className={quietButtonClass} disabled={draft.items.length >= 50} onClick={() => setDraft(current => ({ ...current, items: [...current.items, { id: crypto.randomUUID(), description: "", quantity: "1", price: "", tax: "0" }] }))}><Plus size={17} />{word("add_item")}</button>
        <p className={styles.muted}>{word("tax_note")}</p>
        {(["terms", "notes", "instructions"] as const).map(key => <label className={fieldLabelClass} key={key}>{word(key)}<textarea rows={2} className={fieldClass} maxLength={500} value={draft[key]} placeholder={word(`placeholder_${key}`)} onChange={event => field(key, event.target.value)} /><span className={styles.counter}>{draft[key].length}/500</span></label>)}
        {checks.summary.length ? <ul className={styles.error}>{checks.summary.map(key => <li key={key}><a href={`#invoice-${key}`}>{checks.errorOf(key)}</a></li>)}</ul> : null}
        <div className={styles.footer}><p className={styles.muted}>{word("save_local")}</p><button className={`${primaryButtonClass} ${styles.formSubmit}`} type="submit">{word("save_draft")}</button></div>
      </form>
      <aside className={styles.livePreview}><p className={styles.muted}>{word("live_preview")}</p><InvoiceDocument invoice={draft} business={business} /></aside>
    </div>
  </section>
  </AdaptivePanel>
    {leaving ? <AdaptivePanel title={word("unsaved")} closeLabel={t("common.close")} onClose={() => setLeaving(false)}><div className={styles.panelBody}><p>{word("leave_note")}</p><button className={primaryButtonClass} onClick={save}>{word("save_draft")}</button><button className={quietButtonClass} onClick={onClose}>{word("discard")}</button></div></AdaptivePanel> : null}
  </>;
}
