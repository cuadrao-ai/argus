import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import RecordsPagePreview from "@/components/business-app/transacciones/RecordsPagePreview";
import { defaultRecordsPreferences } from "@/components/business-app/transacciones/records-view-preferences";
import { businessReportRow } from "@/lib/business-reporting-wire";
import type { ReportAnswer, ReportRecord } from "@/lib/business-reports-api";
import spanish from "@/public/locales/es-419/common.json";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";
import { useBusinessReport } from "@/components/business-app/transacciones/useBusinessReport";
import type { ReportingTransport } from "@/lib/business-reporting-wire";

let root: Root | undefined;
let previousGrant: string | null | undefined;
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => { if (root) await act(async () => root?.unmount()); root = undefined; if (previousGrant !== undefined) setChosenGrant(previousGrant); previousGrant = undefined; document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const row = (id: string, amount: string | null): ReportRecord => ({
  row_id: `draft:${id}`, draft_id: id, linked_activity_ids: [], revision: 3, report_date: null, date_basis: "document_issue", family: "purchase", stage: null,
  technical_state: "processing", workflow_blockers: [], currency: amount ? "DOP" : null, gross_amount: amount, recorded_amount: null, recorded_currency: null, proposed_amount: null,
  money_kind: "expense", money_effect: "unknown", adjustment_effect: null, counterparty: id, counterparty_key: null, category_key: "uncategorized", funding_key: null, funding_label: null,
  funding_kind: null, has_document: false, document_kind: "unknown", fiscal_classification: "unknown", fiscal_number: null, note: "Nota actual", settlement_status: null, dependency_fingerprint: "dependency",
});

test("a same-grant notification keeps the current report while an actual switch immediately clears it", async () => {
  previousGrant = getChosenGrant();
  const grantId = "00000000-0000-4000-8000-000000000001";
  setChosenGrant(grantId);
  const transport: ReportingTransport = {
    query: async (_scope, request) => ({ items: [], matching_count: 0, page: request.page, page_size: request.page_size, page_count: 0, totals: [], fingerprint: "a".repeat(64), captured_at: "2026-10-26", resolved_period: { from_date: null, to_date: null, calendar: "America/Santo_Domingo" }, excluded_unknown_dates: 0, counterparties: [], categories: [], funding_sources: [], coverage_notes: [] }),
    export: async () => new Blob(), listViews: async () => [], mutateView: async () => null,
  };
  function Probe() {
    const { state } = useBusinessReport({ userId: "person", businessId: "business", grantId }, undefined, transport);
    return <span data-report-state={state.load.kind}>{state.load.kind}</span>;
  }
  const host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
  await act(async () => root?.render(<Probe />));
  assert.equal(host.textContent, "ready");
  await act(async () => setChosenGrant(grantId));
  assert.equal(host.textContent, "ready");
  await act(async () => setChosenGrant(null));
  assert.equal(host.textContent, "failed");
});

test("a connected last page uses full server count and original row order, with unknown values and read-only notes", async () => {
  const items = [row("zeta", null), row("alfa", "1234567890123.45")];
  const answer: ReportAnswer = { items, matching_count: 102, page: 5, page_size: 25, page_count: 5, totals: [], fingerprint: "a".repeat(64), captured_at: "2026-10-26", resolved_period: { from_date: null, to_date: null, calendar: "America/Santo_Domingo" }, excluded_unknown_dates: 0, counterparties: [], categories: [], funding_sources: [], coverage_notes: ["legal_cancellation_coverage_unavailable"] };
  const pages: number[] = [];
  const sizes: number[] = [];
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const context = { chosen: { space_id: "fixture-space", role: "owner", capabilities: ["read", "prepare"] }, panel: { kind: "transactions" }, openPanel: () => undefined, records: { workspace: null } } as unknown as BusinessContextValue;
  const host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
  await act(async () => root?.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>
    <RecordsPagePreview records={items.map(businessReportRow)} density="normal" preferences={defaultRecordsPreferences()} onSortChange={() => { throw new Error("Connected rows cannot sort locally"); }} rowRef={() => undefined} resetKey="report" connected={{ answer, onPage: (page) => pages.push(page), onPageSize: (size) => sizes.push(size) }} />
  </BusinessContext.Provider></I18nextProvider>));
  assert.equal(document.querySelector('[data-testid="records-pagination"]')?.getAttribute("data-page"), "5");
  assert.match(document.querySelector('[data-testid="records-count"]')!.textContent!, /101.*102.*102/);
  const rows = [...document.querySelectorAll('tbody tr[data-record-id]')];
  assert.deepEqual(rows.map((item) => item.getAttribute("data-record-id")), ["zeta", "alfa"]);
  assert.match(rows[0].querySelector('[data-col="monto"]')!.textContent!, /-/);
  assert.equal(rows[0].querySelector('[data-col="notas"]')!.textContent, "Nota actual");
  assert.equal(rows[0].querySelector('[data-col="notas"] button'), null);
  assert.equal(document.querySelector('[data-record-workflow="ready"]'), null);
  await act(async () => (document.querySelector('th[data-col="fecha"] button') as HTMLElement).click());
  await act(async () => (document.querySelector('button[aria-label="Primera página"]') as HTMLElement).click());
  assert.deepEqual(pages, [1]);
  const picker = [...document.querySelectorAll("button")].find((button) => button.textContent?.includes("25 por página"));
  assert.ok(picker);
  await act(async () => picker.click());
  const hundred = [...document.querySelectorAll("button")].find((button) => button.textContent?.includes("100 por página"));
  assert.ok(hundred);
  await act(async () => hundred.click());
  assert.deepEqual(sizes, [100]);
});
