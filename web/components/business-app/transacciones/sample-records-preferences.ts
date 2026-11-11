import answer from "@/test-fixtures/records-default-report-answer.json";
import { reportAnswerSchema } from "@/lib/business-reports-api";
import { reportPresentationToRecords } from "@/lib/business-reporting-wire";

export function sampleRecordsPreferences() {
  const report = reportAnswerSchema.parse(answer);
  return reportPresentationToRecords(report.presentation, report.effective_sort ?? "date_desc");
}
