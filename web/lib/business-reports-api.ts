import { z } from "zod";
import { ARGUS_API_BASE_URL, argusApiRequestHeaders, serverRequestId } from "./argus-api-transport";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "./browser-auth-generation";
import { getChosenGrant, subscribeChosenGrant } from "./business-grant";
import { authenticatedRequestHeaders } from "./chat-auth-ownership";

const day = z.iso.date();
const decimal = z.string().regex(/^-?\d+(?:\.\d+)?$/);
const count = z.number().int().nonnegative();
const family = z.enum(["sale", "purchase"]);
const stage = z.enum(["needs_review", "awaiting_approval", "ready_for_export"]);
const documentKind = z.enum(["invoice", "receipt", "credit_note", "unknown"]);
const effect = z.enum(["known", "unknown", "unsupported"]);
const viewName = z.string().trim().refine((value) => Array.from(value).length >= 1 && Array.from(value).length <= 120);
export const reportSortSchema = z.enum(["date_desc", "date_asc", "name_asc", "name_desc", "amount_asc", "amount_desc"]);
export const REPORT_PRESENTATION_KEYS = ["counterparty", "date", "gross_amount", "currency", "family", "category", "stage", "note", "attachment", "funding"] as const;
const presentationKey = z.enum(REPORT_PRESENTATION_KEYS);
export const reportPresentationSchema = z.strictObject({
  order: z.array(presentationKey).length(10).refine((values) => values[0] === "counterparty" && new Set(values).size === 10).default([...REPORT_PRESENTATION_KEYS]),
  hidden: z.array(presentationKey).refine((values) => new Set(values).size === values.length && !values.some((key) => ["counterparty", "gross_amount", "currency"].includes(key))).default(["funding"]),
  density: z.union([z.literal(40), z.literal(48), z.literal(56)]).default(48),
});
const pageSize = z.union([z.literal(25), z.literal(50), z.literal(100)]);
const column = z.enum(["date", "family", "stage", "counterparty", "currency", "gross_amount", "recorded_amount", "proposed_amount", "category", "funding", "document_kind", "fiscal_classification", "note"]);
export const reportPeriodSchema = z.discriminatedUnion("kind", [
  z.strictObject({ kind: z.literal("custom"), from_date: day, to_date: day }).refine((value) => value.from_date <= value.to_date),
  z.strictObject({ kind: z.enum(["all", "this_month", "last_month", "this_year"]), from_date: z.null().optional(), to_date: z.null().optional() }),
]);
export const reportFiltersSchema = z.strictObject({
  q: z.string().refine((value) => Array.from(value).length <= 200).default(""), period: reportPeriodSchema.default({ kind: "all" }),
  record_families: z.array(family).default([]), review_stages: z.array(stage).default([]),
  has_document: z.boolean().nullable().default(null), currencies: z.array(z.string().regex(/^[A-Z]{3}$/)).max(200).default([]),
  amount_min: decimal.nullable().default(null), amount_max: decimal.nullable().default(null),
  counterparties: z.array(z.string().min(1).max(128)).max(200).default([]), categories: z.array(z.string().min(1).max(128)).max(200).default([]),
  funding_sources: z.array(z.string().min(1).max(128)).max(200).default([]), document_kinds: z.array(documentKind).default([]),
  fiscal_classifications: z.array(z.string().min(1).max(128)).max(100).default([]),
});
const reportRecipeV1Schema = z.strictObject({
  schema_version: z.literal(1).default(1), filters: reportFiltersSchema.default(() => reportFiltersSchema.parse({})),
  columns: z.array(column).min(1).refine((values) => new Set(values).size === values.length).default(["date", "family", "stage", "counterparty", "currency", "gross_amount"]),
  sort: z.literal("date_desc").default("date_desc"),
});
const reportRecipeV2Schema = reportRecipeV1Schema.extend({
  schema_version: z.literal(2), sort: reportSortSchema.default("date_desc"),
  presentation: reportPresentationSchema.default(() => reportPresentationSchema.parse({})), page_size: pageSize.default(25),
});
export const reportRecipeSchema = z.union([reportRecipeV1Schema, reportRecipeV2Schema]);
export const reportRequestSchema = z.union([
  reportRecipeV1Schema.extend({ page: z.number().int().positive().default(1), page_size: pageSize.default(25) }),
  reportRecipeV2Schema.extend({ page: z.number().int().positive().default(1) }),
]);
export const reportAttachmentSourceSchema = z.object({
  source_id: z.string(), receipt_id: z.string().nullable(), filename: z.string().nullable(), media_type: z.string().nullable(), source_available: z.boolean(), download_available: z.boolean(),
});
export const reportRecordSchema = z.object({
  row_id: z.string().min(1), draft_id: z.string().nullable(), linked_activity_ids: z.array(z.string()), revision: count,
  report_date: day.nullable(), date_basis: z.enum(["document_issue", "activity_effective"]), family: family.nullable(), stage: stage.nullable(),
  technical_state: z.string().nullable(), workflow_blockers: z.array(z.string()), currency: z.string().nullable(), gross_amount: decimal.nullable(),
  recorded_amount: decimal.nullable(), recorded_currency: z.string().nullable(), proposed_amount: decimal.nullable(), money_kind: z.string(),
  money_effect: effect, adjustment_effect: effect.nullable(), counterparty: z.string().nullable(), counterparty_key: z.string().nullable(),
  category_key: z.string(), funding_key: z.string().nullable(), funding_label: z.string().nullable(), funding_kind: z.string().nullable(),
  has_document: z.boolean(), document_kind: documentKind, fiscal_classification: z.string(), fiscal_number: z.string().nullable(),
  note: z.string().nullable(), settlement_status: z.string().nullable(), dependency_fingerprint: z.string(),
  can_edit_note: z.boolean().optional(), can_append_supporting: z.boolean().optional(), annotation_unavailable_reason: z.string().nullable().optional(), attachment_sources: z.array(reportAttachmentSourceSchema).optional(),
});
export const reportTotalSchema = z.object({
  currency: z.string().nullable(), kind: z.string(), basis: z.enum(["recorded_activity_amount", "proposed_activity_amount", "document_gross_amount", "document_credit_adjustment", "document_family_amount"]),
  matching_count: count, known_amount_minor: z.number().int(), unknown_count: count, unsupported_count: count, complete: z.boolean(),
  amount_minor: z.number().int().nullable(), known_amount: decimal.nullable(), amount: decimal.nullable(),
});
export const reportAnswerSchema = z.object({
  items: z.array(reportRecordSchema), matching_count: count, page: z.number().int().positive(), page_size: z.union([z.literal(25), z.literal(50), z.literal(100)]), page_count: count,
  totals: z.array(reportTotalSchema), fingerprint: z.string().regex(/^[0-9a-f]{64}$/), captured_at: z.string(),
  resolved_period: z.object({ from_date: day.nullable(), to_date: day.nullable(), calendar: z.literal("America/Santo_Domingo") }),
  excluded_unknown_dates: count, counterparties: z.array(z.object({ key: z.string(), labels: z.array(z.string()) })), categories: z.array(z.string()),
  funding_sources: z.array(z.object({ key: z.string(), label: z.string().nullable(), kind: z.string().nullable() })), coverage_notes: z.array(z.string()),
  overview: z.object({ needs_review: count, awaiting_approval: count, ready_for_export: count }).optional(), effective_sort: reportSortSchema.optional(),
  sort_unavailable_reason: z.literal("amount_sort_requires_single_known_currency").nullable().optional(),
});
export const savedReportViewSchema = z.object({
  id: z.string().uuid(), name: viewName, recipe: reportRecipeSchema, version: z.number().int().positive(), created_at: z.string(), updated_at: z.string(),
});
export type ReportPeriod = z.infer<typeof reportPeriodSchema>;
export type ReportPresentation = z.infer<typeof reportPresentationSchema>;
export type ReportSort = z.infer<typeof reportSortSchema>;
export type ReportFilters = z.infer<typeof reportFiltersSchema>;
export type ReportRecipe = z.infer<typeof reportRecipeSchema>;
export type ReportRequest = z.infer<typeof reportRequestSchema>;
export type ReportRecord = z.infer<typeof reportRecordSchema>;
export type ReportTotal = z.infer<typeof reportTotalSchema>;
export type ReportAnswer = z.infer<typeof reportAnswerSchema>;
export type SavedReportView = z.infer<typeof savedReportViewSchema>;
export type ReportScope = Readonly<{ userId: string; businessId: string; grantId: string | null }>;
export type ReportProblem = Error & { status?: number; code?: string; requestId?: string };

