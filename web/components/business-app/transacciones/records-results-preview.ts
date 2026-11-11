import { currencyDigits, minorToDecimal } from "@/lib/money-entry";
import { customPeriod, todayIso, type Period } from "../business-format";
import type { ReviewFilter } from "./records-filter-preview-model";
import type { Money, RecordRow } from "./transacciones-model";
import type { DgiiChoice, Purchase606 } from "@/lib/business-reports-api";
import { EXPENSE_TYPES, PAYMENT_FORMS } from "../dossier-fixtures";

/** A sample row's stage, as the server would name a recorded row's: a blocker gained after approval, a missing 606 fact, a line ready for the TXT, or a line a downloaded TXT froze. */
export type PreviewWorkflow = "review" | "fiscal" | "ready" | "exported";
export type PreviewFinancialEligibility = "confirmed" | "unconfirmed" | "personal";
/** `dgii606` mirrors a live row's `dgii_606`: null for a record the 606 never lists, absent when the sample says nothing. `missing` mirrors `export_missing` on a `fiscal` row. */
export type PreviewRecordMetadata = { workflow: PreviewWorkflow; financialEligibility: PreviewFinancialEligibility; documentNumbers?: readonly string[]; dgii606?: Purchase606 | null; missing?: { export_missing: string; export_missing_several?: boolean } };

// This is a local illustration for the synthetic own Business, never a source adapter.
// The sample's one copy of the DGII names lives in dossier-fixtures; live rows read the server's label.
const expenseType = (code: string): DgiiChoice => ({ code, label: EXPENSE_TYPES[code] });
const paymentForm = (code: string): DgiiChoice => ({ code, label: PAYMENT_FORMS[code] });
const SERVICES = expenseType("02");
const COST_OF_SALES = expenseType("09");
const CARD = paymentForm("03");
const TRANSFER = paymentForm("02");
const FIXTURE_METADATA: Readonly<Record<string, PreviewRecordMetadata>> = {
  "gasto:exp-gas": { workflow: "fiscal", financialEligibility: "confirmed", dgii606: { expense_type: null, payment_form: TRANSFER }, missing: { export_missing: "expense_type_missing" } },
  "gasto:exp-hosting": { workflow: "exported", financialEligibility: "confirmed", documentNumbers: ["B0100000042"], dgii606: { expense_type: SERVICES, payment_form: CARD } },
  "gasto:exp-imprenta": { workflow: "fiscal", financialEligibility: "confirmed", dgii606: { expense_type: COST_OF_SALES, payment_form: null }, missing: { export_missing: "payment_method_missing" } },
  "gasto:exp-lunch": { workflow: "ready", financialEligibility: "personal", dgii606: null },
  "venta:exp-gas": { workflow: "ready", financialEligibility: "confirmed", dgii606: null },
  "venta:exp-hosting": { workflow: "ready", financialEligibility: "unconfirmed", dgii606: null },
  "venta:exp-lunch": { workflow: "ready", financialEligibility: "personal", dgii606: null },
  // The sample's own sales (search-fixtures): the two from late October already went out in an export.
  ...Object.fromEntries(Array.from({ length: 7 }, (_, index) => [`venta:venta-${index + 1}`, { workflow: index < 5 ? "ready" : "exported", financialEligibility: "confirmed", dgii606: null } satisfies PreviewRecordMetadata])),
};
export function previewRecordMetadata(row: RecordRow, businessId: string | null): PreviewRecordMetadata | null {
  return businessId === "fixture-space" ? FIXTURE_METADATA[`${row.kind}:${row.id}`] ?? null : null;
}
/** The tipos de gasto the sample rows carry, for the sample's filter editor; the live editor reads the server's catalogue instead. */
export const SAMPLE_EXPENSE_TYPES: readonly DgiiChoice[] = Object.values(FIXTURE_METADATA).flatMap((item) => item.dgii606?.expense_type ?? []).filter((choice, index, all) => all.findIndex((other) => other.code === choice.code) === index);
export function matchesPreviewExpenseType(row: RecordRow, businessId: string | null, selected: readonly string[]): boolean {
  if (!selected.length) return true;
  const purchase = previewRecordMetadata(row, businessId)?.dgii606;
  return Boolean(purchase) && selected.includes(purchase!.expense_type?.code ?? "missing");
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
  unknownWorkflow: number;
  excluded: SummaryExclusions;
  excludedByKind: { sales: SummaryExclusions; expenses: SummaryExclusions };
  sales: Money[];
  expenses: Money[];
};
export function summarizePreviewRecords(rows: readonly RecordRow[], businessId: string | null): RecordsResultsPreview {
  const result: RecordsResultsPreview = { count: rows.length, unknownWorkflow: 0, excluded: emptyExclusions(), excludedByKind: { sales: emptyExclusions(), expenses: emptyExclusions() }, sales: [], expenses: [] };
  const totals = { venta: new Map<string, bigint>(), gasto: new Map<string, bigint>() };
  for (const row of rows) {
    const exclude = (reason: keyof SummaryExclusions) => {
      result.excluded[reason] += 1;
      result.excludedByKind[row.kind === "venta" ? "sales" : "expenses"][reason] += 1;
    };
    const metadata = previewRecordMetadata(row, businessId);
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


const WORKFLOW_FILTER: Record<PreviewWorkflow, ReviewFilter> = { review: "review", fiscal: "fiscal", ready: "export", exported: "exported" };
export function matchesPreviewWorkflow(row: RecordRow, businessId: string | null, selected: readonly ReviewFilter[]): boolean {
  if (!selected.length) return true;
  const metadata = previewRecordMetadata(row, businessId);
  return metadata !== null && selected.includes(WORKFLOW_FILTER[metadata.workflow]);
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

export function matchesPreviewFiscalData(row: RecordRow, businessId: string | null, choice: "complete" | "missing" | null): boolean {
  if (choice === null) return true;
  const metadata = previewRecordMetadata(row, businessId);
  if (!metadata || row.marks.personal || metadata.financialEligibility !== "confirmed") return false;
  return choice === "missing" ? metadata.workflow === "fiscal" : metadata.workflow === "ready" || metadata.workflow === "exported";
}
