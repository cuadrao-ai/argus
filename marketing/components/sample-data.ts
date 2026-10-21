export const sampleExpenses = [
  { category: 0, amount: 98000 },
  { category: 1, amount: 42000 },
  { category: 2, amount: 18500 },
  { category: 3, amount: 10000 },
] as const;

const sampleExpenseTotal = sampleExpenses.reduce(
  (sum, item) => sum + item.amount,
  0,
);
export const sampleMonths = [
  { income: 185000, expenses: 132000 },
  { income: 235000, expenses: 158000 },
  { income: 256000, expenses: 147000 },
  { income: 142000, expenses: 110000 },
  { income: 245000, expenses: sampleExpenseTotal },
  { income: 218000, expenses: 153000 },
] as const;

export const sampleReceivables = [
  { id: "1024", customer: "A", day: 12, amount: 48000 },
  { id: "1031", customer: "B", day: 18, amount: 32500 },
  { id: "1040", customer: "C", day: 27, amount: 25000 },
] as const;

export const sampleInvoiceStory = {
  invoice: sampleReceivables[0],
  customerName: "Comercial La Ceiba",
  payment: 18000,
} as const;

export function getSampleSummary(): {
  income: number;
  expenses: number;
  difference: number;
  receivables: number;
} {
  const income = sampleMonths[4].income;
  const expenses = sampleExpenseTotal;
  return {
    income,
    expenses,
    difference: income - expenses,
    receivables: sampleReceivables.reduce((sum, item) => sum + item.amount, 0),
  };
}

export function formatSampleMoney(value: number, locale: "es" | "en"): string {
  return `RD$ ${new Intl.NumberFormat(locale === "es" ? "es-DO" : "en-US", { maximumFractionDigits: 0 }).format(value)}`;
}
