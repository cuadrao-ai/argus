import { test } from "bun:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { approvalLine, finishPeriodExportRequest, saveBlobDownload, startPeriodExportRequest, ReceiptApprovalGuidance, ReceiptPeriodExport, ReceiptReadPurchases } from "@/components/business-app/ReceiptDossierReview";
import { factsRevision, type BusinessDossier } from "@/lib/business-dossier";
import { businessExportPeriodValid, fetchBusinessExport, approveBusinessDraft, getBusinessDossier, reviewBusinessDraft, listBusinessExpenses, type BusinessExpense } from "@/lib/business-api";
import { withBusinessSpace } from "@/components/business-app/business-data";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { presentBusinessFact, presentFiscalFact } from "@/components/business-app/receipt-fact-presentation";

test("accepted recorded dossiers omit preapproval guidance while open and uncertain blockers remain", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const ready = await fixture.dossier(dossierFixtureIds.ready);
  const accepted = await fixture.approveDraft(ready.draft_id, ready.version);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const render = (dossier: BusinessDossier) => renderToStaticMarkup(createElement(I18nextProvider, { i18n }, createElement(ReceiptApprovalGuidance, { dossier })));
  const closed = { ...accepted, blockers: [{ code: "business_draft_not_open", field: null }] };
  assert.equal(render(closed), "");
  const open = await fixture.dossier(dossierFixtureIds.unknown);
  assert.match(render(open), /Antes de aprobar/);
  assert.match(render(open), /Cómo se pagó/);
  const uncertain = { ...open, review_state: "accepting" as const, approval_result: { status: "outcome_unknown" as const, code: "recording_unknown", reviewed_version: open.version } };
  assert.match(render(uncertain), /Antes de aprobar/);
  assert.match(render({ ...closed, approval_result: uncertain.approval_result }), /Antes de aprobar/);
  assert.match(render({ ...closed, review_state: "open" }), /Antes de aprobar/);
});

test("canonical draft transport binds explicit ID, version, human effect and idempotency", async () => {
  const originalFetch = globalThis.fetch;
  const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  const calls: { url: string; method: string; body: unknown; key: string | null }[] = [];
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null, key: new Headers(init?.headers).get("Idempotency-Key") });
    return new Response(JSON.stringify({ draft_id: dossierFixtureIds.ready }), { headers: { "Content-Type": "application/json" } });
  };
  try {
    await getBusinessDossier(dossierFixtureIds.ready);
    await reviewBusinessDraft(dossierFixtureIds.ready, 8, { funding: { state: "owner_does_not_know", value: null } }, "human-review-once");
    await reviewBusinessDraft(dossierFixtureIds.ready, 8, { funding: { state: "owner_does_not_know", value: null } }, "human-review-once");
    await reviewBusinessDraft(dossierFixtureIds.ready, 9, { kind: { state: "known", value: "expense" } }, "human-review-new-intent");
    await approveBusinessDraft(dossierFixtureIds.ready, 10, "human-approval-once");
    assert.equal(calls.length, 5);
    assert.ok(calls[0].url.endsWith(`/business/drafts/${dossierFixtureIds.ready}/dossier`));
    assert.deepEqual(calls[1].body, { version: 8, facts: { funding: { state: "owner_does_not_know", value: null } } });
    assert.equal(calls[1].key, "human-review-once");
    assert.deepEqual(calls[2], calls[1]);
    assert.equal(calls[3].key, "human-review-new-intent");
    assert.deepEqual(calls[3].body, { version: 9, facts: { kind: { state: "known", value: "expense" } } });
    assert.deepEqual(calls[4].body, { version: 10, action: "record_expense" });
    assert.equal(calls[4].key, "human-approval-once");
    assert.equal(calls[4].method, "POST");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  }
});

test("grant-scoped receipt and draft calls never create the current person's Business space", async () => {
  const fixture = createFixtureBusinessDataSource();
  let starts = 0;
  const source = withBusinessSpace({ ...fixture, ensureSpace: async () => { starts++; return { id: "wrong-own-space", name: "Own business" }; } }, () => "en");
  const record = await source.dossier(dossierFixtureIds.ready);
  const receipt = await source.receipt("rcpt-ferreteria");
  await source.receiptSource(receipt.id);
  const reviewed = await source.saveReview(receipt.id, receipt.version, { account_id: receipt.record_context!.accounts[0].id });
  assert.ok(reviewed.draft_id);
  await source.dossier(reviewed.draft_id);
  assert.equal(starts, 0);
  assert.equal(record.space_name, "Taller Lucía · sample business");
});

