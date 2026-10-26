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
export const SUMMARY_METRICS = ["sales", "expenses"] as const;
export type SummaryMetric = typeof SUMMARY_METRICS[number];
export const DEFAULT_SUMMARY_METRICS: readonly SummaryMetric[] = ["sales", "expenses"];
export type SummaryExclusions = { unconfirmed: number; personal: number; unavailable: number };
const emptyExclusions = (): SummaryExclusions => ({ unconfirmed: 0, personal: 0, unavailable: 0 });
export type RecordsResultsPreview = {
  count: number;
  review: number;
  unknownWorkflow: number;
  excluded: SummaryExclusions;
  excludedByKind: { sales: SummaryExclusions; expenses: SummaryExclusions };
  sales: Money[];
  expenses: Money[];
};
export function summarizePreviewRecords(rows: readonly RecordRow[], businessId: string | null): RecordsResultsPreview {
  const result: RecordsResultsPreview = { count: rows.length, review: 0, unknownWorkflow: 0, excluded: emptyExclusions(), excludedByKind: { sales: emptyExclusions(), expenses: emptyExclusions() }, sales: [], expenses: [] };
  const totals = { venta: new Map<string, bigint>(), gasto: new Map<string, bigint>() };
  for (const row of rows) {
    const exclude = (reason: keyof SummaryExclusions) => {
      result.excluded[reason] += 1;
      result.excludedByKind[row.kind === "venta" ? "sales" : "expenses"][reason] += 1;
    };
    const metadata = previewRecordMetadata(row, businessId);
    if (metadata?.workflow === "review") result.review += 1;
    if (!metadata) result.unknownWorkflow += 1;
    if (!metadata) { exclude("unavailable"); continue; }
    if (row.marks.personal) { exclude("personal"); continue; }
    if (metadata.financialEligibility !== "confirmed") { exclude(metadata.financialEligibility); continue; }
    const amount = exactMinor(row.money);
    if (amount === null) { exclude("unavailable"); continue; }
    const absolute = amount < BigInt(0) ? -amount : amount;
    totals[row.kind].set(row.money.currency, (totals[row.kind].get(row.money.currency) ?? BigInt(0)) + absolute);
  }
  const money = (values: Map<string, bigint>) => [...values.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([currency, minor]) => ({ currency, amount: minorToDecimal(minor, currency) }));
  result.sales = money(totals.venta); result.expenses = money(totals.gasto);
  return result;
}
