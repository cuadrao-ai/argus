import answer from "@/test-fixtures/records-default-report-answer.json";
import byFamily from "@/test-fixtures/records-columns-by-family.json";
import { reportAnswerSchema, reportColumnSchema } from "@/lib/business-reports-api";
import { reportPresentationToRecords } from "@/lib/business-reporting-wire";

export function sampleRecordsPreferences() {
  const report = reportAnswerSchema.parse(answer);
  return reportPresentationToRecords(report.presentation, report.effective_sort ?? "date_desc", report.columns);
}

/** The columns the server offers each tab, recorded from the backend for the sample preview. */
export function sampleRecordsColumns(family: "purchase" | "sale") {
  return reportColumnSchema.array().parse(byFamily[family]);
}
