"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Eye, Plus, Trash2 } from "lucide-react";
import { FormField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { fieldClass, fieldLabelClass } from "@/components/ui/form-field";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import InvoiceDocument, { useInvoiceWords } from "./InvoiceDocument";
import { CURRENCIES, invoiceDraftErrors, validDraft, type InvoiceCustomer, type InvoicePreview } from "./invoice-preview-model";
import styles from "./invoicing-preview.module.css";

export default function InvoiceEditor({ initial, business, customers, onSave, onClose }: { initial: InvoicePreview; business: string; customers: InvoiceCustomer[]; onSave: (invoice: InvoicePreview) => void; onClose: () => void }) {
  const { word, t } = useInvoiceWords();
  const [draft, setDraft] = useState(initial);
  const form = useRef<HTMLFormElement>(null);
  const [preview, setPreview] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const values: Record<string, string> = { ...draft.customer, issuedOn: draft.issuedOn, dueOn: draft.dueOn, items: String(draft.items.length) };
  for (const item of draft.items) for (const key of ["description", "quantity", "price", "tax"] as const) values[`${item.id}-${key}`] = item[key];
  const errors = invoiceDraftErrors(draft);
  const rules: FieldRules<string> = Object.fromEntries(Object.keys(values).map(key => [key, () => errors[key] ? word(`error_${errors[key]}`) : null]));
  const checks = useFieldChecks(rules, values);
  const feedback = (key: string) => ({ id: `invoice-${key}`, error: checks.errorOf(key), onBlur: () => checks.blur(key), reserveMessages: [word(`error_${errors[key] ?? (key === "name" || key.endsWith("description") ? "required" : "date")}`)] });
  useEffect(() => { if (checks.attempt) form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(); }, [checks.attempt]);
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);
  useEffect(() => {
    if (!changed) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changed]);
  const field = (key: "issuedOn" | "dueOn" | "terms" | "notes" | "instructions", value: string) => setDraft(current => ({ ...current, [key]: value }));
  const customer = (key: keyof InvoiceCustomer, value: string) => setDraft(current => ({ ...current, customer: { ...current.customer, [key]: value } }));
  const save = () => { if (checks.submit() && validDraft(draft)) onSave(draft); else setLeaving(false); };
  return <section data-testid="invoice-editor">
    <div className={styles.editorHeading}><button className={quietButtonClass} aria-label={word("back")} onClick={() => changed ? setLeaving(true) : onClose()}><ArrowLeft size={18} /><span className={styles.backLabel}>{word("back")}</span></button><span>{changed ? word("unsaved") : word("state_draft")}</span><button className={secondaryButtonClass} onClick={() => setPreview(true)}><Eye size={17} />{word("preview")}</button></div>
    <div className={styles.editorGrid}>
      <form ref={form} noValidate className={styles.formCard} onSubmit={event => { event.preventDefault(); save(); }}>
        <h2>{word("draft_title")}</h2><p className={styles.muted}>{business} · {draft.reference}</p>
        <div className={styles.sectionHeading}><h3>{word("customer")}</h3><ToolbarPicker label={word("choose_customer")} value={word("choose_customer")}>{close => customers.map(item => <button type="button" className={styles.option} key={item.id} onClick={() => { setDraft(current => ({ ...current, customer: { ...item } })); close(); }}>{item.name}</button>)}</ToolbarPicker></div>
        <div className={styles.fields}>{(["name", "email", "taxId", "address"] as const).map(key => <FormField key={key} {...feedback(key)} reserveMessages={key === "name" || key === "email" ? [word(key === "name" ? "error_required" : "error_email")] : []} label={word(`customer_${key}`)} value={draft.customer[key]} type={key === "email" ? "email" : "text"} required={key === "name"} maxLength={key === "address" ? 240 : key === "email" ? 254 : 120} autoComplete="off" placeholder={word(`placeholder_${key}`)} onChange={event => customer(key, event.target.value)} />)}</div>
        <div className={styles.fields}>{(["issuedOn", "dueOn"] as const).map(key => <FormField key={key} {...feedback(key)} reserveMessages={[word("error_date"), ...(key === "dueOn" ? [word("error_due_date")] : [])]} label={word(key === "issuedOn" ? "issue_date" : "due_date")} value={draft[key]} required placeholder={word("date_placeholder")} maxLength={10} onChange={event => field(key, event.target.value)} />)}</div>
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
        <div className={styles.footer}><button className={`${primaryButtonClass} ${styles.formSubmit}`} type="submit">{word("save_draft")}</button></div>
      </form>
      <aside className={styles.livePreview}><p className={styles.muted}>{word("live_preview")}</p><InvoiceDocument invoice={draft} business={business} /></aside>
    </div>
    {preview ? <AdaptivePanel title={word("customer_preview")} width="record" snaps={["full"]} initialSnap="full" closeLabel={t("common.close")} onClose={() => setPreview(false)}><InvoiceDocument invoice={draft} business={business} /></AdaptivePanel> : null}
    {leaving ? <AdaptivePanel title={word("unsaved")} closeLabel={t("common.close")} onClose={() => setLeaving(false)}><div className={styles.panelBody}><p>{word("leave_note")}</p><button className={primaryButtonClass} onClick={save}>{word("save_draft")}</button><button className={quietButtonClass} onClick={onClose}>{word("discard")}</button></div></AdaptivePanel> : null}
  </section>;
}
