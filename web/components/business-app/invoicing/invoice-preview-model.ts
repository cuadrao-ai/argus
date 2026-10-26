import { todayIso } from "../business-format";

export type InvoiceCurrency = "DOP" | "USD" | "EUR";
export type InvoiceCustomer = { id: string; name: string; email: string; address: string; taxId: string };
export type InvoiceItem = { id: string; description: string; quantity: string; price: string; tax: string; discount?: string };
export type InvoiceEmailDraft = { to: string; cc: string; message: string };
export type InvoicePayment = { id: string; amount: number; currency: InvoiceCurrency; date: string; method: "transfer" | "cash" | "other"; reference: string };
export type InvoiceCorrectionKind = "full_cancellation" | "partial_credit" | "debit_adjustment";
export type InvoiceCorrection = {
  id: string; kind: InvoiceCorrectionKind; reason: string; amount: number;
  attempts: { number: number; status: "pending" | "confirmed" | "failed" }[];
};
export type InvoiceFiscalStatus = "not_submitted" | "processing" | "accepted" | "accepted_observations" | "rejected" | "failed" | "uncertain";
export type InvoicePreview = {
  documentType: "E31" | "E32";
  fiscal: { status: InvoiceFiscalStatus; documentNumber?: string };
  id: string; reference: string; customer: InvoiceCustomer; currency: InvoiceCurrency;
  issuedOn: string; dueOn: string; items: InvoiceItem[]; terms: string; notes: string; instructions: string;
  issuance: "draft" | "issued" | "uncertain";
  delivery: "not_sent" | "prepared" | "sent" | "failed";
  emailDraft?: InvoiceEmailDraft;
  deliveryPreparation?: { channel: "email" | "link"; email: string };
  payments: InvoicePayment[];
  corrections: InvoiceCorrection[];
};
export type InvoiceFilter = "all" | "draft" | "outstanding" | "overdue" | "paid" | "void";
export const CURRENCIES: readonly InvoiceCurrency[] = ["DOP", "USD", "EUR"];