test("unknown and owner-does-not-know funding preserve their distinct display states", async () => {
  const accounts = [{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }];
  const fixture = createDossierFixtures(accounts);
  const unknown = await fixture.dossier(dossierFixtureIds.unknownAmount);
  const labels = { unknown: "Unknown", ownerUnknown: "Owner doesn't know", ownerFunds: "Owner's money", businessAccount: "Business account" };
  assert.equal(presentBusinessFact("amount", unknown.facts, accounts, "en", labels), "Unknown");
  assert.equal(presentBusinessFact("funding", unknown.facts, accounts, "en", labels), "Unknown");
  const ownerUnknown = await fixture.reviewDraft(unknown.draft_id, unknown.version, { funding: { state: "owner_does_not_know", value: null } }, "owner-uncertainty");
  assert.equal(presentBusinessFact("funding", ownerUnknown.facts, accounts, "en", labels), "Owner doesn't know");
  assert.equal(ownerUnknown.approval_available, false);
});

test("uncertain review replays the same command once, while a new intent uses a new key", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const current = await fixture.dossier(dossierFixtureIds.saveUnknown);
  const facts = { counterparty: { state: "known" as const, value: "Reviewed merchant" } };
  await assert.rejects(fixture.reviewDraft(current.draft_id, current.version, facts, "same-command"), TypeError);
  const replay = await fixture.reviewDraft(current.draft_id, current.version, facts, "same-command");
  assert.equal(replay.version, 3);
  assert.equal(replay.history.length, 3);
  assert.equal(replay.sources.filter((source) => source.kind === "web_action").length, 2);
  await assert.rejects(fixture.reviewDraft(current.draft_id, replay.version, facts, "same-command"), { code: "idempotency_conflict" });
  const next = await fixture.reviewDraft(current.draft_id, replay.version, { counterparty: { state: "known", value: "New correction" } }, "new-command");
  assert.equal(next.version, 4);
  assert.equal(next.facts.counterparty.value, "New correction");
});

test("unknown kind becomes a sourced human expense decision on its exact revision", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const current = await fixture.dossier(dossierFixtureIds.unknownKind);
  assert.equal(current.facts.kind.state, "unknown");
  assert.equal(current.approval_available, false);
  const next = await fixture.reviewDraft(current.draft_id, current.version, { kind: { state: "known", value: "expense" } }, "kind-decision");
  assert.equal(next.facts.kind.value, "expense");
  assert.equal(next.facts.kind.origin, "member_set");
  assert.equal(next.approval_available, true);
  assert.equal(next.approval_result, null);
  const source = next.sources.find((source) => source.id === next.facts.kind.source_ids[0]);
  assert.equal(source?.kind, "web_action");
  assert.deepEqual(source && "text" in source ? JSON.parse(source.text) : null, { version: current.version, facts: { kind: { state: "known", value: "expense" } } });
  await assert.rejects(fixture.reviewDraft(current.draft_id, current.version, { kind: { state: "known", value: "expense" } }, "stale-kind-decision"), { code: "stale_version" });
});

test("fiscal values preserve unknown, exact tax and verified server states", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const dossier = await fixture.dossier(dossierFixtureIds.fiscal);
  const labels = { unknown: "Unknown", ownerUnknown: "Owner doesn't know", notRecorded: "Not recorded" };
  assert.equal(presentFiscalFact("rnc", dossier.facts, "en", labels), "131999888");
  assert.equal(presentFiscalFact("ecf", dossier.facts, "en", labels), "Owner doesn't know");
  assert.equal(presentFiscalFact("itbis", dossier.facts, "en", labels), "RD$ 526.27");
  assert.equal(dossier.facts.fiscal?.itbis.verified, true);
  assert.equal(presentFiscalFact("rnc", dossier.history[0].before!, "en", labels), "Unknown");
  assert.equal(presentFiscalFact("itbis", { ...dossier.facts, currency: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } }, "en", labels), "526.27");
});

test("owner-funded expense projection preserves its null account and funding kind", async () => {
  const originalFetch = globalThis.fetch;
  const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  const expense: BusinessExpense = { id: "owner-funded-expense", merchant: "Supplier", amount: "3450.00", currency: "DOP", category_id: null, account_id: null, funding: "owner_funds", occurred_on: "2026-10-09", receipt_id: null };
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async () => new Response(JSON.stringify({ items: [expense] }), { headers: { "Content-Type": "application/json" } });
  try {
    assert.deepEqual(await listBusinessExpenses("2026-10-01", "2026-10-31"), [expense]);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  }
});


