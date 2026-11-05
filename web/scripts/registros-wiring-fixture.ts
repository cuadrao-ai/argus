// Synthetic contract transport only. Local paired evidence separately runs the frozen backend reducer.
declare const Bun: { serve(options: { hostname: string; port: number; fetch(request: Request): Promise<Response> }): { stop(): void } };
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { createBusinessReportHttpFixture, fixtureId } from "@/__tests__/fixtures/business-report-http-fixture";
import { dossierFixtureIds } from "@/components/business-app/dossier-fixtures";


const fixture = createBusinessReportHttpFixture();
fixture.records[0].gross_amount = "9007199254740993.01";
fixture.records[0].recorded_amount = "9007199254740993.01";
const fixtureSource = createFixtureBusinessDataSource({ chatAvailable: false });
const workspace = await fixtureSource.workspace();
const sampleDossier = await fixtureSource.dossier(dossierFixtureIds.ready);
const sourceObjects = sampleDossier.sources;
const origin = process.env.EVIDENCE_WEB_BASE_URL ?? "http://127.0.0.1:4395";
if (new URL(origin).hostname !== "127.0.0.1" || process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") throw new Error("Synthetic loopback fixture only");
const space = { space_id: fixtureId(3000), grant_id: fixtureId(3001), role: "owner", name: "Colmado sintético", capabilities: ["read", "prepare", "approve"], access_seen: true };
const json = (body: unknown, status = 200) => Response.json(body, { status, headers: { "Cache-Control": "no-store", "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET,POST,PATCH,PUT,DELETE,OPTIONS", "Access-Control-Allow-Credentials": "true" } });
let queryError = false;
const server = Bun.serve({ hostname: "127.0.0.1", port: Number(process.env.EVIDENCE_FIXTURE_PORT ?? "4396"), async fetch(request) {
  const url = new URL(request.url), path = url.pathname, method = request.method;
  if (method === "OPTIONS") return json(null);
  const raw = method === "GET" ? undefined : new Uint8Array(await request.arrayBuffer());
  const contentType = request.headers.get("Content-Type") ?? "";
  const body = raw ? contentType.includes("application/json") ? JSON.parse(new TextDecoder().decode(raw)) : new File([raw], decodeURIComponent(request.headers.get("X-Document-Filename") ?? "synthetic.pdf"), { type: contentType }) : undefined;
  try {
    if (path === "/__fixture/control") { if (body.queryError !== undefined) queryError = body.queryError; if (body.resetViews) fixture.views.length = 0; if (body.bumpViewVersion && fixture.views[0]) fixture.views[0].version++; Object.assign(fixture.controls, body); return json(fixture.controls); }
    if (path.endsWith("/reports/query") && queryError) return new Response(JSON.stringify({ code: "synthetic_private_failure", detail: { title: "INTERNAL_FIXTURE_SECRET_NOT_FOR_UI" } }), { status: 503, headers: { "Content-Type": "application/json", "X-Request-Id": "12345678-1234-4123-8123-123456789012", "Access-Control-Allow-Origin": origin, "Access-Control-Expose-Headers": "X-Request-Id" } });
    if (path.endsWith("/business/spaces")) return json({ spaces: [space], closed_spaces: [] });
    if (path.endsWith("/business/space")) return json({ id: space.space_id, name: space.name });
    if (path.endsWith("/business/workspace")) return json(workspace);
    if (path.endsWith("/business/consent")) return json({ version: url.searchParams.get("version"), accepted_at: "2026-10-26T12:00:00Z" });
    if (path.endsWith("/business/receipt-activity")) return json(await fixtureSource.receiptActivity!());
    if (path.endsWith("/business/receipts")) return json(await fixtureSource.receiptPage!(url.searchParams.get("view") === "all" ? "all" : "inbox"));
    if (path.endsWith("/business/overview")) return json(await fixtureSource.overview(url.searchParams.get("from")!, url.searchParams.get("to")));
    if (path.endsWith("/business/captures")) return json({ items: [], next_cursor: null });
    if (path.endsWith("/business/email/deliveries")) return json({ items: [] });
    if (path.endsWith("/business/email")) return json(await fixtureSource.emailIntake!());
    const dossier = path.match(/\/business\/drafts\/([^/]+)\/dossier$/);
    if (dossier) {
      const row = fixture.records.find((row) => row.draft_id === dossier[1]);
      if (!row) return json({ code: "business_record_not_found" }, 404);
      return json({ ...sampleDossier, facts: { ...sampleDossier.facts, amount: { state: row.gross_amount === null ? "unknown" : "known", value: row.gross_amount, origin: "owner_stated", verified: false, source_ids: [] }, currency: { state: row.currency === null ? "unknown" : "known", value: row.currency, origin: "owner_stated", verified: false, source_ids: [] }, counterparty: { state: row.counterparty === null ? "unknown" : "known", value: row.counterparty, origin: "owner_stated", verified: false, source_ids: [] }, occurred_on: { state: row.report_date === null ? "unknown" : "known", value: row.report_date, origin: "owner_stated", verified: false, source_ids: [] } }, draft_id: row.draft_id, space_id: space.space_id, space_name: space.name, version: row.revision, current_note: row.note, note_edit_available: true, supporting_append_available: true, annotation_unavailable_reason: null, sources: row.attachment_sources?.map((source) => ({ id: source.source_id, connection_id: source.receipt_id, kind: "attachment", channel: "web", received_at: "2026-10-26T12:00:00Z", filename: source.filename, media_type: source.media_type })) ?? sourceObjects });
    }
    const response = await fixture.request(request.url, { method, headers: request.headers, body: body instanceof File ? body : body === undefined ? undefined : JSON.stringify(body) });
    const headers = new Headers(response.headers); headers.set("Access-Control-Allow-Origin", origin); headers.set("Cache-Control", "no-store");
    return new Response(response.body, { status: response.status, headers });
  } catch (error) { return json({ code: "synthetic_fixture_error", detail: String(error) }, 500); }
} });
console.log("Synthetic contract HTTP fixture, no backend/database proof");
for (const signal of ["SIGTERM", "SIGINT"] as const) process.on(signal, () => { server.stop(); process.exit(0); });