export class ReportScopeChanged extends Error {
  readonly code = "business_report_scope_changed";
  constructor() { super("Business report scope changed"); }
}

async function request<T>(scope: ReportScope, path: string, options: RequestInit, consume: (response: Response) => Promise<T>): Promise<T> {
  const generation = browserAuthGeneration();
  let selectionChanged = false;
  const unsubscribe = subscribeChosenGrant(() => { if (getChosenGrant() !== scope.grantId) selectionChanged = true; });
  const assertScope = () => {
    options.signal?.throwIfAborted();
    requireBrowserAuthGeneration(generation);
    if (selectionChanged || getChosenGrant() !== scope.grantId) throw new ReportScopeChanged();
  };
  try {
    assertScope();
    const auth = await authenticatedRequestHeaders(scope.userId);
    assertScope();
    const response = await fetch(`${ARGUS_API_BASE_URL}${path}`, { ...options, cache: "no-store", credentials: "omit", headers: argusApiRequestHeaders(options.headers, auth, path) });
    assertScope();
    if (!response.ok) {
      const raw: unknown = await response.json().catch(() => ({}));
      assertScope();
      const body = z.record(z.string(), z.unknown()).catch({}).parse(raw);
      const detail = z.record(z.string(), z.unknown()).catch({}).parse(body.detail);
      const error: ReportProblem = new Error(typeof detail.title === "string" ? detail.title : "Business report request failed");
      error.status = response.status;
      error.code = String(detail.code ?? body.code ?? "unknown");
      error.requestId = serverRequestId(response, body);
      throw error;
    }
    const value = await consume(response);
    assertScope();
    return value;
  } finally { unsubscribe(); }
}

