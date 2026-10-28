import type { InvoiceDraft, SavedInvoice, SavedCustomer, InvoiceScope } from "@/lib/business-invoices-api";
export const invoiceId = "10000000-0000-4000-8000-000000000001";
export const invoiceScope: InvoiceScope = { userId: "invoice-test-person", businessId: "20000000-0000-4000-8000-000000000002", grantId: "30000000-0000-4000-8000-000000000003" };
export function incompleteInvoice(): InvoiceDraft {
  return { customer_id: null, customer_input: { name: "", email: "", tax_id: "", address: "", phone: "", notes: "" }, document_type: "E32", currency: "DOP", issued_on: "", due_on: "", items: [], terms: "", instructions: "", notes: "", delivery: { to: "", cc: [], message: "" }, payment_type: null, income_type: null, tax_inclusion: null };
}
export function savedInvoice(data = incompleteInvoice()): SavedInvoice {
  return { id: invoiceId, business_id: invoiceScope.businessId, version: 1, revision_id: "40000000-0000-4000-8000-000000000004", data, field_errors: { payment_type: "required" }, amounts: null, operation: null, payment_state: "unknown", paid_amount: null, outstanding_amount: null, delivery_state: "not_sent", created_at: "2026-10-27T16:00:00Z", updated_at: "2026-10-27T16:00:00Z" };
}
export function savedCustomer(): SavedCustomer {
  return { id: "50000000-0000-4000-8000-000000000005", business_id: invoiceScope.businessId, version: 1, data: { name: "Taller sintético", email: "", tax_id: "", address: "", phone: "", notes: "" }, archived: false, created_at: "2026-10-27T00:00:00Z", updated_at: "2026-10-27T00:00:00Z" };
}
