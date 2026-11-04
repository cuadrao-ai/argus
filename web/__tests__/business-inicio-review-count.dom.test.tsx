import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import BusinessSidebarNav from "@/components/business-app/BusinessSidebarNav";
import { HomeWork } from "@/components/business-app/inicio/HomeOverviewDraft";
import { ConnectedBusinessReports } from "@/components/business-app/transacciones/BusinessReportsPanel";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import { setChosenGrant } from "@/lib/business-grant";
import spanish from "@/public/locales/es-419/common.json";
import { createBusinessReportHttpFixture, fixtureId } from "./fixtures/business-report-http-fixture";
import { keepOwnListSearch } from "./fixtures/own-list-search";

await keepOwnListSearch();

let cleanup = async () => {};
const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });
afterAll(async () => {
  await GlobalRegistrator.unregister();
  if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock;
});

const shell: ChatShellBridge = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };

async function mount(waiting: number | null, showReports = true) {
  const { createRoot } = await import("react-dom/client");
  const fixture = createBusinessReportHttpFixture();
  fixture.controls.overview.needs_review = 6;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = fixture.request as typeof fetch;
  setChosenGrant(null);
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  let reloads = 0;
  let context = {
    chosen: { space_id: fixtureId(3000), grant_id: fixtureId(3001), role: "owner", name: "Negocio sintético", capabilities: ["read"], permissions: ["read"] },
    userId: "synthetic-person", source: { ...source, mode: "live" }, revision: 0,
    actions: { create: [] }, panel: { kind: "overview" }, invoicing: "unavailable",
    openPanel: () => undefined, reload: () => { reloads += 1; },
    records: { workspace: await source.workspace(), inbox: [], error: false, receiptActivity: null },
  } as unknown as BusinessContextValue;
  const activity = (count: number | null) => count === null ? null : {
    reading_count: 0, unread_count: 0, presentation: "none" as const,
    pending_review_count: count, needs_attention_count: 0, ready_to_review_count: count,
    bandeja_attention_count: 0, bandeja_listo_count: count,
  };
  context = { ...context, records: { ...context.records, receiptActivity: activity(waiting) } };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  const render = () => act(async () => root.render(
    <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>
      <BusinessSidebarNav shell={shell} /><HomeWork />
      {showReports ? <ConnectedBusinessReports scope={{ userId: "synthetic-person", businessId: fixtureId(3000), grantId: null }} /> : null}
    </BusinessContext.Provider></I18nextProvider>,
  ));
  cleanup = async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; };
  await render();
  return {
    host, fixture, reloads: () => reloads,
    update: async (count: number | null, failure: Partial<BusinessContextValue["records"]> = {}) => {
      context = { ...context, records: { ...context.records, receiptActivity: activity(count), error: false, failureReference: null, serverReference: null, ...failure } };
      await render();
    },
  };
}

function counts(host: HTMLElement, expected: number) {
  assert.equal(host.querySelector('[data-testid="business-inbox-count"]')?.textContent, String(expected));
  assert.equal(host.querySelector('[data-testid="records-bandeja-waiting"]')?.textContent, expected === 1 ? "1 recibo espera en la Bandeja" : `${expected} recibos esperan en la Bandeja`);
  assert.equal(host.querySelector('[data-testid="home-records-to-review"]')?.textContent, `${expected === 1 ? "1 registro por revisar" : `${expected} registros por revisar`}Revisar`);
}

test("Inicio, Bandeja and Registros use the same server count and follow its updates", async () => {
  const page = await mount(28);
  counts(page.host, 28);
  const reportRequests = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  await page.update(1);
  counts(page.host, 1);
  await page.update(0);
  for (const id of ["home-records-to-review", "business-inbox-count", "records-bandeja-waiting"]) {
    assert.equal(page.host.querySelector(`[data-testid="${id}"]`), null, id);
  }
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length, reportRequests, "receipt activity updates do not request another report");
});

test("Inicio does not request a report while its shared receipt count is unknown", async () => {
  const page = await mount(null, false);
  assert.equal(page.host.querySelector('[data-testid="home-records-to-review"]'), null);
  assert.ok(page.host.querySelector('[data-testid="home-needs-attention"] [aria-busy="true"]'));
  assert.equal(page.fixture.calls.length, 0);
  await page.update(28);
  assert.equal(page.host.querySelector('[data-testid="home-records-to-review"]')?.textContent, "28 registros por revisarRevisar");
});

test("a failed shared receipt load keeps its reference and retries that load", async () => {
  const page = await mount(null, false);
  await page.update(null, { error: true, failureReference: "receipt-count-test" });
  const section = page.host.querySelector('[data-testid="home-needs-attention"]')!;
  assert.ok(section.textContent?.includes("receipt-count-test"));
  assert.equal(page.host.querySelector('[data-testid="home-records-to-review"]'), null);
  const retry = [...section.querySelectorAll("button")].find((button) => button.textContent === "Reintentar");
  assert.ok(retry);
  await act(async () => retry.click());
  assert.equal(page.reloads(), 1);
  assert.equal(page.fixture.calls.length, 0);
});


test("an unavailable shared receipt count shows its reference instead of an endless skeleton", async () => {
  const page = await mount(null, false);
  await page.update(null, { inbox: null, serverReference: "receipt-service-test" });
  const failure = page.host.querySelector('[data-testid="home-records-to-review-failed"]');
  assert.ok(failure);
  assert.ok(failure.textContent?.includes("receipt-service-test"));
  assert.equal(page.host.querySelector('[data-testid="home-needs-attention"] [aria-busy="true"]'), null);
  const retry = [...failure.querySelectorAll("button")].find((button) => button.textContent === "Reintentar");
  assert.ok(retry);
  await act(async () => retry.click());
  assert.equal(page.reloads(), 1);
  assert.equal(page.fixture.calls.length, 0);
});
