import { z } from "zod";
import i18n from "i18next";
import { CUADRAO_API_BASE_URL, argusApiRequestHeaders, serverRequestId } from "./argus-api-transport";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "./browser-auth-generation";
import { getChosenGrant, subscribeChosenGrant } from "./business-grant";
import { authenticatedRequestHeaders } from "./chat-auth-ownership";

const day = z.iso.date();
const decimal = z.string().regex(/^-?\d+(?:\.\d+)?$/);
const count = z.number().int().nonnegative();
// Decimal text owns money. Large legacy JSON minor-unit numbers remain unused metadata.
const minorNumber = z.number().refine(Number.isInteger);
const family = z.enum(["sale", "purchase"]);
/** A recorded row's place on the way to the DGII. A draft waits in the Bandeja and is no row here. */
const stage = z.enum(["needs_review", "needs_fiscal_data", "ready_for_export", "exported"]);
export type ReportStage = z.infer<typeof stage>;
const documentKind = z.enum(["invoice", "receipt", "credit_note", "unknown"]);
export const recordsCurrencySchema = z.enum(["DOP", "USD", "EUR"]);
export type RecordsCurrency = z.infer<typeof recordsCurrencySchema>;
/** The document kinds the server's projection names on a row, so Filtros offers only kinds a record can match. The contract still accepts the others. */
export const REPORT_DOCUMENT_KINDS = ["credit_note", "unknown"] as const satisfies readonly z.infer<typeof documentKind>[];
const effect = z.enum(["known", "unknown", "unsupported"]);
const viewName = z.string().trim().refine((value) => Array.from(value).length >= 1 && Array.from(value).length <= 120);
export const reportSortSchema = z.enum(["date_desc", "date_asc", "name_asc", "name_desc", "amount_asc", "amount_desc"]);
/** The server registry's column keys, the `Presentation` enum in docs/api/openapi.yaml. Cell renderers and layouts key on them; a test pins the two lists equal. */
export const REPORT_PRESENTATION_KEYS = ["counterparty_id", "counterparty", "fiscal_number", "date", "net_amount", "itbis_amount", "gross_amount", "stage", "note", "attachment", "expense_type", "payment_form", "funding"] as const;
export type ReportColumnKey = typeof REPORT_PRESENTATION_KEYS[number];
/** A layout as a request carries it. An old link's keys pass through; the server upgrades them and answers the layout the web keeps. */
export const reportPresentationSchema = z.strictObject({
  order: z.array(z.string()),
  hidden: z.array(z.string()),
  density: z.union([z.literal(40), z.literal(48), z.literal(56)]),
});
/** One column the table offers, with the rules the server gives it. `label_key` is a locale path. */
export const reportColumnSchema = z.object({ key: z.enum(REPORT_PRESENTATION_KEYS), label_key: z.string(), required: z.boolean(), pinned: z.boolean(), shown: z.boolean() });
const pageSize = z.union([z.literal(25), z.literal(50), z.literal(100)]);
export const reportPeriodSchema = z.discriminatedUnion("kind", [
  z.strictObject({ kind: z.literal("custom"), from_date: day, to_date: day }).refine((value) => value.from_date <= value.to_date),
  z.strictObject({ kind: z.enum(["all", "this_month", "last_month", "this_year", "latest_month"]), from_date: z.null().optional(), to_date: z.null().optional() }),
]);
export const reportFiltersSchema = z.strictObject({
  q: z.string().refine((value) => Array.from(value).length <= 200).default(""), period: reportPeriodSchema.default({ kind: "all" }),
  record_families: z.preprocess((value) => Array.isArray(value) && (value.length === 0 || value.length === 2 && value.includes("sale") && value.includes("purchase")) ? ["purchase"] : value, z.tuple([family]).default(["purchase"])),
  // A saved view or address bar may still name a stage the server dropped when drafts left Registros; it reads as no stage filter, never as a 422.
  review_stages: z.array(z.string()).default([]).transform((values): ReportStage[] => values.filter((value): value is ReportStage => stage.safeParse(value).success)),
  fiscal_data: z.enum(["complete", "missing"]).nullable().default(null),
  has_document: z.boolean().nullable().default(null), currencies: z.array(z.string().regex(/^[A-Z]{3}$/)).max(200).default([]),
  amount_min: decimal.nullable().default(null), amount_max: decimal.nullable().default(null),
  counterparties: z.array(z.string().min(1).max(128)).max(200).default([]),
  // Registros no longer offers the ledger category, so a saved view or address bar that still names one is read as none: a filter nobody can see or clear never hides rows.
  categories: z.array(z.string().min(1).max(128)).max(200).default([]).transform((): string[] => []),
  expense_types: z.array(z.string().min(1).max(16)).max(20).default([]),
  funding_sources: z.array(z.string().min(1).max(128)).max(200).default([]), document_kinds: z.array(documentKind).default([]),
  fiscal_classifications: z.array(z.string().min(1).max(128)).max(100).default([]),
}).transform((filters) => filters.record_families[0] === "sale" ? { ...filters, expense_types: [] } : filters);
const reportRecipeV1Schema = z.strictObject({
  schema_version: z.literal(1).default(1), filters: reportFiltersSchema.default(() => reportFiltersSchema.parse({})),
  sort: z.literal("date_desc").default("date_desc"),
});
const reportRecipeV2Schema = reportRecipeV1Schema.extend({
  schema_version: z.literal(2), sort: reportSortSchema.default("date_desc"),
  presentation: reportPresentationSchema.optional(), page_size: pageSize.default(25),
});
export const reportRecipeSchema = z.union([reportRecipeV1Schema, reportRecipeV2Schema]);
export const reportRequestSchema = z.union([
  reportRecipeV1Schema.extend({ page: z.number().int().positive().default(1), page_size: pageSize.default(25) }),
  reportRecipeV2Schema.extend({ page: z.number().int().positive().default(1) }),
]);
export const reportAttachmentSourceSchema = z.object({
  source_id: z.string(), receipt_id: z.string().nullable(), filename: z.string().nullable(), media_type: z.string().nullable(), source_available: z.boolean().nullable(), download_available: z.boolean(),
});
/** One 606 answer: its code and the name the DGII list gives it, as the server names it. */
export const dgiiChoiceSchema = z.object({ code: z.string().min(1), label: z.string().min(1) });
/** The two 606 answers a purchase carries. A null answer is still missing. */
export const purchase606Schema = z.object({ expense_type: dgiiChoiceSchema.nullable(), payment_form: dgiiChoiceSchema.nullable() });
export const reportRecordSchema = z.object({
  row_id: z.string().min(1), draft_id: z.string().nullable(), linked_activity_ids: z.array(z.string()), revision: count,
  report_date: day.nullable(), date_basis: z.enum(["document_issue", "activity_effective"]), family: family.nullable(), stage: stage.nullable(), fiscal_data: z.enum(["complete", "missing"]).nullable().optional(), export_missing: z.string().nullable().optional(), export_missing_several: z.boolean().optional(), export_line: z.boolean().optional(),
  technical_state: z.string().nullable(), workflow_blockers: z.array(z.string()), currency: z.string().nullable(), gross_amount: decimal.nullable(),
  net_amount: decimal.nullable().optional(), net_amount_source: z.enum(["read", "calculated", "edited"]).nullable().optional(), amounts_difference: decimal.nullable().optional(),
  inheritance: z.record(z.string(), z.object({ field: z.enum(["net_amount", "itbis", "legal_tip", "occurred_on"]), value: z.string().nullable(), inherited: z.boolean() })).optional(),
  itbis_amount: decimal.nullable().optional(), goods_amount: decimal.nullable().optional(), services_amount: decimal.nullable().optional(),
  recorded_amount: decimal.nullable(), recorded_currency: z.string().nullable(), proposed_amount: decimal.nullable(), money_kind: z.string(),
  money_effect: effect, adjustment_effect: effect.nullable(), counterparty: z.string().nullable(), counterparty_key: z.string().nullable(),
  category_key: z.string(), funding_key: z.string().nullable(), funding_label: z.string().nullable(), funding_kind: z.string().nullable(),
  has_document: z.boolean(), personal: z.boolean().optional(), dgii_606: purchase606Schema.nullable().optional(), document_kind: documentKind, fiscal_classification: z.string(), fiscal_number: z.string().nullable(),
  note: z.string().nullable(), settlement_status: z.string().nullable(), dependency_fingerprint: z.string(),
  can_edit_note: z.boolean().optional(), can_append_supporting: z.boolean().optional(), annotation_unavailable_reason: z.string().nullable().optional(), attachment_sources: z.array(reportAttachmentSourceSchema).optional(),
});
export const reportTotalSchema = z.object({
  currency: z.string().nullable(), kind: z.string(), basis: z.enum(["recorded_activity_amount", "proposed_activity_amount", "document_gross_amount", "document_credit_adjustment", "document_family_amount", "document_net_amount", "document_net_credit_adjustment", "document_net_family_amount"]),
  matching_count: count, known_amount_minor: minorNumber, unknown_count: count, unsupported_count: count, complete: z.boolean(),
  amount_minor: minorNumber.nullable(), known_amount: decimal.nullable(), amount: decimal.nullable(),
});
export const reportFiscalTotalSchema = z.object({
  currency: z.string().nullable(), kind: z.string(), basis: z.enum(["itbis", "goods", "services"]),
  applicable_count: count, populated_count: count, known_amount_minor: minorNumber,
  unknown_count: count, unsupported_count: count, complete: z.boolean(),
  amount_minor: minorNumber.nullable(), known_amount: decimal.nullable(), amount: decimal.nullable(),
});
export const reportAnswerSchema = z.object({
  presentation: reportPresentationSchema, columns: z.array(reportColumnSchema),
  items: z.array(reportRecordSchema), matching_count: count, page: z.number().int().positive(), page_size: z.union([z.literal(25), z.literal(50), z.literal(100)]), page_count: count,
  fiscal_totals: z.array(reportFiscalTotalSchema).optional(),
  totals: z.array(reportTotalSchema), fingerprint: z.string().regex(/^[0-9a-f]{64}$/), captured_at: z.string(),
  resolved_period: z.object({ from_date: day.nullable(), to_date: day.nullable(), calendar: z.literal("America/Santo_Domingo") }),
  excluded_unknown_dates: count, excluded_personal: z.object({ income: count, expense: count }).optional(),
  counterparties: z.array(z.object({ key: z.string(), labels: z.array(z.string()) })), categories: z.array(z.string()), expense_types: z.array(dgiiChoiceSchema).default([]),
  funding_sources: z.array(z.object({ key: z.string(), label: z.string().nullable(), kind: z.string().nullable() })), coverage_notes: z.array(z.string()),
  overview: z.object({ needs_review: count, needs_fiscal_data: count.optional(), ready_for_export: count, exported: count.optional(), export_lines: count.optional() }).optional(), effective_sort: reportSortSchema.optional(),
  sort_unavailable_reason: z.literal("amount_sort_requires_single_known_currency").nullable().optional(),
});
export const savedReportViewSchema = z.object({
  id: z.string().uuid(), name: viewName, recipe: reportRecipeSchema, version: z.number().int().positive(), created_at: z.string(), updated_at: z.string(),
});
export type ReportPeriod = z.infer<typeof reportPeriodSchema>;
export type ReportPresentation = z.infer<typeof reportPresentationSchema>;
export type ReportColumn = z.infer<typeof reportColumnSchema>;
export type ReportSort = z.infer<typeof reportSortSchema>;
export type ReportFilters = z.infer<typeof reportFiltersSchema>;
export type ReportRecipe = z.infer<typeof reportRecipeSchema>;
export type ReportRequest = z.infer<typeof reportRequestSchema>;
export type ReportRecord = z.infer<typeof reportRecordSchema>;
export type DgiiChoice = z.infer<typeof dgiiChoiceSchema>;
export type Purchase606 = z.infer<typeof purchase606Schema>;
export type ReportFiscalTotal = z.infer<typeof reportFiscalTotalSchema>;
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
    const deadline = AbortSignal.timeout(30_000);
    const signal = options.signal ? AbortSignal.any([options.signal, deadline]) : deadline;
    const response = await fetch(`${CUADRAO_API_BASE_URL}${path}`, { ...options, signal, cache: "no-store", credentials: "omit", headers: argusApiRequestHeaders(options.headers, auth, scope.grantId) });
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
/** One file column: `required` ones are always in the file. */
const exportColumnSchema = z.object({ key: z.string(), label_key: z.string(), required: z.boolean(), shown: z.boolean() });
const currencySelectionSchema = z.object({ record_count: count, currencies: z.array(z.string()), columns: z.array(exportColumnSchema).min(1) });
/** What the Registros export would hold, counted by the server before any file is built. */
export const exportPreviewSchema = z.object({
  table: z.object({
    current: currencySelectionSchema,
    /** Null while an amount range ties the export to the screen's currency. */
    all: currencySelectionSchema.nullable(),
  }),
  dgii: z.object({ form: z.enum(["606", "607"]), currency: z.string(), record_count: count, pending_count: count, pending_fiscal_count: count, pending_rate_count: count, pending_rate_currencies: z.array(z.string()), rnc_warning_count: count, rnc_supplier_count: count, rnc_suppliers: z.array(z.object({ name: z.string(), rnc: z.string(), estado: z.string(), status: z.enum(["rnc_inactive", "rnc_unverified"]), record_count: count })) }),
});
export type ExportPreview = z.infer<typeof exportPreviewSchema>;
export type RecordsExportChoice =
  | { mode: "table"; columns: string[]; currencies: "all" | "current"; format: "xlsx" | "csv" }
  | { mode: "dgii"; format: "xlsx" | "csv" };
