import { invoiceSettlement, type InvoiceCurrency, type InvoiceCustomer, type InvoicePreview } from "./invoice-preview-model";

export type BusinessCustomer = InvoiceCustomer & { status: "active" | "archived"; createdAt?: string; updatedAt?: string };
export type CustomerCommand = { type: "save"; customer: BusinessCustomer } | { type: "status"; id: string; status: BusinessCustomer["status"] };

export function customerErrors(customer: InvoiceCustomer): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!customer.name.trim() || customer.name.length > 120) errors.name = "required";
  if (customer.email && (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(customer.email) || customer.email.length > 254)) errors.email = "email";
  if (customer.taxId && !/^(?:[0-9]{9}|[0-9]{11})$/.test(customer.taxId)) errors.taxId = "tax_id";
  if (customer.address.length > 240) errors.address = "required";
  return errors;
}
export function customerReducer(customers: BusinessCustomer[], action: CustomerCommand): BusinessCustomer[] {
  if (action.type === "status") return customers.map(customer => customer.id === action.id ? { ...customer, status: action.status } : customer);
  if (!action.customer.id || Object.keys(customerErrors(action.customer)).length) return customers;
  const previous = customers.find(customer => customer.id === action.customer.id);
  const now = new Date().toISOString();
  const saved = { ...action.customer, name: action.customer.name.trim(), status: previous?.status ?? "active" as const, createdAt: previous ? previous.createdAt : now, updatedAt: now };
  return previous ? customers.map(customer => customer === previous ? saved : customer) : [...customers, saved];
}

export function customerRecentActivity(customer: BusinessCustomer, invoices: InvoicePreview[]) {
  const activity = customerActivity(invoices, customer.id);
  const lastInvoice = activity.invoices.filter(invoice => invoice.issuance === "issued").sort((a, b) => b.issuedOn.localeCompare(a.issuedOn))[0];
  const lastPayment = activity.payments[0];
  const events = [
    ...(customer.updatedAt ? [{ kind: "customer_updated", date: customer.updatedAt.slice(0, 10) }] : []),
    ...(lastInvoice ? [{ kind: "invoice_issued", date: lastInvoice.issuedOn }] : []),
    ...(lastPayment ? [{ kind: "payment_recorded", date: lastPayment.date }] : []),
  ].sort((a, b) => b.date.localeCompare(a.date));
  return { lastInvoice, lastPayment, latest: events[0] };
}
export function seedCustomers(invoices: InvoicePreview[]): BusinessCustomer[] {
  return [...new Map(invoices.map(invoice => [invoice.customer.id, { ...invoice.customer, status: "active" as const }])).values()];
}
export function customerSnapshot({ id, name, email, address, taxId }: BusinessCustomer): InvoiceCustomer {
  return { id, name, email, address, taxId };
}
export function matchesCustomer(customer: BusinessCustomer, query: string): boolean {
  const normalize = (value: string) => value.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();
  return normalize(`${customer.name} ${customer.email} ${customer.taxId}`).includes(normalize(query.trim()));
}
export function customerActivity(invoices: InvoicePreview[], customerId: string) {
  const linked = invoices.filter(invoice => invoice.customer.id === customerId);
  const totals = new Map<InvoiceCurrency, { total: number; paid: number; balance: number }>();
  const payments = linked.filter(invoice => invoice.issuance === "issued").flatMap(invoice => invoice.payments.map(payment => ({ ...payment, invoiceId: invoice.id, invoiceReference: invoice.reference })));
  for (const invoice of linked) {
    const amount = invoiceSettlement(invoice);
    if (invoice.issuance !== "issued" || !amount) continue;
    const previous = totals.get(invoice.currency) ?? { total: 0, paid: 0, balance: 0 };
    totals.set(invoice.currency, { total: previous.total + amount.total + amount.debited - amount.credited, paid: previous.paid + amount.paid, balance: previous.balance + amount.balance });
  }
  return { invoices: linked, totals: [...totals].map(([currency, amounts]) => ({ currency, ...amounts })), payments: payments.sort((a, b) => b.date.localeCompare(a.date)) };
}