// Exact hundredths, bounded before multiplication; never parse a money input with float arithmetic.
export function hundredths(text: string): number | null {
  const match = /^(\d{1,7})(?:[.,](\d{1,2}))?$/.exec(text.trim());
  return match ? Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0")) : null;
}
export function invoiceLineAmounts(item: InvoiceItem) {
  const qty = hundredths(item.quantity), price = hundredths(item.price), rate = hundredths(item.tax);
  const discount = hundredths(item.discount?.trim() || "0");
  if (qty === null || price === null || rate === null || discount === null || qty <= 0 || qty > 100000 || rate > 10000) return null;
  const subtotal = Number((BigInt(qty) * BigInt(price) + BigInt(50)) / BigInt(100));
  if (discount > subtotal) return null;
  const tax = Number((BigInt(subtotal - discount) * BigInt(rate) + BigInt(5000)) / BigInt(10000));
  return { subtotal, discount, tax, total: subtotal - discount + tax };
}
export function invoiceAmounts(invoice: Pick<InvoicePreview, "items" | "payments">) {
  let subtotal = 0, discount = 0, tax = 0;
  for (const item of invoice.items) {
    const line = invoiceLineAmounts(item);
    if (!line) return null;
    subtotal += line.subtotal;
    discount += line.discount;
    tax += line.tax;
  }
  const total = subtotal - discount + tax;
  const paid = invoice.payments.reduce((sum, payment) => sum + payment.amount, 0);
  return { subtotal, discount, tax, total, paid, balance: total - paid };
}
export function invoiceEmailDraft(invoice: InvoicePreview): InvoiceEmailDraft {
  return invoice.emailDraft ?? { to: invoice.customer.email, cc: "", message: "" };
}
export function invoiceEmailErrors(email: InvoiceEmailDraft): Partial<Record<keyof InvoiceEmailDraft, string>> {
  const errors: Partial<Record<keyof InvoiceEmailDraft, string>> = {};
  const valid = (value: string) => value.length <= 254 && /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(value.trim());
  if (!valid(email.to)) errors.to = "email";
  const cc = email.cc.trim() ? email.cc.split(/[,;]/).map(value => value.trim()) : [];
  if (cc.length > 5 || cc.some(value => !valid(value))) errors.cc = "email_cc";
  if (email.message.length > 500) errors.message = "email_message";
  return errors;
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
  if (invoice.documentType === "E31" && !/^(?:[0-9]{9}|[0-9]{11})$/.test(invoice.customer.taxId.trim())) errors.taxId = "tax_id";
  if (!invoice.customer.id.trim()) errors.id = "customer";
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
    const discount = hundredths(item.discount?.trim() || "0");
    const base = quantity !== null && price !== null ? Number((BigInt(quantity) * BigInt(price) + BigInt(50)) / BigInt(100)) : null;
    if (discount === null || base !== null && discount > base) errors[`${item.id}-discount`] = "discount";
    if (tax === null || tax > 10000) errors[`${item.id}-tax`] = "tax";
  }
  if (invoice.items.length === 0 || invoice.items.length > 50) errors.items = "items";
  else if (invoiceAmounts(invoice)?.total === 0) errors[`${invoice.items[0].id}-price`] = "total";
  return errors;
}
export function correctionStatus(correction: InvoiceCorrection) {
  return correction.attempts[correction.attempts.length - 1].status;
}
export function isInvoiceVoid(invoice: InvoicePreview) {
  return invoice.corrections.some(correction => correction.kind === "full_cancellation" && correctionStatus(correction) === "confirmed");
}
export function invoiceSettlement(invoice: InvoicePreview) {
  const original = invoiceAmounts(invoice);
  if (!original) return null;
  const credited = invoice.corrections.reduce((sum, correction) => sum + (correctionStatus(correction) === "confirmed" && correction.kind !== "debit_adjustment" ? correction.amount : 0), 0);
  const debited = invoice.corrections.reduce((sum, correction) => sum + (correctionStatus(correction) === "confirmed" && correction.kind === "debit_adjustment" ? correction.amount : 0), 0);
  return { ...original, credited, debited, creditable: original.total + debited - credited, balance: original.balance + debited - credited };
}
export function correctionErrors(invoice: InvoicePreview, request: Pick<InvoiceCorrection, "kind" | "reason" | "amount">): Record<string, string> {
  const errors: Record<string, string> = {};
  const amount = invoiceSettlement(invoice);
  if (invoice.issuance !== "issued" || isInvoiceVoid(invoice) || !amount || request.kind !== "debit_adjustment" && amount.creditable <= 0) errors.invoice = "correction_unavailable";
  if (!request.reason.trim() || request.reason.trim().length > 500) errors.reason = "correction_reason";
  if (!amount || !Number.isSafeInteger(request.amount) || request.amount <= 0 || !Number.isSafeInteger(amount.creditable + request.amount) || (request.kind !== "debit_adjustment" && request.amount > amount.creditable)
    || (request.kind === "full_cancellation" && request.amount !== amount.creditable)) errors.amount = "correction_amount";
  return errors;
}
export function matchesInvoice(invoice: InvoicePreview, filter: InvoiceFilter, today = todayIso()) {
  const amounts = invoiceSettlement(invoice);
  if (filter === "all") return true;
  if (filter === "void") return isInvoiceVoid(invoice);
  if (filter === "draft") return invoice.issuance === "draft";
  if (invoice.issuance !== "issued" || !amounts || isInvoiceVoid(invoice)) return false;
  if (filter === "paid") return amounts.balance <= 0 && amounts.paid > 0;
  return amounts.balance > 0 && (filter !== "overdue" || invoice.dueOn < today);
}
export function invoiceState(invoice: InvoicePreview, today = todayIso()) {
  if (invoice.issuance !== "issued") return invoice.issuance;
  if (isInvoiceVoid(invoice)) return "void";
  const amount = invoiceSettlement(invoice);
  if (amount && amount.balance < 0) return "credit";
  if (matchesInvoice(invoice, "paid", today)) return "paid";
  if (amount?.balance === 0) return "credited";
  if (matchesInvoice(invoice, "overdue", today)) return "overdue";
  return invoice.payments.length ? "partial" : "outstanding";
}
export type InvoiceCommand =
  | { type: "save"; invoice: InvoicePreview }
  | { type: "issue"; id: string }
  | { type: "prepare"; id: string; preparation: NonNullable<InvoicePreview["deliveryPreparation"]> }
  | { type: "pay"; id: string; payment: InvoicePayment }
  | { type: "correct"; id: string; correction: Pick<InvoiceCorrection, "id" | "kind" | "reason" | "amount"> }
  | { type: "retry_correction"; id: string; correctionId: string }
  | { type: "resolve_correction"; id: string; correctionId: string; attempt: number; outcome: "confirmed" | "failed" };
