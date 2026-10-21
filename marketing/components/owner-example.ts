import type { BusinessLocale } from "./content";
import { sampleInvoiceStory } from "./sample-data";
import { sampleExpenseStory, samplePriorities } from "./sample-priorities";

type Label = Record<BusinessLocale, string>;
export type ExampleCurrency = "DOP" | "USD";
export type MoneyMovement = {
  id: string;
  label: Label;
  amount: number;
  currency: ExampleCurrency;
  date: string;
} & (
  | { kind: "income" | "expense" | "owner-contribution" | "owner-withdrawal"; account: "business" }
  | { kind: "expense"; account: "personal"; linkedId: string }
);
export const exampleAccounts = [
  { currency: "DOP", opening: 62000, label: { es: "Cuenta y caja del negocio", en: "Business account and cash" } },
  { currency: "USD", opening: 900, label: { es: "Cuenta en dólares", en: "Dollar account" } },
] as const;
export const exampleMovements: readonly MoneyMovement[] = [
  { id: "payment-1024", label: { es: "Abono de Comercial La Ceiba", en: "Comercial La Ceiba payment" }, amount: sampleInvoiceStory.payment, currency: "DOP", date: "2026-10-06", kind: "income", account: "business" },
  { id: sampleExpenseStory.expense.id, label: sampleExpenseStory.expense.expense, amount: sampleExpenseStory.expense.amount, currency: "DOP", date: "2026-10-06", kind: "expense", account: "business" },
  { id: "expense-317", label: { es: "Materiales del taller", en: "Workshop supplies" }, amount: 4500, currency: "DOP", date: "2026-10-05", kind: "expense", account: "business" },
  { id: "owner-101", label: { es: "Aporte de la dueña", en: "Owner contribution" }, amount: 10000, currency: "DOP", date: "2026-10-04", kind: "owner-contribution", account: "business" },
  { id: "owner-102", label: { es: "Retiro de la dueña", en: "Owner withdrawal" }, amount: 3000, currency: "DOP", date: "2026-10-05", kind: "owner-withdrawal", account: "business" },
  { id: "expense-318", label: { es: "Internet del local", en: "Shop internet" }, amount: 1600, currency: "DOP", date: "2026-10-06", kind: "expense", account: "personal", linkedId: "personal-064" },
];
export const exampleDebt = { balance: 36000, installment: 6000, date: "2026-10-20", label: { es: "Equipo del taller", en: "Workshop equipment" } } as const;
const supplier = samplePriorities.find((record) => record.kind === "payable")!;
export const exampleExpectations = [
  { id: "supplier-208", label: { es: supplier.supplier, en: supplier.supplier }, amount: supplier.amount, direction: "out", date: "2026-10-07", status: "scheduled" },
  { id: "rent", label: { es: "Alquiler del local", en: "Shop rent" }, amount: 20000, direction: "out", date: "2026-10-12", status: "scheduled" },
  { id: "collection-1024", label: { es: sampleInvoiceStory.customerName, en: sampleInvoiceStory.customerName }, amount: sampleInvoiceStory.invoice.amount - sampleInvoiceStory.payment, direction: "in", date: "2026-10-12", status: "expected" },
  { id: "debt", label: exampleDebt.label, amount: exampleDebt.installment, direction: "out", date: exampleDebt.date, status: "scheduled" },
] as const;
export const exampleBudgets = [
  { label: { es: "Transporte", en: "Transport" }, limit: 10000, movementIds: [sampleExpenseStory.expense.id] },
  { label: { es: "Materiales", en: "Supplies" }, limit: 8000, movementIds: ["expense-317"] },
  { label: { es: "Servicios", en: "Utilities" }, limit: 6000, movementIds: ["expense-318"] },
] as const;
export const exampleGoal = { saved: 15000, target: 30000, label: { es: "Reserva para equipos", en: "Equipment reserve" } } as const;
export function movementCashEffect(movement: MoneyMovement): number {
  if (movement.account !== "business") return 0;
  return movement.kind === "income" || movement.kind === "owner-contribution" ? movement.amount : -movement.amount;
}
export function accountSummary(currency: ExampleCurrency) {
  const account = exampleAccounts.find((item) => item.currency === currency)!;
  const movements = exampleMovements.filter((item) => item.currency === currency);
  const change = movements.reduce((total, movement) => total + movementCashEffect(movement), 0);
  return {
    opening: account.opening, change, cash: account.opening + change,
    income: movements.filter((item) => item.kind === "income").reduce((sum, item) => sum + item.amount, 0),
    expenses: movements.filter((item) => item.kind === "expense").reduce((sum, item) => sum + item.amount, 0),
  };
}
export function projectedCash(delayCollection: boolean) {
  const rows = exampleExpectations.filter((item) => !(delayCollection && item.direction === "in"));
  return rows.reduce((balance, item) => balance + (item.direction === "in" ? item.amount : -item.amount), accountSummary("DOP").cash);
}
export function budgetActual(ids: readonly string[]) {
  return exampleMovements.filter((item) => ids.includes(item.id) && item.kind === "expense").reduce((sum, item) => sum + item.amount, 0);
}
export function exampleMoney(value: number, currency: ExampleCurrency, locale: BusinessLocale) {
  return `${currency === "DOP" ? "RD$" : "US$"} ${new Intl.NumberFormat(locale === "es" ? "es-DO" : "en-US").format(value)}`;
}
export function exampleDate(date: string, locale: BusinessLocale) {
  return new Intl.DateTimeFormat(locale === "es" ? "es-DO" : "en-US", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${date}T12:00:00Z`));
}