export type RecordsExportFile = { blob: Blob; filename: string };
const FILE_TYPES = new Set(["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/csv"]);

export function previewRecordsExport(scope: ReportScope, report: ReportRequest, signal?: AbortSignal): Promise<ExportPreview> {
  return json(scope, "/business/reports/export/preview", exportPreviewSchema, { method: "POST", body: JSON.stringify({ report: reportRequestSchema.parse(report) }), signal });
}
export async function downloadRecordsExport(scope: ReportScope, report: ReportRequest, choice: RecordsExportChoice, signal?: AbortSignal): Promise<RecordsExportFile> {
  return request(scope, "/business/reports/export", { method: "POST", headers: { "Accept-Language": (i18n.resolvedLanguage || i18n.language)?.startsWith("en") ? "en" : "es-419" }, body: JSON.stringify({ report: reportRequestSchema.parse(report), ...choice }), signal }, async (response) => {
    const type = response.headers.get("Content-Type")?.split(";")[0].trim() ?? "";
    // The server names the file; the web saves it under that name.
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
    const filename = encoded ? decodeURIComponent(encoded) : /filename="([^"]+)"/.exec(disposition)?.[1];
    if (!FILE_TYPES.has(type) || !filename) throw new Error("Invalid Registros export file");
    return { blob: await response.blob(), filename };
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
export function getBusinessReportAnnotationDossier(scope: ReportScope, draftId: string, signal?: AbortSignal) {
  return json(scope, `/business/drafts/${encodeURIComponent(z.string().uuid().parse(draftId))}/dossier`, annotationDossierSchema, { signal });
}
export function downloadBusinessReportAttachment(scope: ReportScope, receiptId: string, signal?: AbortSignal): Promise<Blob> {
  return request(scope, `/business/receipts/${encodeURIComponent(z.string().uuid().parse(receiptId))}/source`, { signal }, (response) => response.blob());
}
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
