import { expect, type Page } from "@playwright/test";
import type { BusinessExpense } from "../../lib/business-api";
import { reportAnswerSchema, reportFiltersSchema, reportRequestSchema, type ReportRecord } from "../../lib/business-reports-api";
import { installReceiptBusiness } from "./business-receipt-fixture";

export async function installBusinessRouteFixture(page: Page) {
  const now = new Date();
  await page.clock.setFixedTime(now);
  const approved = new Map<string, BusinessExpense>();
  const source = await installReceiptBusiness(page, (parts, route, fixture) => {
    const path = parts.join("/");
    const request = route.request();
    const url = new URL(request.url());
    if (parts[0] === "drafts" && parts[2] === "approve") return (async () => {
      expect(request.method()).toBe("POST");
      const body = request.postDataJSON();
      const receipt = await fixture.receipt("rcpt-ferreteria");
      expect(parts[1]).toBe(receipt.draft_id);
      const current = await fixture.dossier(parts[1]);
      expect(body.version).toBe(current.version);
      expect(body.action).toBe("record_expense");
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      const result = await fixture.approveDraft(parts[1], body.version, request.headers()["idempotency-key"], body.action);
      if (result.approval_result?.status === "recorded") {
        approved.set(receipt.id, {
          id: result.approval_result.activity_id, receipt_id: receipt.id, draft_id: parts[1],
          merchant: "Ferretería La Esquina", amount: "3450.00", currency: "DOP",
          category_id: "other", account_id: null, occurred_on: receipt.occurred_on!, fiscal_known: true,
        });
      }
      return result;
    })();
    if (path === "receipts") return fixture.receiptPage!("all").then((answer) => {
      const pending = answer.items.filter((item) => approved.has(item.id) && item.status !== "confirmed").length;
      const items = answer.items.map((item) => approved.has(item.id) ? { ...item, status: "confirmed", bandeja_group: { group: null, reason: null, draft_id: item.bandeja_group?.draft_id ?? null, version: item.bandeja_group?.version ?? null } } : item);
      return { ...answer, items: url.searchParams.get("view") === "all" ? items : items.filter((item) => item.status !== "confirmed"), activity: { ...answer.activity, pending_review_count: answer.activity.pending_review_count - pending, bandeja_attention_count: (answer.activity.bandeja_attention_count ?? 0) - pending } };
    });
    if (parts[0] === "receipts" && parts.length === 2 && approved.has(parts[1])) return fixture.receipt(parts[1]).then((receipt) => ({ ...receipt, status: "confirmed" }));
    if (parts[0] === "expenses" && parts.length === 2) return fixture.expense(parts[1]);
    if (path === "expenses") return fixture.expenses("", null).then((items) => ({ items: [...approved.values(), ...items.filter((item) => ![...approved.values()].some((saved) => saved.id === item.id))] }));
    if (path === "search") return fixture.search(url.searchParams.get("q") ?? "").then((answer) => {
      const query = (url.searchParams.get("q") ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      const matches = [...approved.values()].filter((item) => item.merchant!.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().includes(query));
      return { ...answer, expenses: [...matches, ...answer.expenses.filter((item) => !matches.some((saved) => saved.id === item.id))], receipts: answer.receipts.filter((item) => !matches.some((saved) => saved.receipt_id === item.id)) };
    });
    if (path === "search/recents") return Promise.resolve({ items: [] });
    if (path === "search/opens") return Promise.resolve({});
    if (path === "report-views") return Promise.resolve([]);
    if (path === "reports/query") return (async () => {
      expect(request.method()).toBe("POST");
      const report = reportRequestSchema.parse(request.postDataJSON());
      expect(["all", "this_month"]).toContain(report.filters.period.kind);
      expect(report.filters).toEqual(reportFiltersSchema.parse({ period: report.filters.period }));
      expect(report.sort).toBe("date_desc");
      expect(report.page).toBe(1);
      expect(report.page_size).toBe(25);
      const from = report.filters.period.kind === "all" ? null : `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-01`;
      const to = from ? new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0)).toISOString().slice(0, 10) : null;
      const seeded = await fixture.expenses("", null);
      const expenses = [...approved.values(), ...seeded.filter((item) => ![...approved.values()].some((saved) => saved.id === item.id))];
      const matching = expenses.filter((item) => (!from || item.occurred_on >= from) && (!to || item.occurred_on <= to)).sort((a, b) => b.occurred_on.localeCompare(a.occurred_on));
      const items: ReportRecord[] = matching.map((item) => ({
        row_id: item.id, draft_id: item.draft_id ?? null, linked_activity_ids: [item.id], revision: 1,
        report_date: item.occurred_on, date_basis: "activity_effective", family: "purchase", stage: item.id === "exp-gas" ? "needs_review" : "ready_for_export",
        technical_state: "recorded", workflow_blockers: [], currency: item.currency, gross_amount: item.amount,
        recorded_amount: item.amount, recorded_currency: item.currency, proposed_amount: null, money_kind: "expense",
        money_effect: "known", adjustment_effect: null, counterparty: item.merchant, counterparty_key: item.merchant,
        category_key: item.category_id ?? "uncategorized", funding_key: item.account_id, funding_label: null, funding_kind: null,
        has_document: Boolean(item.receipt_id), document_kind: item.receipt_id ? "receipt" : "unknown", fiscal_classification: "unknown", fiscal_number: null,
        note: null, settlement_status: "unpaid", dependency_fingerprint: "synthetic-record", can_edit_note: false, can_append_supporting: false,
        attachment_sources: [],
      }));
      return reportAnswerSchema.parse({
        items, matching_count: items.length, page: report.page, page_size: report.page_size, page_count: 1,
        totals: [], fingerprint: "0".repeat(64), captured_at: "2026-11-02T12:00:00Z",
        resolved_period: { from_date: from, to_date: to, calendar: "America/Santo_Domingo" },
        excluded_unknown_dates: 0, excluded_personal: { income: 0, expense: 0 }, counterparties: [], categories: [], funding_sources: [], coverage_notes: [],
        overview: { needs_review: items.filter((item) => item.stage === "needs_review").length, awaiting_approval: 0, ready_for_export: items.filter((item) => item.stage === "ready_for_export").length }, effective_sort: "date_desc", sort_unavailable_reason: null,
      });
    })();
    return undefined;
  });
  return source;
}

export async function showAllRecords(page: Page) {
  await page.getByTestId("records-toolbar").getByRole("button", { name: "Este mes", exact: true }).click();
  await page.getByRole("button", { name: "Todo", exact: true }).click();
  await expect(page.getByTestId("records-toolbar").getByRole("button", { name: "Todo", exact: true })).toBeVisible();
}
