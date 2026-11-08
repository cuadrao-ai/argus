import { minorToDecimal } from "@/lib/money-entry";
import type { ReportAnswer, ReportFiscalTotal, ReportTotal } from "@/lib/business-reports-api";
import type { BusinessDataSource } from "../business-data";
import { exactMinor, matchesPreviewWorkflow, previewRecordMetadata, summarizePreviewRecords, type SettlementSummary } from "./records-results-preview";
import type { RecordRow } from "./transacciones-model";

type FiscalSample = { currency: string; total: string; itbis: string; goods: string | null; services: string | null };
const FISCAL_SAMPLES: Readonly<Record<string, FiscalSample>> = {
  "exp-gas": { currency: "DOP", total: "2100.00", itbis: "320.34", goods: "1779.66", services: null },
  "exp-imprenta": { currency: "DOP", total: "4800.00", itbis: "732.20", goods: null, services: "4067.80" },
  "exp-hosting": { currency: "USD", total: "24.00", itbis: "0.00", goods: null, services: "24.00" },
};
type SampleOverview = { answer: Pick<ReportAnswer, "matching_count" | "totals" | "fiscal_totals">; fiscalCount: number; purchaseSummary: SettlementSummary };

export function sampleRecordsOverview({ sourceMode, businessId, rows }: { sourceMode: BusinessDataSource["mode"]; businessId: string | null; rows: readonly RecordRow[] }): SampleOverview | undefined {
  if (sourceMode !== "fixture" || businessId !== "fixture-space") return undefined;
  const purchases = rows.filter((row) => row.kind === "gasto" && !row.marks.personal && previewRecordMetadata(row, businessId)?.financialEligibility !== "personal");
  const totals: ReportTotal[] = [];
  const fiscalTotals: ReportFiscalTotal[] = [];
  const currencies = [...new Set(purchases.map((row) => row.money.currency))].sort();
  for (const currency of currencies) {
    const matching = purchases.filter((row) => row.money.currency === currency);
    const summary = summarizePreviewRecords(matching, businessId);
    const known = summary.expenses[0]?.amount ?? minorToDecimal(BigInt(0), currency);
    const knownMinor = exactMinor({ currency, amount: known }) ?? BigInt(0);
    const unknown = summary.excluded.unavailable + summary.excluded.unconfirmed;
    totals.push({ currency, kind: "expense", basis: "document_family_amount", matching_count: matching.length, known_amount_minor: Number(knownMinor), unknown_count: unknown, unsupported_count: 0, complete: unknown === 0, amount_minor: unknown === 0 ? Number(knownMinor) : null, known_amount: known, amount: unknown === 0 ? known : null });
    for (const basis of ["itbis", "goods", "services"] as const) {
      let sum = BigInt(0);
      let populated = 0;
      for (const row of matching) {
        const sample = FISCAL_SAMPLES[row.id];
        const total = exactMinor(row.money);
        if (!sample || sample.currency !== currency || total === null || (total < BigInt(0) ? -total : total) !== exactMinor({ currency, amount: sample.total })) continue;
        const amount = sample[basis];
        if (amount === null) continue;
        const minor = exactMinor({ currency, amount });
        if (minor === null) continue;
        sum += minor;
        populated++;
      }
      const complete = populated === matching.length;
      const amount = minorToDecimal(sum, currency);
      fiscalTotals.push({ currency, kind: "expense", basis, applicable_count: matching.length, populated_count: populated, known_amount_minor: Number(sum), unknown_count: matching.length - populated, unsupported_count: 0, complete, amount_minor: complete ? Number(sum) : null, known_amount: amount, amount: complete ? amount : null });
    }
  }
  return {
    answer: { matching_count: rows.length, totals, fiscal_totals: fiscalTotals },
    fiscalCount: rows.filter((row) => matchesPreviewWorkflow(row, businessId, ["fiscal"])).length,
    purchaseSummary: {
      currencies: totals.map((line) => ({ currency: line.currency ?? "", total: line.amount, known: line.known_amount, settled: null, balance: null })),
      exclusions: summarizePreviewRecords(rows.filter((row) => row.kind === "gasto"), businessId).excludedByKind.expenses,
    },
  };
}
