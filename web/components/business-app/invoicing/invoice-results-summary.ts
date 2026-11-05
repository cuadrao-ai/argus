import { invoiceSettlement, type InvoiceCurrency, type InvoiceFilter, type InvoicePreview } from "./invoice-preview-model";

export function summarizeInvoiceResults(results: readonly InvoicePreview[], currency: InvoiceCurrency | "all", filter: InvoiceFilter) {
  const groups = new Map<string, { total: number; settled: number; balance: number }>();
  if (!results.length && currency !== "all" && filter !== "draft") {
    groups.set(currency, { total: 0, settled: 0, balance: 0 });
  }
  let unconfirmed = 0;
  for (const invoice of results) {
    const amount = invoiceSettlement(invoice);
    if (!amount || invoice.issuance !== "issued") { unconfirmed++; continue; }
    const previous = groups.get(invoice.currency) ?? { total: 0, settled: 0, balance: 0 };
    groups.set(invoice.currency, { total: previous.total + amount.total + amount.debited - amount.credited, settled: previous.settled + amount.paid, balance: previous.balance + amount.balance });
  }
  return { currencies: [...groups].map(([currency, amount]) => ({ currency, ...amount })), exclusions: { unconfirmed, personal: 0, unavailable: 0 } };
}
