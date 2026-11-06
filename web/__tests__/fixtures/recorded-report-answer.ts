import answer from "@/test-fixtures/records-default-report-answer.json";
import { reportAnswerSchema } from "@/lib/business-reports-api";

export const recordedReportAnswer = reportAnswerSchema.parse(answer);