test("export periods match inclusive calendar limits without timezone or invalid-date coercion", () => {
  assert.equal(businessExportPeriodValid("2024-01-01", "2024-12-31"), true);
  assert.equal(businessExportPeriodValid("2024-01-01", "2025-01-01"), false);
  assert.equal(businessExportPeriodValid("2026-10-10", "2026-10-10"), true);
  for (const [start, end] of [["2026-02-29", "2026-03-01"], ["2026-10-11", "2026-10-10"], ["2026-1-01", "2026-01-31"], ["0000-01-01", "0000-01-02"], ["", "2026-01-01"]]) assert.equal(businessExportPeriodValid(start, end), false);
});

test("Spanish export control names the authorized client and allows read-only records without approval", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const fixture = createDossierFixtures([{ id: "client-account", nickname: "Caja", type: "cash", currency: "DOP" }]);
  const record = await fixture.dossier(dossierFixtureIds.readOnly);
  const render = (dossier: BusinessDossier, available = true, end = "2026-10-31") => renderToStaticMarkup(createElement(I18nextProvider, { i18n }, createElement(ReceiptPeriodExport, { dossier, start: "2026-10-01", end, available })));
  const html = render(record);
  assert.ok(html.includes(record.space_name));
  assert.match(html, /Descargar CSV, Excel y originales/);
  assert.match(html, /originales faltantes/);
  assert.doesNotMatch(html, /<button[^>]*\sdisabled=""/);
  assert.ok(!html.includes("Aprobar"));
  assert.equal(render({ ...record, capabilities: [] }), "");
  assert.match(render(record, false), /<button[^>]*\sdisabled=""/);
  assert.match(render(record, false), /vista conectada/);
  assert.match(render(record, true, "2028-10-31"), /<button[^>]*\sdisabled=""/);
});

test("export transport reads only the explicit draft client and preserves the server ZIP bytes", async () => {
  const originalFetch = globalThis.fetch;
  const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const calls: { url: URL; init?: RequestInit }[] = [];
  const bytes = new Uint8Array([80, 75, 3, 4, 0, 255, 39, 0]);
  globalThis.fetch = async (input, init) => {
    calls.push({ url: new URL(String(input)), init });
    return new Response(bytes, { headers: { "Content-Type": "application/zip" } });
  };
  try {
    const blob = await fetchBusinessExport(dossierFixtureIds.readOnly, "2026-10-01", "2026-10-31");
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
    assert.equal(blob.type, "application/zip");
    assert.equal(calls.length, 1);
    assert.ok(calls[0].url.pathname.endsWith("/business/exports"));
    assert.deepEqual([...calls[0].url.searchParams], [["start", "2026-10-01"], ["end", "2026-10-31"], ["draft_id", dossierFixtureIds.readOnly]]);
    assert.equal(calls[0].init?.method ?? "GET", "GET");
    assert.equal(calls[0].init?.body, undefined);
    assert.equal(calls[0].init?.cache, "no-store");
    for (const [status, code] of [[403, "business_permission_denied"], [404, "business_record_not_found"], [413, "export_record_limit"], [503, "business_export_unavailable"]] as const) {
      globalThis.fetch = async () => new Response(JSON.stringify({ detail: { code, status } }), { status, headers: { "Content-Type": "application/json" } });
      await assert.rejects(fetchBusinessExport(dossierFixtureIds.readOnly, "2026-10-01", "2026-10-31"), { status, code });
    }
    globalThis.fetch = async () => new Response("unexpected document", { headers: { "Content-Type": "text/html" } });
    await assert.rejects(fetchBusinessExport(dossierFixtureIds.readOnly, "2026-10-01", "2026-10-31"), /Invalid Business export response/);
    let dispatched = false;
    globalThis.fetch = async () => { dispatched = true; return new Response(bytes); };
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(fetchBusinessExport(dossierFixtureIds.readOnly, "2026-10-01", "2026-10-31", controller.signal));
    assert.equal(dispatched, false);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  }
});


