import { formatDay } from "@/components/business-app/business-format";

/** The server supplies every bound. Locale files own the sentences. */
type Translate = (key: string, fallback: string, options?: Record<string, unknown>) => string;
type DateReason = { code: string; min_date?: string; field?: string };
const codes = new Set(["business_date_before_minimum", "business_date_after_today"]);
const fields: Record<string, string> = {
  due_on: "business.invoicing_preview.due_date",
  issued_on: "business.invoicing_preview.issue_date",
  settled_on: "business.dgii.field.paid_on",
  covered_through: "business.dossier.field.occurred_on",
  occurred_on: "business.dossier.field.occurred_on",
  paid_on: "business.dgii.field.paid_on",
  withheld_on: "business.dgii.field.withheld_on",
};
const object = (value: unknown): Record<string, unknown> => typeof value === "object" && value !== null ? value as Record<string, unknown> : {};

function reasonOf(error: unknown): DateReason | null {
  const value = object(error), context = object(value.context);
  if (typeof value.code === "string" && codes.has(value.code)) {
    return { code: value.code, min_date: (value.min_date ?? context.min_date) as string | undefined, field: (value.field ?? context.field) as string | undefined };
  }
  if (Array.isArray(context.errors)) {
    for (const item of context.errors) {
      const problem = object(item), metadata = object(problem.ctx);
      if (typeof problem.type !== "string" || !codes.has(problem.type)) continue;
      const location = Array.isArray(problem.loc) ? problem.loc : [];
      return { code: problem.type, min_date: metadata.min_date as string | undefined, field: location.findLast((part) => typeof part === "string" && part in fields) as string | undefined };
    }
  }
  return value.cause && value.cause !== error ? reasonOf(value.cause) : null;
}

export function businessDateMessage(error: unknown, t: Translate, locale: string, label?: string): string | null {
  const reason = reasonOf(error);
  if (!reason || (reason.code === "business_date_before_minimum" && typeof reason.min_date !== "string")) return null;
  const field = label ?? t(fields[reason.field ?? ""] ?? fields.occurred_on, "");
  return t(`business.accepted_dates.${reason.code}`, "", { field, min_date: reason.min_date && formatDay(reason.min_date, locale) });
}
