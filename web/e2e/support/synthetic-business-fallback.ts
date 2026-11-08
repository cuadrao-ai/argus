import type { Request } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../../components/business-app/fixture-data";
import { reportAnswerSchema, reportRequestSchema } from "../../lib/business-reports-api";
import { monthCloseWire } from "./month-close-wire";
import recordedAnswer from "../../test-fixtures/records-default-report-answer.json";

type SyntheticBusinessRoute = {
  request(): Pick<Request, "url" | "method" | "postDataJSON">;
  fulfill(options: { json: unknown; status?: number }): Promise<void>;
};

type FixtureSource = ReturnType<typeof createFixtureBusinessDataSource>;
type FixtureSpace = Awaited<ReturnType<FixtureSource["spaces"]>>[number];
type SyntheticBusinessContext = {
  source?: FixtureSource;
  owner?: FixtureSpace;
  fulfillConsent?: () => Promise<void>;
};

const emptyOpenItems = { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] };

export async function fulfillSyntheticBusinessFallback(
  route: SyntheticBusinessRoute,
  context: SyntheticBusinessContext = {},
): Promise<void> {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname.startsWith("/api/v1/business/") ? url.pathname.slice("/api/v1/business/".length) : null;
  const method = request.method();

  if (path === "guide-cards/bandeja-intro") {
    if (method !== "GET" || url.search) throw new Error("Synthetic guide-cards/bandeja-intro requires GET without query parameters");
    return route.fulfill({ json: { dismissed: false } });
  }
  if (path === "guide-cards/bandeja-intro/dismiss") {
    if (method !== "POST" || url.search) throw new Error("Synthetic guide-cards/bandeja-intro/dismiss requires POST without query parameters");
    return route.fulfill({ json: { dismissed: true } });
  }
  if (path === "reports/query") {
    if (method !== "POST" || url.search) throw new Error("Synthetic reports/query requires POST without query parameters");
    const report = reportRequestSchema.parse(request.postDataJSON());
    if (report.filters.period.kind !== "all" || report.sort !== "date_desc") throw new Error("Synthetic reports/query supports only all periods and date_desc");
    return route.fulfill({ json: reportAnswerSchema.parse({
      presentation: report.schema_version === 2 ? report.presentation ?? recordedAnswer.presentation : recordedAnswer.presentation,
      items: [],
      overview: { needs_review: 0, needs_fiscal_data: 0, ready_for_export: 0, exported: 0 },
      effective_sort: "date_desc",
      sort_unavailable_reason: null,
      matching_count: 0,
      page: report.page,
      page_size: report.page_size,
      page_count: 0,
      totals: [],
      fingerprint: "0".repeat(64),
      captured_at: "2026-10-21T17:45:00Z",
      resolved_period: { from_date: null, to_date: null, calendar: "America/Santo_Domingo" },
      excluded_unknown_dates: 0,
      excluded_personal: { income: 0, expense: 0 },
      counterparties: [],
      categories: [],
      expense_types: [],
      funding_sources: [],
      coverage_notes: [
        "records_only_evidence_separate",
        "legal_cancellation_coverage_unavailable",
        "source_document_subtype_may_be_unknown",
        "counterparty_identity_requires_explicit_tax_id",
      ],
    }) });
  }

  const source = context.source ?? createFixtureBusinessDataSource({ chatAvailable: false });
  const owner = context.owner ?? (await source.spaces())[0];

  if (path === "space/name-prompt") {
    if (method !== "POST") throw new Error("Synthetic space/name-prompt requires POST");
    return route.fulfill({ json: { id: owner.space_id, name: owner.name, name_required: false, name_prompt_seen: true, show_prompt: false } });
  }
  if (path === "spaces") {
    if (method !== "GET") throw new Error("Synthetic spaces requires GET");
    return route.fulfill({ json: { spaces: [owner], closed_spaces: [] } });
  }
  if (path === `spaces/${owner.space_id}/profile`) {
    if (method !== "GET") throw new Error("Synthetic space profile requires GET");
    return route.fulfill({ json: { space_id: owner.space_id, name: owner.name, country: "DO", currency: "DOP", revision: 0, details: {}, appearance: { kind: "default" }, image: null } });
  }
  if (path === "space") {
    if (method !== "GET") throw new Error("Synthetic space requires GET");
    return route.fulfill({ json: { id: owner.space_id, name: owner.name } });
  }
  if (path === "workspace") {
    if (method !== "GET") throw new Error("Synthetic workspace requires GET");
    return route.fulfill({ json: await source.workspace() });
  }
  if (path === "overview") {
    if (method !== "GET") throw new Error("Synthetic overview requires GET");
    return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
  }
  if (path === "fiscal-profile/fields") {
    if (method !== "GET") throw new Error("Synthetic fiscal-profile/fields requires GET");
    return route.fulfill({ json: { "606": [], "607": [] } });
  }
  if (path === "fiscal-profile") {
    if (method !== "GET") throw new Error("Synthetic fiscal-profile requires GET");
    return route.fulfill({ json: await source.fiscalProfile() });
  }
  if (path === "consent") {
    if (method !== "GET") throw new Error("Synthetic consent requires GET");
    if (!context.fulfillConsent) throw new Error("Synthetic consent requires an accepted-consent fixture");
    return context.fulfillConsent();
  }
  if (path === "receipt-reading") {
    if (method !== "GET") throw new Error("Synthetic receipt-reading requires GET");
    return route.fulfill({ json: { enabled: false, available: true, can_change: false } });
  }
  if (path === "email") {
    if (method !== "GET") throw new Error("Synthetic email requires GET");
    return route.fulfill({ json: { enabled: true, receiving_address: "receipts@example.test" } });
  }
  if (["captures", "email/deliveries", "email/senders", "ownership-transfers", "closed-spaces", "owned-spaces"].includes(path ?? "")) {
    if (method !== "GET") throw new Error(`Synthetic ${path} requires GET`);
    return route.fulfill({ json: { items: [], spaces: [], transfers: [] } });
  }
  if (path === "receipts") {
    if (method !== "GET") throw new Error("Synthetic receipts requires GET");
    return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0, confirmed_count: 0, dismissed_count: 0 } } });
  }
  if (path === "month-close") {
    if (method !== "GET") throw new Error("Synthetic month-close requires GET");
    return route.fulfill({ json: monthCloseWire("2026-10") });
  }
  if (path === "open-items") {
    if (method !== "GET") throw new Error("Synthetic open-items requires GET");
    return route.fulfill({ json: { today: "2026-10-22", cuentas_por_cobrar: emptyOpenItems, cuentas_por_pagar: emptyOpenItems } });
  }
  if (path === "invitations") {
    if (method !== "GET") throw new Error("Synthetic invitations requires GET");
    return route.fulfill({ json: [] });
  }

  throw new Error(`Unmapped synthetic endpoint ${path ?? url.pathname}`);
}
