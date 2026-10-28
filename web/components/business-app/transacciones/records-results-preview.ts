import { currencyDigits, minorToDecimal } from "@/lib/money-entry";
import { customPeriod, todayIso, type Period } from "../business-format";
import type { ReviewFilter } from "./records-filter-preview-model";
import type { Money, RecordRow } from "./transacciones-model";

export type PreviewWorkflow = "review" | "approval" | "ready";
export type PreviewFinancialEligibility = "confirmed" | "unconfirmed" | "personal";
export type PreviewRecordMetadata = { workflow: PreviewWorkflow; financialEligibility: PreviewFinancialEligibility; documentNumbers?: readonly string[] };

// This is a local illustration for the synthetic own Business, never a source adapter.
const FIXTURE_METADATA: Readonly<Record<string, PreviewRecordMetadata>> = {
  "gasto:exp-gas": { workflow: "review", financialEligibility: "confirmed" },
  "gasto:exp-hosting": { workflow: "ready", financialEligibility: "confirmed", documentNumbers: ["B0100000042"] },
  "gasto:exp-lunch": { workflow: "approval", financialEligibility: "personal" },
  "venta:exp-gas": { workflow: "ready", financialEligibility: "confirmed" },
  "venta:exp-hosting": { workflow: "approval", financialEligibility: "unconfirmed" },
  "venta:exp-lunch": { workflow: "review", financialEligibility: "personal" },
};
export function previewRecordMetadata(row: RecordRow, businessId: string | null): PreviewRecordMetadata | null {
  return businessId === "fixture-space" ? FIXTURE_METADATA[`${row.kind}:${row.id}`] ?? null : null;
}
export function exactMinor(money: Money): bigint | null {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(money.amount);
  const digits = currencyDigits(money.currency);
  if (!match || !money.currency || (match[3]?.length ?? 0) > digits) return null;
  const value = BigInt(match[2] + (match[3] ?? "").padEnd(digits, "0"));
  return match[1] === "-" ? -value : value;
}
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


const WORKFLOW_FILTER: Record<PreviewWorkflow, ReviewFilter> = { review: "review", approval: "approval", ready: "export" };
export function matchesPreviewWorkflow(row: RecordRow, businessId: string | null, selected: readonly ReviewFilter[]): boolean {
  if (!selected.length) return true;
  const metadata = previewRecordMetadata(row, businessId);
  return metadata !== null && selected.includes(WORKFLOW_FILTER[metadata.workflow]);
}
export function overviewPreviewCounts(rows: readonly RecordRow[] | null, businessId: string | null): Record<ReviewFilter, number | null> {
  const counts = { review: 0, approval: 0, export: 0 };
  if (!rows) return { review: null, approval: null, export: null };
  for (const row of rows) {
    const metadata = previewRecordMetadata(row, businessId);
    if (!metadata) return { review: null, approval: null, export: null };
    counts[WORKFLOW_FILTER[metadata.workflow]] += 1;
  }
  return counts;
}

type PreviewAllocation = { currency: string; total: string; payments: readonly string[] };
const FIXTURE_ALLOCATIONS: Readonly<Record<string, PreviewAllocation>> = {
  "gasto:exp-gas": { currency: "DOP", total: "2100.00", payments: ["1000.00", "200.00"] },
  "gasto:exp-hosting": { currency: "USD", total: "24.00", payments: ["12.00"] },
  "venta:exp-gas": { currency: "DOP", total: "2100.00", payments: ["1000.00", "400.00"] },
};
/** An empty currency is the server's unknown currency. A null total with a `known` amount is an incomplete server total. */
export type SettlementCurrency = { currency: string; total: string | null; known?: string | null; settled: string | null; balance: string | null };
export type SettlementSummary = { currencies: SettlementCurrency[]; exclusions: SummaryExclusions };
export function summarizeSettlementPreview(rows: readonly RecordRow[], businessId: string | null, kind: RecordRow["kind"]): SettlementSummary {
  const matching = rows.filter((row) => row.kind === kind);
  const summary = summarizePreviewRecords(matching, businessId);
  const key = kind === "venta" ? "sales" : "expenses";
  const settlements = new Map<string, bigint | null>();
  for (const row of matching) {
    const metadata = previewRecordMetadata(row, businessId);
    const amount = exactMinor(row.money);
    if (!metadata || metadata.financialEligibility !== "confirmed" || row.marks.personal || amount === null) continue;
    const total = amount < BigInt(0) ? -amount : amount;
    const allocation = FIXTURE_ALLOCATIONS[`${row.kind}:${row.id}`];
    const expected = allocation ? exactMinor({ currency: allocation.currency, amount: allocation.total }) : null;
    const payments = allocation?.payments.map((payment) => exactMinor({ currency: allocation.currency, amount: payment })) ?? [];
    const paid = payments.reduce<bigint | null>((sum, value) => sum === null || value === null || value < BigInt(0) ? null : sum + value, BigInt(0));
    const valid = allocation && allocation.currency === row.money.currency && expected === total && paid !== null && paid <= total;
    const previous = settlements.get(row.money.currency);
    settlements.set(row.money.currency, previous === null || !valid ? null : (previous ?? BigInt(0)) + paid!);
  }
  return {
    currencies: summary[key].map((money) => {
      const settled = settlements.get(money.currency);
      return { currency: money.currency, total: money.amount, settled: settled == null ? null : minorToDecimal(settled, money.currency), balance: settled == null ? null : minorToDecimal(exactMinor(money)! - settled, money.currency) };
    }),
    exclusions: summary.excludedByKind[key],
  };
}


export function matchesPreviewPeriod(row: RecordRow, period: Period): boolean {
  if (period.key === "all") return true;
  return customPeriod(row.occurredOn, row.occurredOn) !== null && row.occurredOn >= period.from && row.occurredOn <= (period.to ?? todayIso());
}
