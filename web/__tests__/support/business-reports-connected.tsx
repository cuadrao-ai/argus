import assert from "node:assert/strict";
import { act, StrictMode } from "react";
import { I18nextProvider } from "react-i18next";
import { Plus } from "lucide-react";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import BusinessReportsPanel, { ConnectedBusinessReports } from "@/components/business-app/transacciones/BusinessReportsPanel";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { setChosenGrant } from "@/lib/business-grant";
import { reportAnswerSchema, reportRequestSchema, type ReportAnswer, type ReportRecord, type ReportRequest, type RecordsCurrency } from "@/lib/business-reports-api";
import { createBusinessReportHttpFixture, fixtureId } from "../fixtures/business-report-http-fixture";
import type { recordedReportAnswer } from "../fixtures/recorded-report-answer";
import { translate, type TestLanguage } from "./i18n-instance";

let cleanup = async () => {};
export const unmountConnectedReport = () => cleanup();

export async function mountConnectedReport(options: { onAdd?: () => void; defaultCurrency?: RecordsCurrency; workspaceFailure?: "error" | "refused" | "missing_default"; viewRecipe?: ReportRequest; topLevel?: boolean; grantId?: string; workspaceGrant?: string | null; readOnly?: boolean; large?: boolean; legacy?: boolean; initial?: ReportRequest; width?: number; queryGate?: Promise<void>; queryAnswer?: (request: ReportRequest, answer: ReportAnswer) => ReportAnswer | Promise<ReportAnswer>; waitForAnswer?: boolean; language?: TestLanguage; presentation?: typeof recordedReportAnswer.presentation; role?: string; edit?: (records: ReportRecord[]) => void; waiting?: number | null } = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width: options.width ?? 1440, height: 900 });
  const { createRoot } = await import("react-dom/client");
  const fixture = createBusinessReportHttpFixture(); for (const row of fixture.records) if (row.currency !== "DOP") { row.currency = "DOP"; row.recorded_currency = "DOP"; } if (options.presentation) fixture.controls.presentation = options.presentation; options.edit?.(fixture.records); if (options.large) { fixture.records[1].family = "purchase"; fixture.records[0].gross_amount = "9007199254740993.01"; fixture.records[0].recorded_amount = "9007199254740993.01"; fixture.records[3].family = "purchase"; fixture.records[3].document_kind = "credit_note"; fixture.records[3].gross_amount = "20.00"; fixture.records[3].adjustment_effect = "known"; fixture.records[4].gross_amount = "-20.00"; fixture.records[4].document_kind = "credit_note"; fixture.records[4].adjustment_effect = "known"; } fixture.controls.readOnly = options.readOnly ?? false; fixture.controls.legacy = options.legacy ?? false;
  if (options.viewRecipe) fixture.views.push({ id: fixtureId(3300), name: "Moneda guardada", recipe: { schema_version: options.viewRecipe.schema_version, filters: options.viewRecipe.filters, columns: options.viewRecipe.columns, sort: options.viewRecipe.sort, ...(options.viewRecipe.schema_version === 2 ? { page_size: options.viewRecipe.page_size } : {}) }, version: 1, created_at: "2026-11-07T00:00:00Z", updated_at: "2026-11-07T00:00:00Z" });
  const computedStyle = globalThis.getComputedStyle;
  if (options.width && options.width < 1024) globalThis.getComputedStyle = ((element: Element) => {
    const style = computedStyle(element);
    return new Proxy(style, { get(target, key) { if (key === 'getPropertyValue') return (name: string) => name === '--records-narrow' ? '1' : target.getPropertyValue(name); const value = Reflect.get(target, key); return typeof value === 'function' ? value.bind(target) : value; } });
  }) as typeof getComputedStyle;
  const originalFetch = globalThis.fetch; globalThis.fetch = (async (input, init) => {
    if (String(input).endsWith("/me")) return Response.json({ user: { id: "synthetic-person", language: "es-419" } });
    const query = String(input).endsWith("/reports/query");
    if (options.queryGate && query) await options.queryGate;
    const response = await fixture.request(input, init);
    return query && options.queryAnswer && response.ok ? Response.json(await options.queryAnswer(reportRequestSchema.parse(JSON.parse(String(init?.body))), reportAnswerSchema.parse(await response.json()))) : response;
  }) as typeof fetch;
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
  const downloads: Blob[] = []; URL.createObjectURL = (blob) => { downloads.push(blob as Blob); return "blob:synthetic"; }; URL.revokeObjectURL = () => undefined;
  setChosenGrant(options.grantId ?? null);
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const opened: unknown[] = [];
  const receiptActivity = options.waiting === undefined ? null : options.waiting === null ? null : { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: options.waiting, needs_attention_count: 0, ready_to_review_count: options.waiting };
  const context = { chosen: { space_id: fixtureId(3000), grant_id: fixtureId(3001), role: options.role ?? "owner", name: "Colmado sintético", capabilities: options.readOnly ? ["read"] : ["read", "prepare", "approve"], permissions: options.readOnly ? ["read"] : ["read", "prepare", "approve", "download", "export"] }, source, revision: 0, actions: { create: options.onAdd ? [{ id: "upload_receipt", label: "Agregar", icon: Plus, run: options.onAdd }] : [] }, panel: { kind: "transactions" }, openPanel: (panel: unknown) => { opened.push(panel); }, records: { workspace: { ...await source.workspace(), currency: "CAD", records_default_currency: options.defaultCurrency ?? "DOP" }, workspaceGrant: options.workspaceGrant === undefined ? options.grantId ?? null : options.workspaceGrant, inbox: [], receiptActivity } } as unknown as BusinessContextValue;
  const i18n = await translate(options.language ?? "es-419");
  const host = document.createElement("div"); document.body.appendChild(host); const root = createRoot(host);
  let reloads = 0;
  const render = () => root.render(<StrictMode><I18nextProvider i18n={i18n}><BusinessContext.Provider value={{ ...context }}>{options.topLevel ? <BusinessReportsPanel /> : <ConnectedBusinessReports defaultCurrency={context.records.workspace!.records_default_currency} initial={options.initial} scope={{ userId: "synthetic-person", businessId: fixtureId(3000), grantId: options.grantId ?? null }} />}</BusinessContext.Provider></I18nextProvider></StrictMode>);
  const rerender = () => act(async () => render());
  context.reload = () => {
    reloads += 1;
    void source.workspace().then((workspace) => { context.records.workspace = workspace; context.records.workspaceGrant = options.grantId ?? null; context.records.error = false; context.records.refused = false; render(); });
  };
  if (options.workspaceFailure) {
    if (options.workspaceFailure === "missing_default") Object.assign(context.records.workspace!, { records_default_currency: "CAD" });
    else { context.records.workspace = null; context.records.error = true; context.records.refused = options.workspaceFailure === "refused"; context.records.failureReference = "SYNTHETIC-REF"; }
  }
  await rerender();
  cleanup = async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; globalThis.getComputedStyle = computedStyle; URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; };
  const settle = async (predicate: () => boolean) => { for (let i = 0; i < 80; i++) { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); }); if (predicate()) return; } throw new Error(`Missing state ${document.body.textContent?.slice(-600)}`); };
  const click = async (element: Element | undefined | null) => { assert.ok(element); await act(async () => (element as HTMLElement).click()); };
  const button = (label: string) => [...document.querySelectorAll("button")].find((button) => button.textContent?.trim() === label || label === "Filtros" && button.textContent?.startsWith("Filtros") || button.getAttribute("aria-label") === label);
  const type = async (element: HTMLInputElement | HTMLTextAreaElement, value: string) => { await act(async () => { const prototype = element instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(element, value); element.dispatchEvent(new Event("input", { bubbles: true })); }); };
  if (options.waitForAnswer !== false) await settle(() => document.querySelector(`[data-report-schema="${options.legacy ? 1 : 2}"] [data-testid="records-count"]`) !== null);
  return { fixture, settle, click, button, type, downloads, opened, context, rerender, reloads: () => reloads };
}
