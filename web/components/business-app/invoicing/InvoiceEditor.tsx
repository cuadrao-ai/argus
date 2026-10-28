"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Plus, Trash2 } from "lucide-react";
import { FormField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import InvoiceDateField from "./InvoiceDateField";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { fieldClass, fieldLabelClass } from "@/components/ui/form-field";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import InvoiceDocument, { InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import InvoiceEmailPreview from "./InvoiceEmailPreview";
import { CURRENCIES, hundredths, invoiceLineAmounts, invoiceEmailDraft, invoiceEmailErrors, invoiceDraftErrors, validDraft, type InvoiceCustomer, type InvoiceItem, type InvoicePreview } from "./invoice-preview-model";
import { customerInputLimits } from "@/lib/business-invoices-api";
import type { SavedInvoice } from "@/lib/business-invoices-api";
import { InvoiceItemFiscalFields, InvoiceTermsFiscalFields } from "./InvoiceFiscalFields";
import InvoiceCustomerField from "./InvoiceCustomerField";
import { customerSnapshot, type BusinessCustomer } from "./customer-preview-model";
import { CUSTOMER_FIELD_LIMITS, formatCustomerTaxId } from "./customer-validation";
import styles from "./invoicing-preview.module.css";

const STEPS = ["customer", "items", "terms", "review"] as const;
type EditorStep = typeof STEPS[number];
const stepForField = (key: string): EditorStep => ["id", "name", "email", "taxId", "address"].includes(key) ? "customer" : ["issuedOn", "dueOn"].includes(key) ? "terms" : "items";

function fieldSnapshot(invoice: InvoicePreview): Record<string, unknown> {
  const fields: Record<string, unknown> = {
    customer_id: invoice.customer.id, "customer_input.name": invoice.customer.name, "customer_input.email": invoice.customer.email, "customer_input.tax_id": invoice.customer.taxId, "customer_input.address": invoice.customer.address,
    document_type: invoice.documentType, currency: invoice.currency, issued_on: invoice.issuedOn, due_on: invoice.dueOn, items: invoice.items,
    terms: invoice.terms, instructions: invoice.instructions, notes: invoice.notes,
    payment_type: invoice.fiscalInput?.payment_type ?? null, income_type: invoice.fiscalInput?.income_type ?? null, tax_inclusion: invoice.fiscalInput?.tax_inclusion ?? null,
  };
  for (const item of invoice.items) for (const [key, value] of Object.entries({ description: item.description, quantity: item.quantity, price: item.price, discount: item.discount ?? "", tax: item.tax, classification: item.classification ?? null, tax_treatment: item.taxTreatment ?? null })) fields[`items.${item.id}.${key}`] = value;
  return fields;
}

export type ConnectedInvoiceEditor = { busy: boolean; blocked: boolean; amounts: SavedInvoice["amounts"]; fieldErrors: Record<string, string>; savedInput: InvoicePreview | null; status: ReactNode; errorInput?: InvoicePreview | null; customerSearchStatus?: "pending" | "failed" | "ready"; onCustomerSearch?: (value: string) => void };

export default function InvoiceEditor({ initial, business, customers, onAddCustomer, onSave, onClose, connection }: { connection?: ConnectedInvoiceEditor; initial: InvoicePreview; business: string; customers: BusinessCustomer[]; onAddCustomer: (customer: BusinessCustomer) => void; onSave: (invoice: InvoicePreview, options?: { newCustomer: boolean }) => void; onClose: () => void }) {
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
  const [step, setStep] = useState<EditorStep>(() => {
    const fields = Object.keys(connection?.fieldErrors ?? {});
    if (fields.some(key => key === "customer_id" || key.startsWith("customer_input."))) return "customer";
    if (fields.some(key => key === "items" || key.startsWith("items."))) return "items";
    return fields.some(key => ["payment_type", "income_type", "tax_inclusion", "issued_on", "due_on", "terms", "instructions"].includes(key)) ? "terms" : "customer";
  });
  const [attempted, setAttempted] = useState<ReadonlySet<EditorStep>>(() => new Set());
  const [validationAttempt, setValidationAttempt] = useState(0);
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const values: Record<string, string> = { ...draft.customer, issuedOn: draft.issuedOn, dueOn: draft.dueOn, items: String(draft.items.length) };
  for (const item of draft.items) for (const key of ["description", "quantity", "price", "tax", "discount"] as const) values[`${item.id}-${key}`] = item[key] ?? "";
  const errors = connection ? {} : invoiceDraftErrors(draft);
  const rules: FieldRules<string> = Object.fromEntries(Object.keys(values).map(key => [key, () => errors[key] ? word(`error_${errors[key]}`) : null]));
  const checks = useFieldChecks(rules, values);
  const currentFields = fieldSnapshot(draft), reportedFields = fieldSnapshot(connection?.errorInput ?? connection?.savedInput ?? initial);
  const reportedErrors = Object.fromEntries(Object.entries(connection?.fieldErrors ?? {}).filter(([field]) => JSON.stringify(currentFields[field]) === JSON.stringify(reportedFields[field])));
  const serverError = (key: string) => {
    if (!connection) return null;
    const field = key === "id" ? "customer_id" : key === "issuedOn" ? "issued_on" : key === "dueOn" ? "due_on" : ["name", "email", "taxId", "address"].includes(key) ? `customer_input.${key === "taxId" ? "tax_id" : key}` : draft.items.reduce((path, item) => key.startsWith(`${item.id}-`) ? `items.${item.id}.${key.slice(item.id.length + 1)}` : path, key);
    const reason = reportedErrors[field];
    return reason ? t(`business.invoicing.${reason === "required" ? "field_required" : reason === "customer_invalid" ? "customer_field_invalid" : "field_unsupported"}`) : null;
  };
  const errorOf = (key: string) => serverError(key) || checks.errorOf(key) || ((attempted.has(stepForField(key)) || draft.items.some(item => checkedItems.has(item.id) && key.startsWith(`${item.id}-`))) && errors[key] ? word(`error_${errors[key]}`) : null);
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
    if (connection || !addingCustomer || Object.keys(errors).some(key => stepForField(key) === "customer")) return;
    onAddCustomer({ ...draft.customer, status: "active" });
    setAddingCustomer(false);
  };
  const next = () => {
    if (connection) { goTo(STEPS[Math.min(STEPS.indexOf(step) + 1, STEPS.length - 1)]); return; }
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
    if (connection) { onSave(draft, { newCustomer: addingCustomer }); return; }
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
    return <FormField {...feedback(fieldKey)} reserveMessages={[]} label={word(key === "discount" ? "item_discount" : key, { currency: draft.currency })} required={key !== "discount"} inputMode="decimal" autoComplete="off" maxLength={connection ? 32 : key === "quantity" ? 7 : key === "tax" ? 6 : 10} value={value} placeholder={word(money ? "placeholder_discount" : key === "quantity" ? "placeholder_quantity" : "placeholder_tax")} aria-label={`${word(key === "discount" ? "item_discount" : key, { currency: draft.currency })} ${index + 1}`} onChange={event => updateItem(item.id, key, event.target.value)} onPaste={event => {
      event.preventDefault();
      const input = event.currentTarget;
      updateItem(item.id, key, value.slice(0, input.selectionStart ?? 0) + event.clipboardData.getData("text") + value.slice(input.selectionEnd ?? value.length));
    }} onBlur={() => {
      checks.blur(fieldKey);
      if (connection) return;
      const parsed = hundredths(value);
      if (value && parsed !== null && !errors[fieldKey]) updateItem(item.id, key, money ? `${Math.floor(parsed / 100)}.${String(parsed % 100).padStart(2, "0")}` : value.trim().replace(",", "."));
    }} />;
  };
  const save = () => {
    saveNewCustomer();
    onSave(draft, { newCustomer: Boolean(connection) && addingCustomer });
  };
  return <>
  <AdaptivePanel title={word("draft_title")} summary={draft.reference ? `${business} · ${draft.reference}` : business} width="lg" snaps={["full"]} initialSnap="full" dismissible={!connection?.busy} closeLabel={t("common.close")} onClose={() => changed ? setLeaving(true) : onClose()} expansion={{ expanded, onToggle: () => setExpanded(value => !value), expandLabel: word("expand_editor"), collapseLabel: word("collapse_editor") }}>
  <section data-testid="invoice-editor" data-invoice-source={connection ? "connected" : "preview"} className={styles.editor} data-expanded={expanded} data-view={view} aria-busy={connection?.busy}>
    {connection?.status}
    <div className={styles.editorSwitch}><SegmentedControl label={word("editor_view")} value={view} onChange={setView} fill segments={[{ key: "edit", label: word("edit") }, { key: "preview", label: word("preview") }]} /></div>
    <div className={styles.editorGrid}>
      <form ref={form} noValidate className={styles.formCard} onSubmit={event => { event.preventDefault(); if (step === "review") prepareEmail(); else next(); }}>
        <fieldset className="contents" disabled={connection?.busy || connection?.blocked}>
        <div className={styles.editorStepHeader}>
          <p className={styles.muted}>{word("editor_step_count", { current: STEPS.indexOf(step) + 1, total: STEPS.length })}</p>
          <div className={styles.sectionHeading}>
            <h3 ref={stepHeading} tabIndex={-1} className={`${styles.editorStepTitle} ${step === "review" ? styles.reviewHeading : ""}`}>{word(step === "customer" ? "editor_customer_heading" : step === "review" ? "editor_review_heading" : `editor_step_${step}`)}</h3>
            {step === "items" ? <ToolbarPicker label={word("currency")} value={draft.currency}>{close => CURRENCIES.map(currency => <button key={currency} type="button" className={styles.option} onClick={() => { setDraft(current => ({ ...current, currency })); close(); }}>{currency}</button>)}</ToolbarPicker> : null}
          </div>
          {step === "review" ? <p className={styles.muted}>{word(`editor_help_${step}`)}</p> : null}
        </div>
        {step === "customer" ? <>
        <InvoiceCustomerField nameLimit={connection ? customerInputLimits.name : undefined} searchStatus={connection?.customerSearchStatus} onSearch={connection ? value => { connection.onCustomerSearch?.(value); if (!draft.customer.id) customer("name", value); } : undefined} customers={customers} selectedId={draft.customer.id} selectedName={draft.customer.name} error={errorOf("id") || errorOf("name")} onNameChange={name => customer("name", name)} onBlur={() => checks.blur(draft.customer.id ? "name" : "id")} onChoose={item => { setDraft(current => ({ ...current, customer: customerSnapshot(item) })); setAddingCustomer(false); }} onAdd={name => { setDraft(current => ({ ...current, customer: { id: crypto.randomUUID(), name, email: "", taxId: "", address: "" } })); setAddingCustomer(true); requestAnimationFrame(() => document.getElementById("invoice-customer-search")?.focus()); }} />
        {draft.customer.id ? <>
        {!addingCustomer ? <p className={styles.muted}>{word("customers_invoice_snapshot")}</p> : null}
        <div className={styles.fields}>{(["email", "taxId", "address"] as const).map(key => <FormField key={key} {...feedback(key)} reserveMessages={[word(`error_${key === "email" ? "email" : key === "taxId" ? "tax_id" : "address_length"}`), ...(key === "taxId" ? [word("error_tax_id_length")] : [])]} label={word(key === "taxId" && draft.documentType === "E31" ? "customer_taxId_required" : `customer_${key}`)} value={draft.customer[key]} type={key === "email" ? "email" : "text"} required={key === "taxId" && draft.documentType === "E31"} maxLength={connection ? customerInputLimits[key] : CUSTOMER_FIELD_LIMITS[key]} autoComplete="off" placeholder={word(`placeholder_${key}`)} onBlur={() => { checks.blur(key); if (!connection && key === "taxId") customer(key, formatCustomerTaxId(draft.customer[key])); }} onChange={event => customer(key, event.target.value)} />)}</div>
        </> : null}
        </> : null}
        {step === "terms" ? <>
        <div className={fieldLabelClass}><span>{word("document_type")}</span>
        <ToolbarPicker label={word("document_type")} value={word(`document_${draft.documentType}`)}>{close => (["E32", "E31"] as const).map(documentType => <button type="button" key={documentType} className={styles.option} onClick={() => { setDraft(current => ({ ...current, documentType })); close(); }}>{word(`document_${documentType}`)}</button>)}</ToolbarPicker>
        </div>
        {connection ? <InvoiceTermsFiscalFields value={draft.fiscalInput} errors={reportedErrors} onChange={fiscalInput => setDraft(current => ({ ...current, fiscalInput }))} /> : null}
        <div className={styles.dateFields}>{(["issuedOn", "dueOn"] as const).map(key => <InvoiceDateField due={key === "dueOn"} key={key} id={`invoice-${key}`} label={word(key === "issuedOn" ? "issue_date" : "due_date")} value={draft[key]} error={errorOf(key)} onBlur={() => checks.blur(key)} onChange={value => field(key, value)} />)}</div>
        {(["terms", "instructions"] as const).map(key => <label className={fieldLabelClass} key={key}>{word(key)}<textarea rows={2} className={fieldClass} maxLength={500} value={draft[key]} placeholder={word(`placeholder_${key}`)} onChange={event => field(key, event.target.value)} /><span className={styles.counter}>{draft[key].length}/500</span>{serverError(key) ? <span role="alert" className={styles.error}>{serverError(key)}</span> : null}</label>)}
        </> : null}
        {step === "items" ? <>
        <div className={styles.itemList}>
          {draft.items.map((item, index) => {
            const expanded = activeItemId === item.id;
            const amount = connection ? null : invoiceLineAmounts(item);
            return <fieldset id={`invoice-item-${item.id}`} className={styles.item} key={item.id} data-expanded={expanded}>
              <legend className="sr-only">{word("item_number", { count: index + 1 })}</legend>
              {expanded ? <><div id={`invoice-item-fields-${item.id}`} className={styles.itemFields}>
                <FormField {...feedback(`${item.id}-description`)} reserveMessages={[]} label={word("description")} required maxLength={160} value={item.description} placeholder={word("item_placeholder")} onChange={event => updateItem(item.id, "description", event.target.value)} />
                {numberField(item, index, "quantity")}
                {numberField(item, index, "price")}
              </div>{connection ? <InvoiceItemFiscalFields item={item} errors={reportedErrors} onChange={patch => setDraft(current => ({ ...current, items: current.items.map(value => value.id === item.id ? { ...value, ...patch } : value) }))} /> : null}</> : <button type="button" className={styles.itemSummary} aria-expanded={false} aria-label={word("edit_item", { count: index + 1, name: item.description || word("item_number", { count: index + 1 }) })} onClick={() => { setActiveItemId(item.id); setItemFocus({ id: item.id, invalid: false }); }}>
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
        {connection ? null : <p className={styles.muted}>{word("tax_note")}</p>}
        <label className={fieldLabelClass}>{word("notes")}<textarea rows={2} className={fieldClass} maxLength={500} value={draft.notes} placeholder={word("placeholder_notes")} onChange={event => field("notes", event.target.value)} /><span className={styles.counter}>{draft.notes.length}/500</span></label>
        </> : null}
        {step === "review" ? <>
        <nav className={styles.reviewEditLinks} aria-label={word("edit")}>
          {STEPS.filter(candidate => candidate !== "review").map(candidate => <button type="button" className={quietButtonClass} key={candidate} onClick={() => goTo(candidate)}>{word(`editor_step_${candidate}`)}</button>)}
        </nav>
        <FormField id="invoice-email-to" label={word("email_to")} value={email.to} type="email" autoComplete="off" maxLength={254} placeholder={word("placeholder_email")} error={emailChecks.errorOf("to")} onBlur={() => emailChecks.blur("to")} reserveMessages={[word("error_email")]} onChange={event => updateEmail("to", event.target.value)} />
        <FormField id="invoice-email-cc" label={word("email_cc")} value={email.cc} autoComplete="off" maxLength={1274} placeholder={word("email_cc_placeholder")} error={emailChecks.errorOf("cc")} onBlur={() => emailChecks.blur("cc")} reserveMessages={[word("error_email_cc")]} onChange={event => updateEmail("cc", event.target.value)} />
        <label className={fieldLabelClass} htmlFor="invoice-email-message">{word("email_message")}<textarea id="invoice-email-message" rows={3} className={fieldClass} maxLength={500} value={email.message} placeholder={word("email_message_placeholder")} onChange={event => updateEmail("message", event.target.value)} /><span className={styles.counter}>{email.message.length}/500</span></label>
        <div className={styles.reviewSubmit}>
          <button className={`${primaryButtonClass} ${styles.editorPrimary}`} type="submit">{word(connection ? "save_draft" : "email_save_preparation")}</button>
          <p className={styles.muted}>{connection ? t("business.invoicing.save_only_note") : word("email_local_boundary")}</p>
        </div>
        </> : null}
        {attempted.has(step) && Object.keys(errors).some(key => stepForField(key) === step) ? <p role="alert" className={styles.error}>{word("editor_check_step")}</p> : null}
        <div className={styles.footer}>
          {step !== "review" ? <button className={`${primaryButtonClass} ${styles.editorPrimary}`} type="submit">{word("next")}</button> : null}
          <div className={styles.editorActions}>
            <button className={quietButtonClass} type="button" onClick={save}>{word("save_draft")}</button>
            {step !== "customer" ? <button type="button" className={quietButtonClass} onClick={() => goTo(STEPS[STEPS.indexOf(step) - 1])}>{t("common.back")}</button> : null}
          </div>
        </div>
        </fieldset>
      </form>
      <aside className={styles.livePreview}>{step === "review" && !connection ? <div className={styles.stageTabs} role="tablist" aria-label={word("review_preview")}>
        {(["invoice", "email"] as const).map(tab => <button key={tab} type="button" role="tab" id={`review-tab-${tab}`} aria-selected={reviewView === tab} aria-controls="invoice-review-preview" tabIndex={reviewView === tab ? 0 : -1} onClick={() => setReviewView(tab)} onKeyDown={event => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "Home" ? "invoice" : event.key === "End" ? "email" : tab === "invoice" ? "email" : "invoice";
          setReviewView(next);
          document.getElementById(`review-tab-${next}`)?.focus();
        }}>{word(tab === "invoice" ? "invoice" : "email_preview")}</button>)}
      </div> : <p className={styles.muted}>{word("live_preview")}</p>}<div id="invoice-review-preview" role={step === "review" ? "tabpanel" : undefined} aria-labelledby={step === "review" ? `review-tab-${reviewView}` : undefined}>{step === "review" && reviewView === "email" && !connection ? <InvoiceEmailPreview invoice={draft} business={business} /> : <InvoiceDocument invoice={draft} business={business} activeSection={step} connection={connection ? { amounts: connection.savedInput && JSON.stringify(draft) === JSON.stringify(connection.savedInput) ? connection.amounts : null } : undefined} />}</div></aside>
    </div>
  </section>
  </AdaptivePanel>
    {leaving ? <AdaptivePanel title={word("unsaved")} closeLabel={t("common.close")} onClose={() => setLeaving(false)}><div className={styles.panelBody}><p>{word("leave_note")}</p><button className={primaryButtonClass} onClick={save}>{word("save_draft")}</button><button className={quietButtonClass} onClick={onClose}>{word("discard")}</button></div></AdaptivePanel> : null}
  </>;
}