async function json<T>(scope: ReportScope, path: string, schema: z.ZodType<T>, options: RequestInit = {}): Promise<T> {
  return request(scope, path, options, async (response) => schema.parse(await response.json()));
}

export async function queryBusinessReport(scope: ReportScope, report: ReportRequest, signal?: AbortSignal): Promise<ReportAnswer> {
  return json(scope, "/business/reports/query", reportAnswerSchema, { method: "POST", body: JSON.stringify(reportRequestSchema.parse(report)), signal });
}
export async function exportBusinessReport(scope: ReportScope, report: ReportRequest, fingerprint: string, signal?: AbortSignal): Promise<Blob> {
  const body = z.strictObject({ report: reportRequestSchema, expected_fingerprint: z.string().regex(/^[0-9a-f]{64}$/) }).parse({ report, expected_fingerprint: fingerprint });
  return request(scope, "/business/reports/export", { method: "POST", body: JSON.stringify(body), signal }, async (response) => {
    if (response.headers.get("Content-Type")?.split(";")[0].trim() !== "application/zip") throw new Error("Invalid Business report archive");
    return response.blob();
  });
}
export function listBusinessReportViews(scope: ReportScope, signal?: AbortSignal): Promise<SavedReportView[]> {
  return json(scope, "/business/report-views", z.array(savedReportViewSchema), { signal });
}
const viewWriteSchema = z.strictObject({ name: viewName, recipe: reportRecipeSchema });
export type ReportViewWrite = z.infer<typeof viewWriteSchema>;
export type ReportViewCommand =
  | { kind: "create"; key: string; body: ReportViewWrite }
  | { kind: "update"; key: string; id: string; body: ReportViewWrite & { expected_version: number } }
  | { kind: "delete"; key: string; id: string; body: { expected_version: number } };
