import { todayIso } from "../business-format";

export type InvoiceCurrency = "DOP" | "USD" | "EUR";
export type InvoiceCustomer = { id: string; name: string; email: string; address: string; taxId: string };
export type InvoiceItem = { id: string; description: string; quantity: string; price: string; tax: string };
export type InvoicePayment = { id: string; amount: number; currency: InvoiceCurrency; date: string; method: "transfer" | "cash" | "other"; reference: string };
export type InvoicePreview = {
  id: string; reference: string; customer: InvoiceCustomer; currency: InvoiceCurrency;
  issuedOn: string; dueOn: string; items: InvoiceItem[]; terms: string; notes: string; instructions: string;
  issuance: "draft" | "issued" | "uncertain";
  delivery: "not_sent" | "prepared" | "sent" | "failed";
  deliveryPreparation?: { channel: "email" | "link"; email: string };
  payments: InvoicePayment[];
};
export type InvoiceFilter = "all" | "draft" | "outstanding" | "overdue" | "paid";
export const CURRENCIES: readonly InvoiceCurrency[] = ["DOP", "USD", "EUR"];

// Exact hundredths, bounded before multiplication; never parse a money input with float arithmetic.
export function hundredths(text: string): number | null {
  const match = /^(\d{1,7})(?:[.,](\d{1,2}))?$/.exec(text.trim());
  return match ? Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0")) : null;
}
export function invoiceAmounts(invoice: Pick<InvoicePreview, "items" | "payments">) {
  let subtotal = 0, tax = 0;
  for (const item of invoice.items) {
    const qty = hundredths(item.quantity), price = hundredths(item.price), rate = hundredths(item.tax);
    if (qty === null || price === null || rate === null || qty <= 0 || qty > 100000 || rate > 10000) return null;
    const base = Number((BigInt(qty) * BigInt(price) + BigInt(50)) / BigInt(100));
    subtotal += base;
    tax += Number((BigInt(base) * BigInt(rate) + BigInt(5000)) / BigInt(10000));
  }
  const total = subtotal + tax;
  const paid = invoice.payments.reduce((sum, payment) => sum + payment.amount, 0);
  return { subtotal, tax, total, paid, balance: total - paid };
}
export function validIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
export function validDraft(invoice: InvoicePreview) {
  return Object.keys(invoiceDraftErrors(invoice)).length === 0;
}
export function invoiceDraftErrors(invoice: InvoicePreview): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!invoice.customer.name.trim()) errors.name = "required";
  if (invoice.customer.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(invoice.customer.email)) errors.email = "email";
  if (!validIsoDate(invoice.issuedOn)) errors.issuedOn = "date";
  if (!validIsoDate(invoice.dueOn)) errors.dueOn = "date";
  else if (validIsoDate(invoice.issuedOn) && invoice.dueOn < invoice.issuedOn) errors.dueOn = "due_date";
  for (const item of invoice.items) {
    if (!item.description.trim()) errors[`${item.id}-description`] = "required";
    const quantity = hundredths(item.quantity), price = hundredths(item.price), tax = hundredths(item.tax);
    if (quantity === null || quantity <= 0 || quantity > 100000) errors[`${item.id}-quantity`] = "quantity";
    if (price === null) errors[`${item.id}-price`] = "price";
    if (tax === null || tax > 10000) errors[`${item.id}-tax`] = "tax";
  }
  if (invoice.items.length === 0 || invoice.items.length > 50) errors.items = "items";
  else if (invoiceAmounts(invoice)?.total === 0) errors[`${invoice.items[0].id}-price`] = "total";
  return errors;
}
export function matchesInvoice(invoice: InvoicePreview, filter: InvoiceFilter, today = todayIso()) {
  const amounts = invoiceAmounts(invoice);
  if (filter === "all") return true;
  if (filter === "draft") return invoice.issuance === "draft";
  if (invoice.issuance !== "issued" || !amounts) return false;
  if (filter === "paid") return amounts.balance === 0;
  return amounts.balance > 0 && (filter !== "overdue" || invoice.dueOn < today);
}
export function invoiceState(invoice: InvoicePreview, today = todayIso()) {
  if (invoice.issuance !== "issued") return invoice.issuance;
  if (matchesInvoice(invoice, "paid", today)) return "paid";
  if (matchesInvoice(invoice, "overdue", today)) return "overdue";
  return invoice.payments.length ? "partial" : "outstanding";
}
export type InvoiceCommand = { type: "save"; invoice: InvoicePreview } | { type: "issue"; id: string } | { type: "prepare"; id: string; preparation: NonNullable<InvoicePreview["deliveryPreparation"]> } | { type: "pay"; id: string; payment: InvoicePayment };
export function invoiceReducer(invoices: InvoicePreview[], action: InvoiceCommand): InvoicePreview[] {
  if (action.type === "save") {
    if (!validDraft(action.invoice)) return invoices;
    const previous = invoices.find(invoice => invoice.id === action.invoice.id);
    if (previous && previous.issuance !== "draft") return invoices;
    return previous ? invoices.map(invoice => invoice.id === action.invoice.id ? action.invoice : invoice) : [...invoices, action.invoice];
  }
  return invoices.map(invoice => {
    if (invoice.id !== action.id) return invoice;
    if (action.type === "issue") return invoice.issuance === "draft" && validDraft(invoice) ? { ...invoice, issuance: "issued" } : invoice;
    if (action.type === "prepare") return invoice.issuance === "issued" && (action.preparation.channel === "link" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(action.preparation.email)) ? { ...invoice, delivery: "prepared", deliveryPreparation: action.preparation } : invoice;
    const amount = invoiceAmounts(invoice);
    const payment = action.payment;
    if (invoice.issuance !== "issued" || !amount || invoice.payments.some(item => item.id === payment.id)
      || !Number.isSafeInteger(payment.amount) || payment.amount <= 0 || payment.amount > amount.balance
      || payment.currency !== invoice.currency || !validIsoDate(payment.date) || payment.date > todayIso()) return invoice;
    return { ...invoice, payments: [...invoice.payments, payment] };
  });
}
export function newInvoice(id: string, reference: string): InvoicePreview {
  return { id, reference, customer: { id: "", name: "", email: "", address: "", taxId: "" }, currency: "DOP", issuedOn: todayIso(), dueOn: todayIso(), items: [{ id: `${id}-1`, description: "", quantity: "1", price: "", tax: "0" }], terms: "", notes: "", instructions: "", issuance: "draft", delivery: "not_sent", payments: [] };
}
export function invoiceFixtures(): InvoicePreview[] {
  const day = (offset: number) => { const d = new Date(`${todayIso()}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + offset); return d.toISOString().slice(0, 10); };
  const make = (id: string, name: string, price: string, issuance: InvoicePreview["issuance"], dueOffset: number): InvoicePreview => ({ ...newInvoice(id, `M-${id}`), customer: { id: `customer-${id}`, name, email: `cliente${id}@example.test`, address: "", taxId: "" }, issuedOn: day(-14), dueOn: day(dueOffset), items: [{ id: `${id}-1`, description: "", quantity: "1", price, tax: "0" }], issuance });
  return [make("001", "Taller Brisa", "100.00", "draft", 7), make("002", "Colmado Aurora", "2400.00", "issued", -4), { ...make("003", "Estudio Palma", "800.00", "issued", 7), delivery: "failed" }, make("004", "Café Horizonte", "125.00", "uncertain", 7)];
}
