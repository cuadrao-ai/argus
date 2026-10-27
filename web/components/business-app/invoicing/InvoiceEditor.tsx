"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Plus, Trash2 } from "lucide-react";
import { FormField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import InvoiceDateField from "./InvoiceDateField";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { fieldClass, fieldLabelClass } from "@/components/ui/form-field";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import InvoiceDocument, { InvoiceDate, InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import InvoiceEmailPreview from "./InvoiceEmailPreview";
import { CURRENCIES, hundredths, invoiceAmounts, invoiceLineAmounts, invoiceEmailDraft, invoiceEmailErrors, invoiceDraftErrors, validDraft, type InvoiceCustomer, type InvoiceItem, type InvoicePreview } from "./invoice-preview-model";
import InvoiceCustomerField from "./InvoiceCustomerField";
import { customerSnapshot, type BusinessCustomer } from "./customer-preview-model";
import { CUSTOMER_FIELD_LIMITS, formatCustomerTaxId } from "./customer-validation";
import styles from "./invoicing-preview.module.css";

const STEPS = ["customer", "items", "terms", "review"] as const;
type EditorStep = typeof STEPS[number];
const stepForField = (key: string): EditorStep => ["id", "name", "email", "taxId", "address"].includes(key) ? "customer" : ["issuedOn", "dueOn"].includes(key) ? "terms" : "items";

export default function InvoiceEditor({ initial, business, customers, onAddCustomer, onSave, onClose }: { initial: InvoicePreview; business: string; customers: BusinessCustomer[]; onAddCustomer: (customer: BusinessCustomer) => void; onSave: (invoice: InvoicePreview) => void; onClose: () => void }) {
  const { word, t } = useInvoiceWords();
  const [draft, setDraft] = useState(initial);
  const [activeItemId, setActiveItemId] = useState(initial.items[0]?.id ?? "");
  const [checkedItems, setCheckedItems] = useState<ReadonlySet<string>>(() => new Set());
  const [itemFocus, setItemFocus] = useState<{ id: string; invalid: boolean } | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const [addingCustomer, setAddingCustomer] = useState(false);
  const [view, setView] = useState<"edit" | "preview">("edit");
  const [reviewView, setReviewView] = useState<"invoice" | "email">("invoice");
  const [expanded, setExpanded] = useState(true);
  const [leaving, setLeaving] = useState(false);
  const [step, setStep] = useState<EditorStep>("customer");
  const [attempted, setAttempted] = useState<ReadonlySet<EditorStep>>(() => new Set());
  const [validationAttempt, setValidationAttempt] = useState(0);
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const values: Record<string, string> = { ...draft.customer, issuedOn: draft.issuedOn, dueOn: draft.dueOn, items: String(draft.items.length) };
  for (const item of draft.items) for (const key of ["description", "quantity", "price", "tax", "discount"] as const) values[`${item.id}-${key}`] = item[key] ?? "";
  const errors = invoiceDraftErrors(draft);
  const rules: FieldRules<string> = Object.fromEntries(Object.keys(values).map(key => [key, () => errors[key] ? word(`error_${errors[key]}`) : null]));
  const checks = useFieldChecks(rules, values);
  const errorOf = (key: string) => checks.errorOf(key) || ((attempted.has(stepForField(key)) || draft.items.some(item => checkedItems.has(item.id) && key.startsWith(`${item.id}-`))) && errors[key] ? word(`error_${errors[key]}`) : null);
  const feedback = (key: string) => ({ id: `invoice-${key}`, error: errorOf(key), onBlur: () => checks.blur(key), reserveMessages: [word(`error_${errors[key] ?? (key === "name" || key.endsWith("description") ? "required" : "date")}`)] });
  const goTo = (next: EditorStep) => { setStep(next); setView("edit"); };
  useEffect(() => { stepHeading.current?.focus(); }, [step]);
  useEffect(() => { if (validationAttempt) (form.current?.querySelector<HTMLElement>('[aria-invalid="true"]') ?? stepHeading.current)?.focus(); }, [validationAttempt]);
  useEffect(() => {
    if (!itemFocus || step !== "items") return;
    const item = document.getElementById(`invoice-item-${itemFocus.id}`);
    const control = itemFocus.invalid ? item?.querySelector<HTMLElement>('[aria-invalid="true"]') : document.getElementById(`invoice-${itemFocus.id}-description`);
    control?.focus();
  }, [itemFocus, step]);
  const showErrors = (target: EditorStep) => {
    if (target === "items") {
      const invalid = draft.items.find(item => Object.keys(errors).some(key => key.startsWith(`${item.id}-`)));
      if (invalid) { setActiveItemId(invalid.id); setItemFocus({ id: invalid.id, invalid: true }); }
    }
    goTo(target); setAttempted(current => new Set(current).add(target)); setValidationAttempt(current => current + 1); };
  const saveNewCustomer = () => {
    if (!addingCustomer) return;
    onAddCustomer({ ...draft.customer, status: "active" });
    setAddingCustomer(false);
  };
  const next = () => {
    if (step === "terms" && Object.keys(errors).some(key => stepForField(key) === "customer")) { showErrors("customer"); return; }
    if (Object.keys(errors).some(key => stepForField(key) === step)) { showErrors(step); return; }
    if (step === "customer") saveNewCustomer();
    goTo(STEPS[Math.min(STEPS.indexOf(step) + 1, STEPS.length - 1)]);
  };
  const email = invoiceEmailDraft(draft);
  const emailErrors = invoiceEmailErrors(email);
  const emailChecks = useFieldChecks<keyof typeof email>({
    to: () => emailErrors.to ? word("error_email") : null,
    cc: () => emailErrors.cc ? word("error_email_cc") : null,
    message: () => emailErrors.message ? word("error_email_message") : null,
  }, email);
  const updateEmail = (key: keyof typeof email, value: string) => setDraft(current => ({ ...current, emailDraft: { ...invoiceEmailDraft(current), [key]: value } }));
  const prepareEmail = () => {
    setReviewView("email");
    if (!emailChecks.submit()) { requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()); return; }
    if (validDraft(draft)) onSave({ ...draft, emailDraft: email });
  };
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);
  useEffect(() => {
    if (!changed) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changed]);
  const field = (key: "issuedOn" | "dueOn" | "terms" | "notes" | "instructions", value: string) => setDraft(current => ({ ...current, [key]: value }));
  const customer = (key: keyof InvoiceCustomer, value: string) => setDraft(current => ({ ...current, customer: { ...current.customer, [key]: value } }));
  const updateItem = (id: string, key: keyof InvoiceItem, value: string) => setDraft(current => ({ ...current, items: current.items.map(item => item.id === id ? { ...item, [key]: value } : item) }));
  const addItem = () => {
    if (draft.items.length >= 50) return;
    if (Object.keys(errors).some(key => key.startsWith(`${activeItemId}-`))) {
      setCheckedItems(current => new Set(current).add(activeItemId));
      setItemFocus({ id: activeItemId, invalid: true });
      return;
    }
    const id = crypto.randomUUID();
    setDraft(current => ({ ...current, items: [...current.items, { id, description: "", quantity: "1", price: "", tax: "0" }] }));
    setActiveItemId(id);
    setItemFocus({ id, invalid: false });
  };
  const removeItem = (id: string) => {
    if (draft.items.length === 1) return;
    const index = draft.items.findIndex(item => item.id === id);
    const remaining = draft.items.filter(item => item.id !== id);
    setDraft(current => ({ ...current, items: current.items.filter(item => item.id !== id) }));
    if (activeItemId === id) {
      const next = remaining[Math.min(index, remaining.length - 1)];
      setActiveItemId(next.id);
      setItemFocus({ id: next.id, invalid: false });
    }
  };
  const numberField = (item: InvoiceItem, index: number, key: "quantity" | "price" | "tax" | "discount") => {
    const value = item[key] ?? "";
    const fieldKey = `${item.id}-${key}`;
    const money = key === "price" || key === "discount";
    return <FormField {...feedback(fieldKey)} reserveMessages={[]} label={word(key === "discount" ? "item_discount" : key, { currency: draft.currency })} required={key !== "discount"} inputMode="decimal" autoComplete="off" maxLength={key === "quantity" ? 7 : key === "tax" ? 6 : 10} value={value} placeholder={word(money ? "placeholder_discount" : key === "quantity" ? "placeholder_quantity" : "placeholder_tax")} aria-label={`${word(key === "discount" ? "item_discount" : key, { currency: draft.currency })} ${index + 1}`} onChange={event => updateItem(item.id, key, event.target.value)} onPaste={event => {
      event.preventDefault();
      const input = event.currentTarget;
      updateItem(item.id, key, value.slice(0, input.selectionStart ?? 0) + event.clipboardData.getData("text") + value.slice(input.selectionEnd ?? value.length));
    }} onBlur={() => {
      checks.blur(fieldKey);
      const parsed = hundredths(value);
      if (value && parsed !== null && !errors[fieldKey]) updateItem(item.id, key, money ? `${Math.floor(parsed / 100)}.${String(parsed % 100).padStart(2, "0")}` : value.trim().replace(",", "."));
    }} />;
  };
  const save = () => {
    if (validDraft(draft) && !Object.keys(errors).length) { saveNewCustomer(); onSave(draft); return; }
    setLeaving(false);
    showErrors(STEPS.find(candidate => Object.keys(errors).some(key => stepForField(key) === candidate)) ?? "customer");
  };
  return <>
  <AdaptivePanel title={word("draft_title")} summary={`${business} · ${draft.reference}`} width="lg" snaps={["full"]} initialSnap="full" closeLabel={t("common.close")} onClose={() => changed ? setLeaving(true) : onClose()} expansion={{ expanded, onToggle: () => setExpanded(value => !value), expandLabel: word("expand_editor"), collapseLabel: word("collapse_editor") }}>
  <section data-testid="invoice-editor" className={styles.editor} data-expanded={expanded} data-view={view}>
    <div className={styles.editorSwitch}><SegmentedControl label={word("editor_view")} value={view} onChange={setView} fill segments={[{ key: "edit", label: word("edit") }, { key: "preview", label: word("preview") }]} /></div>
    <div className={styles.editorGrid}>
      <form ref={form} noValidate className={styles.formCard} onSubmit={event => { event.preventDefault(); if (step === "review") prepareEmail(); else next(); }}>
        <div className={styles.editorStepHeader}>
          <p className={styles.muted}>{word("editor_step_count", { current: STEPS.indexOf(step) + 1, total: STEPS.length })}</p>
          <div className={styles.sectionHeading}>
            <h3 ref={stepHeading} tabIndex={-1} className={styles.editorStepTitle}>{word(step === "customer" ? "editor_customer_heading" : `editor_step_${step}`)}</h3>
            {step === "items" ? <ToolbarPicker label={word("currency")} value={draft.currency}>{close => CURRENCIES.map(currency => <button key={currency} type="button" className={styles.option} onClick={() => { setDraft(current => ({ ...current, currency })); close(); }}>{currency}</button>)}</ToolbarPicker> : null}
          </div>
          {step !== "customer" && step !== "items" ? <p className={styles.muted}>{word(`editor_help_${step}`)}</p> : null}
        </div>
        {step === "customer" ? <>
        <InvoiceCustomerField customers={customers} selectedId={draft.customer.id} selectedName={draft.customer.name} error={errorOf("id") || errorOf("name")} onNameChange={name => customer("name", name)} onBlur={() => checks.blur(draft.customer.id ? "name" : "id")} onChoose={item => { setDraft(current => ({ ...current, customer: customerSnapshot(item) })); setAddingCustomer(false); }} onAdd={name => { setDraft(current => ({ ...current, customer: { id: crypto.randomUUID(), name, email: "", taxId: "", address: "" } })); setAddingCustomer(true); requestAnimationFrame(() => document.getElementById("invoice-customer-search")?.focus()); }} />
        {draft.customer.id ? <>
        {!addingCustomer ? <p className={styles.muted}>{word("customers_invoice_snapshot")}</p> : null}
        <div className={styles.fields}>{(["email", "taxId", "address"] as const).map(key => <FormField key={key} {...feedback(key)} reserveMessages={[word(`error_${key === "email" ? "email" : key === "taxId" ? "tax_id" : "address_length"}`), ...(key === "taxId" ? [word("error_tax_id_length")] : [])]} label={word(key === "taxId" && draft.documentType === "E31" ? "customer_taxId_required" : `customer_${key}`)} value={draft.customer[key]} type={key === "email" ? "email" : "text"} required={key === "taxId" && draft.documentType === "E31"} maxLength={CUSTOMER_FIELD_LIMITS[key]} autoComplete="off" placeholder={word(`placeholder_${key}`)} onBlur={() => { checks.blur(key); if (key === "taxId") customer(key, formatCustomerTaxId(draft.customer[key])); }} onChange={event => customer(key, event.target.value)} />)}</div>
        </> : null}
        </> : null}
        {step === "terms" ? <>
        <div className={fieldLabelClass}><span>{word("document_type")}</span>
        <ToolbarPicker label={word("document_type")} value={word(`document_${draft.documentType}`)}>{close => (["E32", "E31"] as const).map(documentType => <button type="button" key={documentType} className={styles.option} onClick={() => { setDraft(current => ({ ...current, documentType })); close(); }}>{word(`document_${documentType}`)}</button>)}</ToolbarPicker>
        </div>
        <div className={styles.fields}>{(["issuedOn", "dueOn"] as const).map(key => <InvoiceDateField key={key} id={`invoice-${key}`} label={word(key === "issuedOn" ? "issue_date" : "due_date")} value={draft[key]} error={errorOf(key)} onBlur={() => checks.blur(key)} onChange={value => field(key, value)} />)}</div>
        {(["terms", "instructions"] as const).map(key => <label className={fieldLabelClass} key={key}>{word(key)}<textarea rows={2} className={fieldClass} maxLength={500} value={draft[key]} placeholder={word(`placeholder_${key}`)} onChange={event => field(key, event.target.value)} /><span className={styles.counter}>{draft[key].length}/500</span></label>)}
        </> : null}
        {step === "items" ? <>
        <div className={styles.itemList}>
          {draft.items.map((item, index) => {
            const expanded = activeItemId === item.id;
            const amount = invoiceLineAmounts(item);
            return <fieldset id={`invoice-item-${item.id}`} className={styles.item} key={item.id} data-expanded={expanded}>
              <legend className="sr-only">{word("item_number", { count: index + 1 })}</legend>
              {expanded ? <div id={`invoice-item-fields-${item.id}`} className={styles.itemFields}>
                <FormField {...feedback(`${item.id}-description`)} reserveMessages={[]} label={word("item_description")} required maxLength={160} value={item.description} placeholder={word("item_placeholder")} onChange={event => updateItem(item.id, "description", event.target.value)} />
                {numberField(item, index, "quantity")}
                {numberField(item, index, "price")}
              </div> : <button type="button" className={styles.itemSummary} aria-expanded={false} aria-label={word("edit_item", { count: index + 1, name: item.description || word("item_number", { count: index + 1 }) })} onClick={() => { setActiveItemId(item.id); setItemFocus({ id: item.id, invalid: false }); }}>
                <span><strong>{item.description || word("item_number", { count: index + 1 })}</strong><small>{item.quantity} × {hundredths(item.price) !== null ? <InvoiceMoney amount={hundredths(item.price)!} currency={draft.currency} /> : "-"}</small></span>
                <span className={styles.itemSummaryAmount}>{amount ? <InvoiceMoney amount={amount.total} currency={draft.currency} /> : "-"}<ChevronDown size={16} aria-hidden="true" /></span>
              </button>}
              <button type="button" className={`${styles.iconButton} ${styles.itemRemove}`} disabled={draft.items.length === 1} aria-label={word("remove_item", { count: index + 1 })} onClick={() => removeItem(item.id)}><Trash2 size={17} /></button>
              {expanded ? <div className={styles.itemAdjustment}>
                {numberField(item, index, "tax")}
                {numberField(item, index, "discount")}
                <div className={styles.itemTotal}><span>{word("item_total")}</span><strong>{amount ? <InvoiceMoney amount={amount.total} currency={draft.currency} /> : "-"}</strong></div>
              </div> : null}
            </fieldset>;
          })}
        </div>
        <button type="button" className={`${quietButtonClass} ${styles.addItem}`} disabled={draft.items.length >= 50} onClick={addItem}><Plus size={17} />{word("add_item")}</button>
        <p className={styles.muted}>{word("tax_note")}</p>
        <label className={fieldLabelClass}>{word("notes")}<textarea rows={2} className={fieldClass} maxLength={500} value={draft.notes} placeholder={word("placeholder_notes")} onChange={event => field("notes", event.target.value)} /><span className={styles.counter}>{draft.notes.length}/500</span></label>
        </> : null}
        {step === "review" ? <>
        <div className={styles.editorReview}>
          {STEPS.filter(candidate => candidate !== "review").map(candidate => <button type="button" className={styles.editorReviewRow} key={candidate} onClick={() => goTo(candidate)}><span><strong>{word(`editor_step_${candidate}`)}</strong><small>{candidate === "customer" ? draft.customer.name : candidate === "items" ? word("editor_item_count", { count: draft.items.length }) : <><InvoiceDate date={draft.issuedOn} /> · <InvoiceDate date={draft.dueOn} /></>}</small></span><span>{word("edit")}</span></button>)}
        </div>
        <div className={styles.reviewTotal}><span>{word("document_total")}</span><strong>{(() => { const amount = invoiceAmounts(draft); return amount ? <InvoiceMoney amount={amount.total} currency={draft.currency} /> : "-"; })()}</strong></div>
        <FormField id="invoice-email-to" label={word("email_to")} value={email.to} type="email" autoComplete="off" maxLength={254} placeholder={word("placeholder_email")} error={emailChecks.errorOf("to")} onBlur={() => emailChecks.blur("to")} reserveMessages={[word("error_email")]} onChange={event => updateEmail("to", event.target.value)} />
        <FormField id="invoice-email-cc" label={word("email_cc")} value={email.cc} autoComplete="off" maxLength={1274} placeholder={word("email_cc_placeholder")} error={emailChecks.errorOf("cc")} onBlur={() => emailChecks.blur("cc")} reserveMessages={[word("error_email_cc")]} onChange={event => updateEmail("cc", event.target.value)} />
        <label className={fieldLabelClass} htmlFor="invoice-email-message">{word("email_message")}<textarea id="invoice-email-message" rows={3} className={fieldClass} maxLength={500} value={email.message} placeholder={word("email_message_placeholder")} onChange={event => updateEmail("message", event.target.value)} /><span className={styles.counter}>{email.message.length}/500</span></label>
        </> : null}
        {attempted.has(step) && Object.keys(errors).some(key => stepForField(key) === step) ? <p role="alert" className={styles.error}>{word("editor_check_step")}</p> : null}
        <div className={styles.footer}>
          <p className={styles.muted}>{word(step === "review" ? "email_local_boundary" : "save_local")}</p>
          <div className={styles.editorActions}>
            <button className={quietButtonClass} type="button" onClick={save}>{word("save_draft")}</button>
            <div>{step !== "customer" ? <button type="button" className={quietButtonClass} onClick={() => goTo(STEPS[STEPS.indexOf(step) - 1])}>{t("common.back")}</button> : null}<button className={primaryButtonClass} type="submit">{word(step === "review" ? "email_save_preparation" : "next")}</button></div>
          </div>
        </div>
      </form>
      <aside className={styles.livePreview}>{step === "review" ? <SegmentedControl label={word("review_preview")} value={reviewView} onChange={setReviewView} segments={[{ key: "invoice", label: word("invoice") }, { key: "email", label: word("email_preview") }]} /> : <p className={styles.muted}>{word("live_preview")}</p>}{step === "review" && reviewView === "email" ? <InvoiceEmailPreview invoice={draft} business={business} /> : <InvoiceDocument invoice={draft} business={business} activeSection={step} />}</aside>
    </div>
  </section>
  </AdaptivePanel>
    {leaving ? <AdaptivePanel title={word("unsaved")} closeLabel={t("common.close")} onClose={() => setLeaving(false)}><div className={styles.panelBody}><p>{word("leave_note")}</p><button className={primaryButtonClass} onClick={save}>{word("save_draft")}</button><button className={quietButtonClass} onClick={onClose}>{word("discard")}</button></div></AdaptivePanel> : null}
  </>;
}
