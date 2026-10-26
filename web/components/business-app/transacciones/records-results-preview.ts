import { currencyDigits, minorToDecimal } from "@/lib/money-entry";
import type { Money, RecordRow } from "./transacciones-model";

export type PreviewWorkflow = "review" | "approval" | "ready";
export type PreviewFinancialEligibility = "confirmed" | "unconfirmed" | "personal";
export type PreviewRecordMetadata = { workflow: PreviewWorkflow; financialEligibility: PreviewFinancialEligibility };

// This is a local illustration for the synthetic own Business, never a source adapter.
const FIXTURE_METADATA: Readonly<Record<string, PreviewRecordMetadata>> = {
  "gasto:exp-gas": { workflow: "review", financialEligibility: "confirmed" },
  "gasto:exp-hosting": { workflow: "ready", financialEligibility: "confirmed" },
  "gasto:exp-lunch": { workflow: "approval", financialEligibility: "personal" },
  "venta:exp-gas": { workflow: "ready", financialEligibility: "confirmed" },
  "venta:exp-hosting": { workflow: "approval", financialEligibility: "unconfirmed" },
  "venta:exp-lunch": { workflow: "review", financialEligibility: "personal" },
};
export function previewRecordMetadata(row: RecordRow, businessId: string | null): PreviewRecordMetadata | null {
  return businessId === "fixture-space" ? FIXTURE_METADATA[`${row.kind}:${row.id}`] ?? null : null;
}
function exactMinor(money: Money): bigint | null {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(money.amount);
  const digits = currencyDigits(money.currency);
  if (!match || !money.currency || (match[3]?.length ?? 0) > digits) return null;
  const value = BigInt(match[2] + (match[3] ?? "").padEnd(digits, "0"));
  return match[1] === "-" ? -value : value;
}
export type RecordsResultsPreview = {
  count: number;
  review: number;
  unknownWorkflow: number;
  excluded: { unconfirmed: number; personal: number; unavailable: number };
  sales: Money[];
  expenses: Money[];
};
export function summarizePreviewRecords(rows: readonly RecordRow[], businessId: string | null): RecordsResultsPreview {
  const result: RecordsResultsPreview = { count: rows.length, review: 0, unknownWorkflow: 0, excluded: { unconfirmed: 0, personal: 0, unavailable: 0 }, sales: [], expenses: [] };
  const totals = { venta: new Map<string, bigint>(), gasto: new Map<string, bigint>() };
  for (const row of rows) {
    const metadata = previewRecordMetadata(row, businessId);
    if (metadata?.workflow === "review") result.review += 1;
    if (!metadata) result.unknownWorkflow += 1;
    if (!metadata) { result.excluded.unavailable += 1; continue; }
    if (row.marks.personal) { result.excluded.personal += 1; continue; }
    if (metadata.financialEligibility !== "confirmed") { result.excluded[metadata.financialEligibility] += 1; continue; }
    const amount = exactMinor(row.money);
    if (amount === null) { result.excluded.unavailable += 1; continue; }
    const absolute = amount < BigInt(0) ? -amount : amount;
    totals[row.kind].set(row.money.currency, (totals[row.kind].get(row.money.currency) ?? BigInt(0)) + absolute);
  }
  const money = (values: Map<string, bigint>) => [...values.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([currency, minor]) => ({ currency, amount: minorToDecimal(minor, currency) }));
  result.sales = money(totals.venta); result.expenses = money(totals.gasto);
  return result;
}