export function invoiceReducer(invoices: InvoicePreview[], action: InvoiceCommand): InvoicePreview[] {
  if (action.type === "save") {
    if (action.invoice.issuance !== "draft" || !validDraft(action.invoice)) return invoices;
    const previous = invoices.find(invoice => invoice.id === action.invoice.id);
    if (previous && previous.issuance !== "draft") return invoices;
    return previous ? invoices.map(invoice => invoice.id === action.invoice.id ? action.invoice : invoice) : [...invoices, action.invoice];
  }
  return invoices.map(invoice => {
    if (invoice.id !== action.id) return invoice;
    if (action.type === "issue") return invoice.issuance === "draft" && validDraft(invoice) ? { ...invoice, issuance: "issued", fiscal: { status: "processing" } } : invoice;
    if (action.type === "prepare") return invoice.issuance === "issued" && (action.preparation.channel === "link" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(action.preparation.email)) ? { ...invoice, delivery: "prepared", deliveryPreparation: action.preparation } : invoice;
    if (action.type === "correct") {
      if (!action.correction.id.trim() || invoice.corrections.some(item => item.id === action.correction.id || correctionStatus(item) === "pending")
        || Object.keys(correctionErrors(invoice, action.correction)).length) return invoice;
      return { ...invoice, corrections: [...invoice.corrections, { ...action.correction, reason: action.correction.reason.trim(), attempts: [{ number: 1, status: "pending" }] }] };
    }
    if (action.type === "retry_correction" || action.type === "resolve_correction") {
      const target = invoice.corrections.find(item => item.id === action.correctionId);
      if (!target) return invoice;
      const latest = target.attempts[target.attempts.length - 1];
      if (action.type === "retry_correction") {
        if (latest.status !== "failed" || invoice.corrections.some(item => correctionStatus(item) === "pending")
          || Object.keys(correctionErrors(invoice, target)).length) return invoice;
        return { ...invoice, corrections: invoice.corrections.map(item => item === target ? { ...item, attempts: [...item.attempts, { number: latest.number + 1, status: "pending" }] } : item) };
      }
      if (latest.status !== "pending" || action.attempt !== latest.number) return invoice;
      if (action.outcome === "confirmed" && Object.keys(correctionErrors(invoice, target)).length) return invoice;
      return { ...invoice, corrections: invoice.corrections.map(item => item === target ? { ...item, attempts: item.attempts.map(attempt => attempt === latest ? { ...attempt, status: action.outcome } : attempt) } : item) };
    }
    const amount = invoiceSettlement(invoice);
    const payment = action.payment;
    if (invoice.issuance !== "issued" || isInvoiceVoid(invoice) || !amount || invoice.payments.some(item => item.id === payment.id)
      || !Number.isSafeInteger(payment.amount) || payment.amount <= 0 || payment.amount > amount.balance
      || payment.currency !== invoice.currency || !validIsoDate(payment.date) || payment.date > todayIso()) return invoice;
    return { ...invoice, payments: [...invoice.payments, payment] };
  });
}
export function newInvoice(id: string, reference: string): InvoicePreview {
  return { documentType: "E32", fiscal: { status: "not_submitted" }, id, reference, customer: { id: "", name: "", email: "", address: "", taxId: "" }, currency: "DOP", issuedOn: todayIso(), dueOn: todayIso(), items: [{ id: `${id}-1`, description: "", quantity: "1", price: "", tax: "0" }], terms: "", notes: "", instructions: "", issuance: "draft", delivery: "not_sent", payments: [], corrections: [] };
}
export function invoiceFixtures(): InvoicePreview[] {
  const day = (offset: number) => { const d = new Date(`${todayIso()}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + offset); return d.toISOString().slice(0, 10); };
  const make = (id: string, name: string, price: string, issuance: InvoicePreview["issuance"], dueOffset: number): InvoicePreview => ({ ...newInvoice(id, `M-${id}`), customer: { id: `customer-${id}`, name, email: `cliente${id}@example.test`, address: "", taxId: "" }, issuedOn: day(-14), dueOn: day(dueOffset), items: [{ id: `${id}-1`, description: "", quantity: "1", price, tax: "0" }], issuance, fiscal: { status: issuance === "issued" ? "accepted" : issuance === "uncertain" ? "uncertain" : "not_submitted" } });
  return [make("001", "Taller Brisa", "100.00", "draft", 7), make("002", "Colmado Aurora", "2400.00", "issued", -4), { ...make("003", "Estudio Palma", "800.00", "issued", 7), delivery: "failed" }, make("004", "Café Horizonte", "125.00", "uncertain", 7)];
}

export function invoicePreviewSeed(variant: string | null, reason: string): InvoicePreview[] {
  if (!variant || !["seeded", "correction-pending", "correction-failed", "correction-confirmed", "partial-confirmed", "credit-balance", "debit-confirmed", "fiscal-processing", "fiscal-accepted", "fiscal-observations", "fiscal-rejected", "fiscal-failed", "fiscal-uncertain"].includes(variant)) return [];
  let invoices = invoiceFixtures();
  if (variant === "seeded") return invoices;
  const fiscalVariants: Record<string, InvoiceFiscalStatus> = { "fiscal-processing": "processing", "fiscal-accepted": "accepted", "fiscal-observations": "accepted_observations", "fiscal-rejected": "rejected", "fiscal-failed": "failed", "fiscal-uncertain": "uncertain" };
  if (fiscalVariants[variant]) return invoices.map(invoice => invoice.id === "002" ? { ...invoice, fiscal: { status: fiscalVariants[variant] } } : invoice);
  const partial = variant === "partial-confirmed" || variant === "credit-balance";
  if (variant === "credit-balance") invoices = invoiceReducer(invoices, { type: "pay", id: "002", payment: { id: "fixture-payment", amount: 200000, currency: "DOP", date: todayIso(), method: "transfer", reference: "" } });
  invoices = invoiceReducer(invoices, { type: "correct", id: "002", correction: { id: "fixture-correction", kind: variant === "debit-confirmed" ? "debit_adjustment" : partial ? "partial_credit" : "full_cancellation", reason, amount: partial || variant === "debit-confirmed" ? 60000 : 240000 } });
  if (variant !== "correction-pending") invoices = invoiceReducer(invoices, { type: "resolve_correction", id: "002", correctionId: "fixture-correction", attempt: 1, outcome: variant === "correction-failed" ? "failed" : "confirmed" });
  return invoices;
}
