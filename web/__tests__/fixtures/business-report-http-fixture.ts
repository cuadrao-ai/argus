import { recordedReportAnswer } from "./recorded-report-answer";
import { reportAnswerSchema, reportRequestSchema, type ReportRecord, type ReportRequest, type ReportTotal } from "@/lib/business-reports-api";

export const fixtureId = (value: number) => `00000000-0000-4000-8000-${String(value).padStart(12, "0")}`;
export const FROZEN_REPORT_BACKEND = "eda4bb38ab2a195761523b084dbbfb6862e67c7e";
const text = (value: string) => value.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
const cents = (amount: string) => BigInt(amount.replace(".", ""));
const decimal = (minor: bigint) => `${minor / BigInt(100)}.${String(minor % BigInt(100)).padStart(2, "0")}`;
/** Mirrors the server's document-family totals for rows that are all document-dated: one total per currency and family, null amount while any row is unknown. */
export function documentFamilyTotals(rows: readonly ReportRecord[]): ReportTotal[] {
  const groups = new Map<string, { currency: string | null; kind: string; rows: ReportRecord[] }>();
  for (const row of rows) {
    const kind = row.family === "sale" ? "income" : row.family === "purchase" ? "expense" : "unknown";
    const key = `${row.currency}:${kind}`;
    groups.set(key, { currency: row.currency, kind, rows: [...groups.get(key)?.rows ?? [], row] });
  }
  return [...groups.values()].map(({ currency, kind, rows: members }) => {
    const known = members.reduce((sum, row) => row.gross_amount === null ? sum : sum + cents(row.gross_amount), BigInt(0));
    const unknown = members.filter((row) => row.gross_amount === null || currency === null).length;
    return { currency, kind, basis: "document_family_amount", matching_count: members.length, known_amount_minor: Number(known), unknown_count: unknown, unsupported_count: 0, complete: unknown === 0, amount_minor: unknown === 0 ? Number(known) : null, known_amount: currency ? decimal(known) : null, amount: currency && unknown === 0 ? decimal(known) : null };
  });
}

/** Mirrors the server's `latest_month`: the month of the newest dated row. */
function latestMonth(rows: readonly ReportRecord[]) {
  const newest = rows.flatMap((row) => row.report_date ?? []).sort().at(-1) ?? "2026-10-26";
  const [year, month] = newest.split("-").map(Number);
  return { from_date: `${newest.slice(0, 7)}-01`, to_date: new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10), calendar: "America/Santo_Domingo" };
}