test("export download clicks a named link and revokes its object URL only after a delay", () => {
  const events: string[] = [];
  const link = { href: "", download: "", click() { events.push(`click:${this.download}:${this.href}`); }, remove() { events.push("remove"); } };
  const globals = globalThis as unknown as { document?: unknown; setTimeout: typeof setTimeout };
  const original = { document: globals.document, setTimeout: globals.setTimeout, create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  let revokeLater: (() => void) | null = null;
  let revokeDelay = 0;
  globals.document = { createElement: () => link, body: { appendChild: () => events.push("append") } };
  globals.setTimeout = ((callback: () => void, delay: number) => { revokeLater = callback; revokeDelay = delay; return 0; }) as unknown as typeof setTimeout;
  URL.createObjectURL = () => "blob:export";
  URL.revokeObjectURL = (url: string) => { events.push(`revoke:${url}`); };
  try {
    saveBlobDownload(new Blob(["zip"]), "business-export-2026-10-01-2026-10-31.zip");
    assert.deepEqual(events, ["append", "click:business-export-2026-10-01-2026-10-31.zip:blob:export", "remove"]);
    assert.equal(revokeDelay, 30_000);
    revokeLater!();
    assert.deepEqual(events.at(-1), "revoke:blob:export");
  } finally {
    globals.document = original.document;
    globals.setTimeout = original.setTimeout;
    URL.createObjectURL = original.create;
    URL.revokeObjectURL = original.revoke;
  }
});

test("revoked export releases busy immediately and late settlement cannot unlock a restored request", () => {
  const request: { current: AbortController | null } = { current: null };
  let busy = false;
  const changes: boolean[] = [];
  const setBusy = (value: boolean) => { busy = value; changes.push(value); };
  const revoked = startPeriodExportRequest(request, setBusy)!;
  assert.equal(busy, true);
  assert.equal(startPeriodExportRequest(request, setBusy), null);
  revoked.abort();
  assert.equal(busy, false);
  assert.equal(request.current, null);
  const restored = startPeriodExportRequest(request, setBusy)!;
  assert.equal(busy, true);
  finishPeriodExportRequest(request, revoked, setBusy);
  assert.equal(busy, true);
  assert.equal(request.current, restored);
  finishPeriodExportRequest(request, restored, setBusy);
  assert.equal(busy, false);
  assert.equal(request.current, null);
  assert.deepEqual(changes, [true, false, true, false]);
});

test("read purchases say what the record covers of the receipt total until the rest is settled", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const ready = await fixture.dossier(dossierFixtureIds.ready);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const render = (dossier: BusinessDossier) => renderToStaticMarkup(createElement(I18nextProvider, { i18n }, createElement(ReceiptReadPurchases, { dossier, onSettle: () => undefined })));
  const read = [{ index: 1, amount: "3450.00", currency: "DOP", occurred_on: "2026-10-09", merchant: "Ferretería La Esquina", kind_hint: "expense" }, { index: 2, amount: "95.00", currency: "DOP", occurred_on: "2026-10-09", merchant: "Ferretería La Esquina", kind_hint: "expense" }];
  assert.equal(render(ready), "");
  const open = { ...ready, read_purchases: read, read_total: "3545.00", unrecorded_purchases: 2 };
  assert.match(render(open), /más de una compra/);
  assert.doesNotMatch(render(open), /dossier-settle-remainder/);
  const accepted = await fixture.approveDraft(ready.draft_id, ready.version);
  const recorded = { ...accepted, read_purchases: read, read_total: "3545.00", unrecorded_purchases: 1 };
  const html = render(recorded);
  assert.match(html, /Registrado .*3[.,]450/);
  assert.match(html, /1 compras de este recibo siguen sin registrar/);
  assert.match(html, /dossier-settle-remainder/);
  const done = render({ ...recorded, unrecorded_purchases: 0 });
  assert.match(done, /ya está atendido/);
  assert.doesNotMatch(done, /dossier-settle-remainder/);
});

test("the header revision is the latest facts revision the history lists, not the event counter", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const ready = await fixture.dossier(dossierFixtureIds.ready);
  assert.equal(factsRevision(ready), Math.max(...ready.history.map((r) => r.version)));
  // An approval and a settlement moved the event to version 4 while the facts stayed at revision 2.
  const settled = { ...ready, version: 4, history: ready.history.filter((r) => r.version <= 2) };
  assert.equal(factsRevision(settled), 2);
  assert.equal(factsRevision({ version: 3, history: [] }), 3);
});

test("the line under approve never tells a person who can approve that someone else must", () => {
  // Owner (prepare + approve) on a note whose kind is still unknown: no permission line; the blockers card names the kind.
  assert.equal(approvalLine(true, true), null);
  assert.equal(approvalLine(true, true), null);
  assert.equal(approvalLine(true, false), null);
  // Only prepare-only access reads a permission line.
  assert.equal(approvalLine(false, true), "prepare_only");
  assert.equal(approvalLine(false, true), "prepare_only");
  assert.equal(approvalLine(false, false), null);
});

test("the record page mounts no export panel: exports belong to a period surface", () => {
  const source = readFileSync(join(import.meta.dir, "..", "components", "business-app", "ReceiptDossierReview.tsx"), "utf-8");
  const start = source.indexOf("export default function ReceiptDossierReview");
  assert.ok(start >= 0, "the page component is where the test looks for it");
  const page = source.slice(start);
  assert.ok(!page.includes("<ReceiptPeriodExport"));
});
