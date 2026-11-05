import type { InvoiceDraft, SavedInvoice, SavedCustomer } from "@/lib/business-invoices-api";
import type { InvoicePreview } from "./invoice-preview-model";
import type { BusinessCustomer } from "./customer-preview-model";

export function customerForEditor(customer: SavedCustomer): BusinessCustomer {
  return { id: customer.id, name: customer.data.name, email: customer.data.email, address: customer.data.address, taxId: customer.data.tax_id, status: customer.archived ? "archived" : "active", createdAt: customer.created_at, updatedAt: customer.updated_at };
}
export function invoiceForEditor(data: InvoiceDraft, id: string, operation: SavedInvoice["operation"] = null, reference = ""): InvoicePreview {
  const fiscal = operation?.state.legal === "ACCEPTED" ? "accepted" : operation?.state.legal === "ACCEPTED_WITH_OBSERVATIONS" ? "accepted_observations" : operation?.state.legal === "REJECTED" ? "rejected" : operation?.state.submission === "unknown" ? "uncertain" : operation ? "processing" : "not_submitted";
  return {
    id, reference: operation?.number ?? reference, customer: { id: data.customer_id ?? (Object.values(data.customer_input).some(Boolean) ? "inline-customer" : ""), name: data.customer_input.name, email: data.customer_input.email, taxId: data.customer_input.tax_id, address: data.customer_input.address },
    documentType: data.document_type, currency: data.currency, issuedOn: data.issued_on, dueOn: data.due_on,
    items: data.items.map(item => ({ id: item.id, description: item.description, quantity: item.quantity, price: item.price, tax: item.tax, discount: item.discount, classification: item.classification, taxTreatment: item.tax_treatment })), terms: data.terms, notes: data.notes, instructions: data.instructions,
    emailDraft: { ...data.delivery, cc: data.delivery.cc.join(", ") }, fiscalInput: { payment_type: data.payment_type, income_type: data.income_type, tax_inclusion: data.tax_inclusion },
    fiscal: { status: fiscal, documentNumber: operation?.number }, issuance: fiscal === "accepted" || fiscal === "accepted_observations" ? "issued" : "draft", delivery: "not_sent", payments: [], corrections: [],
  };
}
export function draftFromEditor(draft: InvoicePreview, base: InvoiceDraft, customers: SavedCustomer[]): InvoiceDraft {
  const selected = customers.find(customer => customer.id === draft.customer.id);
  const customerId = selected?.id ?? (base.customer_id === draft.customer.id ? base.customer_id : null);
  const contact = selected?.data ?? (base.customer_id === customerId ? base.customer_input : null);
  return {
    customer_id: customerId,
    customer_input: { name: draft.customer.name, email: draft.customer.email, tax_id: draft.customer.taxId, address: draft.customer.address, phone: contact?.phone ?? "", notes: contact?.notes ?? "" },
    document_type: draft.documentType, currency: draft.currency, issued_on: draft.issuedOn, due_on: draft.dueOn,
    items: draft.items.map(item => ({ id: item.id, description: item.description, quantity: item.quantity, price: item.price, tax: item.tax, discount: item.discount ?? "", classification: item.classification ?? null, tax_treatment: item.taxTreatment ?? null })),
    terms: draft.terms, notes: draft.notes, instructions: draft.instructions,
    delivery: draft.emailDraft ? { to: draft.emailDraft.to, cc: draft.emailDraft.cc.trim() ? draft.emailDraft.cc.split(/[,;]/).map(value => value.trim()) : [], message: draft.emailDraft.message } : base.delivery,
    payment_type: draft.fiscalInput?.payment_type ?? null, income_type: draft.fiscalInput?.income_type ?? null, tax_inclusion: draft.fiscalInput?.tax_inclusion ?? null,
  };
}
export function linkedDraftFromEditor(draft: InvoicePreview, base: InvoiceDraft, customers: SavedCustomer[], linked: SavedCustomer | null): InvoiceDraft {
  return draftFromEditor(linked ? { ...draft, customer: { ...draft.customer, id: linked.id } } : draft, base, linked ? [linked, ...customers] : customers);
}
export function blankInvoiceDraft(): InvoiceDraft {
  return { customer_id: null, customer_input: { name: "", email: "", tax_id: "", address: "", phone: "", notes: "" }, currency: "DOP", document_type: "E32", issued_on: "", due_on: "", items: [], terms: "", instructions: "", notes: "", delivery: { to: "", cc: [], message: "" }, payment_type: null, income_type: null, tax_inclusion: null };
}