export function createBusinessReportHttpFixture() {
  const records: ReportRecord[] = Array.from({ length: 126 }, (_, index) => ({
    row_id: `draft:${fixtureId(index + 1)}`, draft_id: fixtureId(index + 1), linked_activity_ids: [fixtureId(1000 + index)], revision: 3,
    report_date: index === 0 ? "1999-10-01" : index === 2 ? null : "2026-10-20", date_basis: "document_issue", family: index % 2 ? "sale" : "purchase", stage: index === 2 ? null : "needs_review", technical_state: index === 2 ? "processing" : null, workflow_blockers: [],
    currency: index === 2 ? null : index === 1 ? "USD" : "DOP", gross_amount: index === 2 ? null : "100.00", recorded_amount: index === 2 ? null : "100.00", recorded_currency: index === 2 ? null : index === 1 ? "USD" : "DOP", proposed_amount: null,
    money_kind: index % 2 ? "income" : "expense", money_effect: index === 2 ? "unknown" : "known", adjustment_effect: null,
    counterparty: index === 125 ? "José Peña" : `Proveedor ${index + 1}`, counterparty_key: null, category_key: "uncategorized", funding_key: null, funding_label: null, funding_kind: null,
    has_document: index === 0 || index === 125, document_kind: "unknown", fiscal_classification: "unknown", fiscal_number: null,
    // Sales carry no 606 answers; every third purchase still needs its tipo de gasto, every fifth its forma de pago.
    dgii_606: index % 2 ? null : { expense_type: index % 3 ? { code: "02", label: "Gastos por trabajos, suministros y servicios" } : null, payment_form: index % 5 ? { code: "01", label: "Efectivo" } : null },
    note: `Nota ${index + 1}`, settlement_status: "paid", dependency_fingerprint: `dependency-${index}`, can_edit_note: true, can_append_supporting: true, annotation_unavailable_reason: null,
    attachment_sources: index === 0 ? [{ source_id: fixtureId(500), receipt_id: fixtureId(700), filename: "Original sintético.pdf", media_type: "application/pdf", source_available: true, download_available: true }] : index === 125 ? [{ source_id: fixtureId(501), receipt_id: fixtureId(701), filename: "José Peña.pdf", media_type: "application/pdf", source_available: true, download_available: true }] : [],
  }));
  const calls: { path: string; method: string; headers: Headers; body: unknown }[] = [];
  const views: { id: string; name: string; recipe: unknown; version: number; created_at: string; updated_at: string }[] = [];
  let createdViews = 0;
  const storage = new Map([[fixtureId(700), new TextEncoder().encode("original synthetic bytes")], [fixtureId(701), new TextEncoder().encode("other synthetic bytes")]]);
  const replay = new Map<string, { signature: string; result: Record<string, unknown> }>();
  const controls = { presentation: recordedReportAnswer.presentation, exportFails: false, exports: [] as { mode: string }[], dgiiCurrency: "DOP", noteUncertain: false, fileUncertainAt: 0, files: 0, readOnly: false, originalAvailable: true, legacy: false, overview: { needs_review: 6, needs_fiscal_data: 60, ready_for_export: 40, exported: 20 } as Record<string, number>, reportForbidden: false, reportUnavailable: false };
  const dossier = (row: ReportRecord) => ({ draft_id: row.draft_id, version: row.revision, current_note: row.note, note_edit_available: !controls.readOnly, supporting_append_available: !controls.readOnly, annotation_unavailable_reason: controls.readOnly ? "business_annotation_unavailable" : null });
  const problem = (status: number, code: string) => Response.json({ code, detail: code }, { status });
  const matchingRecords = (report: ReportRequest) => {
    let matching = records.filter((row) => !report.filters.q || text(`${row.counterparty} ${row.note} ${row.attachment_sources?.map((source) => source.filename).join(" ")}`).includes(text(report.filters.q)));
    matching = matching.filter((row) => row.family === report.filters.record_families[0]);
    if (report.filters.fiscal_data !== null) matching = matching.filter((row) => row.fiscal_data === report.filters.fiscal_data);
    if (report.filters.counterparties.length) matching = matching.filter((row) => row.counterparty_key && report.filters.counterparties.includes(row.counterparty_key));
    if (report.filters.review_stages.length) matching = matching.filter((row) => row.stage && report.filters.review_stages.includes(row.stage));
    if (report.filters.currencies.length) matching = matching.filter((row) => row.currency && report.filters.currencies.includes(row.currency));
    if (report.filters.expense_types.length) matching = matching.filter((row) => row.dgii_606 && report.filters.expense_types.includes(row.dgii_606.expense_type?.code ?? "missing"));
    if (report.filters.document_kinds.length) matching = matching.filter((row) => report.filters.document_kinds.includes(row.document_kind));
    return matching;
  };
  const request = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    const path = new URL(String(input), "http://127.0.0.1").pathname;
    const method = init.method ?? "GET";
    const headers = new Headers(init.headers);
    const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
    calls.push({ path, method, headers, body });
    if (path.endsWith("/reports/query")) {
      if (controls.reportForbidden) return problem(403, "permission_denied");
      if (controls.reportUnavailable) return problem(503, "business_report_unavailable");
      const report = reportRequestSchema.parse(body);
      const matching = matchingRecords(report);
      const currencies = new Set(matching.map((row) => row.currency));
      const blocked = report.sort.startsWith("amount_") && (currencies.size !== 1 || currencies.has(null));
      const effective_sort = blocked ? "date_desc" : report.sort;
      if (effective_sort.startsWith("name_")) matching.sort((a, b) => (a.counterparty ?? "").localeCompare(b.counterparty ?? "") * (effective_sort.endsWith("asc") ? 1 : -1));
      const items = matching.slice((report.page - 1) * report.page_size, report.page * report.page_size).map((row) => ({ ...row, can_edit_note: !controls.readOnly, can_append_supporting: !controls.readOnly, attachment_sources: row.attachment_sources?.map((source) => ({ ...source, source_available: source.receipt_id === fixtureId(700) ? controls.originalAvailable : source.source_available, download_available: !controls.readOnly && (source.receipt_id !== fixtureId(700) || controls.originalAvailable) })) }));
      return Response.json(reportAnswerSchema.parse({ presentation: report.schema_version === 2 && report.presentation ? report.presentation : controls.presentation, items, matching_count: matching.length, page: report.page, page_size: report.page_size, page_count: Math.ceil(matching.length / report.page_size),
        totals: documentFamilyTotals(matching),
        fingerprint: "a".repeat(64), captured_at: "2026-10-26T12:00:00Z", resolved_period: report.filters.period.kind === "latest_month" ? latestMonth(records) : { from_date: null, to_date: null, calendar: "America/Santo_Domingo" }, excluded_unknown_dates: 0,
        counterparties: [{ key: "101001577", labels: ["Proveedor autorizado"] }], categories: ["uncategorized"], expense_types: [{ code: "02", label: "Gastos por trabajos, suministros y servicios" }], funding_sources: [], coverage_notes: ["legal_cancellation_coverage_unavailable", "records_only_evidence_separate"],
        ...controls.legacy ? {} : { overview: { ...controls.overview, ...("needs_fiscal_data" in controls.overview ? { needs_fiscal_data: matching.filter((row) => row.fiscal_data === "missing").length } : {}) }, effective_sort, sort_unavailable_reason: blocked ? "amount_sort_requires_single_known_currency" : null } }));
    }
    if (path.endsWith("/reports/export/preview")) {
      const report = reportRequestSchema.parse((body as { report: unknown }).report);
      const presentation = report.schema_version === 2 && report.presentation ? report.presentation : controls.presentation;
      const sale = report.filters.record_families[0] === "sale";
      const selection = (rows: ReportRecord[]) => ({ record_count: rows.length, currencies: [...new Set(rows.flatMap((row) => row.currency ? [row.currency] : []))].sort() });
      const bounded = report.filters.amount_min !== null || report.filters.amount_max !== null;
      const family = records.filter((row) => row.family === report.filters.record_families[0]);
      const foreign = family.filter((row) => row.fiscal_data && row.currency && row.currency !== controls.dgiiCurrency);
      const pendingFiscal = family.filter((row) => row.fiscal_data === "missing" && row.currency === controls.dgiiCurrency).length;
      return Response.json({
        table: { columns: presentation.order.filter((key) => !sale || (key !== "expense_type" && key !== "payment_form")).map((key) => ({ key, shown: !presentation.hidden.includes(key) })), current: selection(matchingRecords(report)), all: bounded ? null : selection(matchingRecords({ ...report, filters: { ...report.filters, currencies: [] } })) },
        dgii: { form: sale ? "607" : "606", currency: controls.dgiiCurrency, record_count: family.filter((row) => row.fiscal_data === "complete").length, pending_count: pendingFiscal + foreign.length, pending_fiscal_count: pendingFiscal, pending_rate_count: foreign.length, pending_rate_currencies: [...new Set(foreign.map((row) => row.currency!))].sort() },
      });
    }
    if (path.endsWith("/reports/export")) {
      controls.exports.push(body as { mode: string });
      if (controls.exportFails) return problem(503, "business_reports_unavailable");
      const csv = (body as { format: string }).format === "csv";
      return new Response(`Contraparte ${controls.exports.length}`, { headers: { "Content-Type": csv ? "text/csv; charset=utf-8" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Content-Disposition": `attachment; filename="Compras_noviembre-2026.${csv ? "csv" : "xlsx"}"` } });
    }
    if (path.endsWith("/report-views") && method === "GET") return Response.json(views);
    if (path.includes("/report-views")) {
      const command = body as { name?: string; recipe?: unknown; expected_version?: number };
      const id = path.split("/").at(-1)!;
      const current = views.find((view) => view.id === id);
      if (method !== "POST" && (!current || current.version !== command.expected_version)) return problem(409, "business_report_view_changed");
      if (method === "DELETE") { views.splice(views.indexOf(current!), 1); return new Response(null, { status: 204 }); }
      const saved = { id: current?.id ?? fixtureId(9000 + createdViews++), name: command.name!, recipe: command.recipe, version: (current?.version ?? 0) + 1, created_at: "2026-10-26T12:00:00Z", updated_at: "2026-10-26T12:00:00Z" };
      if (current) views.splice(views.indexOf(current), 1, saved); else views.push(saved);
      return Response.json(saved, { status: current ? 200 : 201 });
    }
    const draft = path.match(/\/drafts\/([^/]+)\/(current-note|supporting-files|dossier)$/);
    if (draft) {
      const row = records.find((row) => row.draft_id === draft[1]);
      if (!row) return problem(404, "business_record_not_found");
      if (draft[2] === "dossier") return Response.json(dossier(row));
      if (controls.readOnly) return problem(403, "business_human_command_required");
      const key = headers.get("Idempotency-Key")!;
      const command = body as { note: string; expected_version: number };
      const file = init.body instanceof Blob ? init.body : null;
      const bytes = file ? new Uint8Array(await file.arrayBuffer()) : null;
      const signature = JSON.stringify({ path, body: file ? Array.from(bytes!) : command, filename: headers.get("X-Document-Filename"), version: file ? headers.get("X-Draft-Version") : command.expected_version });
      const prior = replay.get(key);
      if (prior) return prior.signature === signature ? Response.json({ result: prior.result, dossier: dossier(row) }) : problem(409, "business_action_conflict");
      const expected = file ? Number(headers.get("X-Draft-Version")) : command.expected_version;
      if (row.revision !== expected) return problem(409, "stale_version");
      row.revision++;
      let result: Record<string, unknown>;
      if (draft[2] === "current-note") { row.note = command.note; result = { draft_id: row.draft_id, version: row.revision, note: row.note }; }
      else {
        const receiptId = fixtureId(8000 + ++controls.files);
        const sourceId = fixtureId(6000 + controls.files);
        storage.set(receiptId, bytes!);
        row.has_document = true;
        row.attachment_sources = [...row.attachment_sources ?? [], { source_id: sourceId, receipt_id: receiptId, filename: decodeURIComponent(headers.get("X-Document-Filename")!), media_type: headers.get("Content-Type"), source_available: true, download_available: true }];
        result = { draft_id: row.draft_id, version: row.revision, outcome: "appended", source_id: sourceId, receipt_id: receiptId, sha256: "b".repeat(64) };
      }
      replay.set(key, { signature, result });
      if (draft[2] === "current-note" && controls.noteUncertain) { controls.noteUncertain = false; throw new TypeError("Synthetic response lost"); }
      if (file && controls.fileUncertainAt === controls.files) { controls.fileUncertainAt = 0; throw new TypeError("Synthetic response lost"); }
      return Response.json({ result, dossier: dossier(row) });
    }
    const source = path.match(/\/receipts\/([^/]+)\/source$/);
    if (source) {
      if (controls.readOnly) return problem(403, "permission_denied");
      if (!controls.originalAvailable && source[1] === fixtureId(700)) return problem(422, "document_source_unavailable");
      const bytes = storage.get(source[1]);
      return bytes ? new Response(bytes, { headers: { "Content-Type": "application/pdf" } }) : problem(404, "document_source_unavailable");
    }
    throw new Error(`Unexpected synthetic request ${method} ${path}`);
  };
  return { records, calls, views, storage, controls, request };
}