export async function mutateBusinessReportView(scope: ReportScope, command: ReportViewCommand, signal?: AbortSignal): Promise<SavedReportView | null> {
  const key = z.string().min(1).max(200).parse(command.key);
  const version = z.strictObject({ expected_version: z.number().int().positive() });
  const body = command.kind === "create" ? viewWriteSchema.parse(command.body) : command.kind === "update" ? viewWriteSchema.extend(version.shape).parse(command.body) : version.parse(command.body);
  const suffix = command.kind === "create" ? "" : `/${encodeURIComponent(z.string().uuid().parse(command.id))}`;
  return request(scope, `/business/report-views${suffix}`, { method: { create: "POST", update: "PATCH", delete: "DELETE" }[command.kind], headers: { "Idempotency-Key": key }, body: JSON.stringify(body), signal }, async (response) => command.kind === "delete" ? null : savedReportViewSchema.parse(await response.json()));
}

const annotationDossierSchema = z.object({
  draft_id: z.string().uuid(), version: count, current_note: z.string().nullable(), note_edit_available: z.boolean(), supporting_append_available: z.boolean(), annotation_unavailable_reason: z.string().nullable(),
}).passthrough();
const noteResultSchema = z.object({ draft_id: z.string().uuid(), version: count, note: z.string() });
const noteMutationSchema = z.object({ result: noteResultSchema, dossier: annotationDossierSchema });
const supportingMutationSchema = z.object({
  result: z.object({ draft_id: z.string().uuid(), version: count, outcome: z.enum(["appended", "duplicate"]), source_id: z.string().uuid(), receipt_id: z.string().uuid(), sha256: z.string().regex(/^[0-9a-f]{64}$/) }), dossier: annotationDossierSchema,
});
export type NoteMutationAnswer = z.infer<typeof noteMutationSchema>;
export type SupportingMutationAnswer = z.infer<typeof supportingMutationSchema>;
export type CurrentNoteCommand = { draftId: string; expectedVersion: number; note: string; key: string };
export type SupportingFileCommand = { draftId: string; expectedVersion: number; file: File; key: string };
const annotationKey = z.string().min(1).max(80);
export async function setBusinessReportCurrentNote(scope: ReportScope, command: CurrentNoteCommand, signal?: AbortSignal): Promise<NoteMutationAnswer> {
  const id = z.string().uuid().parse(command.draftId);
  const body = z.strictObject({ expected_version: count, note: z.string().refine((value) => Array.from(value).length <= 500) }).parse({ expected_version: command.expectedVersion, note: command.note });
  return json(scope, `/business/drafts/${encodeURIComponent(id)}/current-note`, noteMutationSchema, { method: "PUT", headers: { "Idempotency-Key": annotationKey.parse(command.key) }, body: JSON.stringify(body), signal });
}
export async function appendBusinessReportSupportingFile(scope: ReportScope, command: SupportingFileCommand, signal?: AbortSignal): Promise<SupportingMutationAnswer> {
  const id = z.string().uuid().parse(command.draftId);
  return json(scope, `/business/drafts/${encodeURIComponent(id)}/supporting-files`, supportingMutationSchema, {
    method: "POST", headers: { "Idempotency-Key": annotationKey.parse(command.key), "X-Draft-Version": String(count.parse(command.expectedVersion)), "X-Document-Filename": encodeURIComponent(command.file.name), "Content-Type": command.file.type }, body: command.file, signal,
  });
}
