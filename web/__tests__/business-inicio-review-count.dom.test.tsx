import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import BusinessSidebarNav from "@/components/business-app/BusinessSidebarNav";
import { HomeAttention } from "@/components/business-app/inicio/HomeAttention";
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
  const opened: BusinessContextValue["panel"][] = [];
  let context = {
    chosen: { space_id: fixtureId(3000), grant_id: fixtureId(3001), role: "owner", name: "Negocio sintético", capabilities: ["read"], permissions: ["read"] },
    userId: "synthetic-person", source: { ...source, mode: "live" }, revision: 0,
    actions: { create: [] }, panel: { kind: "overview" }, invoicing: "unavailable",
    openPanel: (panel: BusinessContextValue["panel"]) => { opened.push(panel); }, reload: () => { reloads += 1; },
    records: { workspace: await source.workspace(), inbox: [], notes: [], emails: [], error: false, receiptActivity: null },
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
      <BusinessSidebarNav shell={shell} /><HomeAttention firstDay={false} />
      {showReports ? <ConnectedBusinessReports defaultCurrency={context.records.workspace!.records_default_currency} scope={{ userId: "synthetic-person", businessId: fixtureId(3000), grantId: null }} /> : null}
    </BusinessContext.Provider></I18nextProvider>,
  ));
  cleanup = async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; };
  await render();
  return {
    host, fixture, opened, reloads: () => reloads,
    update: async (count: number | null, failure: Partial<BusinessContextValue["records"]> = {}) => {
      context = { ...context, records: { ...context.records, receiptActivity: activity(count), error: false, failureReference: null, serverReference: null, ...failure } };
      await render();
    },
  };
}

function counts(host: HTMLElement, expected: number) {
  assert.equal(host.querySelector('[data-testid="business-inbox-count"]')?.textContent, String(expected));
  // Necesita atención is everything waiting in the Bandeja: the sidebar's one count.
  assert.equal(host.querySelector('[data-testid="home-attention-count"]')?.textContent, String(expected));
}

test("Inicio and the Bandeja use the same server count and follow its updates", async () => {
  const page = await mount(28);
  counts(page.host, 28);
  const reportRequests = page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  await page.update(1);
  counts(page.host, 1);
  await page.update(0);
  for (const id of ["home-attention-count", "business-inbox-count"]) {
    assert.equal(page.host.querySelector(`[data-testid="${id}"]`), null, id);
  }
  assert.match(page.host.querySelector('[data-testid="home-attention"]')?.textContent ?? "", /Todo al día/);
  assert.equal(page.fixture.calls.filter((call) => call.path.endsWith("/reports/query")).length, reportRequests, "receipt activity updates do not request another report");
});

test("Inicio offers retry without requesting a report when a completed receipt read has no count", async () => {
  const page = await mount(null, false);
  assert.ok(page.host.querySelector('[data-testid="home-attention-error"]'));
  assert.equal(page.host.querySelector('[data-testid="home-attention"] [aria-busy="true"]'), null);
  assert.equal(page.fixture.calls.length, 0);
  await page.update(28);
  assert.equal(page.host.querySelector('[data-testid="home-attention-count"]')?.textContent, "28");
});

test("a failed shared receipt load keeps its reference and retries that load", async () => {
  const page = await mount(null, false);
  await page.update(null, { error: true, failureReference: "receipt-count-test" });
  const section = page.host.querySelector('[data-testid="home-attention"]')!;
  assert.ok(section.textContent?.includes("receipt-count-test"));
  const retry = [...section.querySelectorAll("button")].find((button) => button.textContent === "Reintentar");
  assert.ok(retry);
  await act(async () => retry.click());
  assert.equal(page.reloads(), 1);
  assert.equal(page.fixture.calls.length, 0);
});


test("an unavailable shared receipt count shows its reference instead of an endless skeleton", async () => {
  const page = await mount(null, false);
  await page.update(null, { inbox: null, serverReference: "receipt-service-test" });
  const failure = page.host.querySelector('[data-testid="home-attention"]');
  assert.ok(failure);
  assert.ok(failure.textContent?.includes("receipt-service-test"));
  assert.equal(page.host.querySelector('[data-testid="home-attention"] [aria-busy="true"]'), null);
  const retry = [...failure.querySelectorAll("button")].find((button) => button.textContent === "Reintentar");
  assert.ok(retry);
  await act(async () => retry.click());
  assert.equal(page.reloads(), 1);
  assert.equal(page.fixture.calls.length, 0);
});


test("Ver todo opens the Bandeja in its normal view: no tab, no filter", async () => {
  const page = await mount(28, false);
  const seeAll = page.host.querySelector<HTMLButtonElement>('[data-testid="home-attention-see-all"]');
  assert.ok(seeAll);
  await act(async () => seeAll.click());
  assert.deepEqual(page.opened, [{ kind: "inbox" }]);
});
