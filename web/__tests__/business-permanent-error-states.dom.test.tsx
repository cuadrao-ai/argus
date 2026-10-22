import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { loadRecovery, refusedForGood } from "@/lib/failure-screen";
import { createHttpMonthCloseClient, createMockMonthCloseClient, type MonthCloseClient } from "@/lib/business-month-close";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import { renderMonthCloseView } from "./helpers/month-close-view";

// A server that refuses on purpose says so with a status and a code. Asking
// again gets the same answer, so the screen offers no Reintentar and does not
// blame the connection. Any other failure can pass, so Reintentar stays.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  document.body.innerHTML = "";
});

/** A failure shaped the way the API client throws it. */
const refusal = (status: number, code: string) => Object.assign(new Error(`API error ${status}`), { status, code, requestId: "4ea79978-ce17-4853-b232-b2a72f4c9ce7" });
const NETWORK = () => new TypeError("Failed to fetch");

const BUSINESS_OFF = () => refusal(404, "business_unavailable");
const EMAIL_OFF = () => refusal(503, "email_capture_unavailable");
const BANK_DOWN = () => refusal(503, "business_bank_unavailable");
const SERVER_DOWN = () => refusal(500, "internal_error");

const CONNECTION_BLAME = /conexión/;
const buttons = (within: Element | null) => [...(within?.querySelectorAll("button") ?? [])].map((button) => button.textContent);

describe("which failures asking again can help", () => {
  test("the two explicit refusals are for good; each needs its status and its code together", () => {
    assert.equal(refusedForGood(BUSINESS_OFF()), true);
    assert.equal(refusedForGood(EMAIL_OFF()), true);
    assert.equal(refusedForGood(refusal(503, "business_unavailable")), false, "the code alone is not enough");
    assert.equal(refusedForGood(refusal(404, "email_capture_unavailable")), false, "the status alone is not enough");
  });

  test("a bank outage, any other 503, a 500 and a dropped request can pass", () => {
    for (const error of [BANK_DOWN(), refusal(503, "service_unavailable"), refusal(503, "unknown"), SERVER_DOWN(), NETWORK()]) {
      assert.equal(refusedForGood(error), false, String((error as { code?: string }).code ?? error.message));
      assert.equal(loadRecovery(error, true), "retry", String((error as { code?: string }).code ?? error.message));
    }
  });

  test("ended sessions, closed and revoked access keep their own paths: none reads as refused for good", () => {
    for (const error of [refusal(401, "unauthorized"), refusal(403, "forbidden"), refusal(403, "business_grant_not_live")]) {
      assert.equal(refusedForGood(error), false, (error as { code: string }).code);
    }
  });

  test("offline is the connection banner's to say, whatever the server last answered", () => {
    assert.equal(loadRecovery(NETWORK(), false), "offline");
    assert.equal(loadRecovery(BUSINESS_OFF(), false), "offline");
    assert.equal(loadRecovery(BUSINESS_OFF(), true), "refused");
    assert.equal(loadRecovery(EMAIL_OFF(), true), "refused");
  });

  test("a refusal wrapped by the month-close client is still read as one", async () => {
    const client = createHttpMonthCloseClient(async () => { throw BUSINESS_OFF(); });
    const error = await client.load("2026-10").then(() => null, (caught: unknown) => caught);
    assert.equal(refusedForGood(error), true);
    const down = createHttpMonthCloseClient(async () => { throw BANK_DOWN(); });
    assert.equal(refusedForGood(await down.load("2026-10").then(() => null, (caught: unknown) => caught)), false);
  });
});

describe("Inicio's month when a read fails", () => {
  const now = new Date(2026, 9, 18);
  /** The sample month, with its month read and its Por cobrar and Por pagar read failing through the live client. */
  function failing({ month, open }: { month?: () => unknown; open?: () => unknown }): { client: MonthCloseClient; calls: { month: number; open: number } } {
    const calls = { month: 0, open: 0 };
    const sample = createMockMonthCloseClient({ now });
    const http = (fail: () => unknown) => createHttpMonthCloseClient(async () => { throw fail(); });
    return {
      calls,
      client: {
        ...sample,
        load: async (...args) => { calls.month += 1; return month ? http(month).load(...args) : sample.load(...args); },
        openItems: async (...args) => { calls.open += 1; return open ? http(open).openItems(...args) : sample.openItems(...args); },
      },
    };
  }
  const settle = async (act: (run: () => Promise<void>) => Promise<void>, done: () => boolean, what: string) => {
    for (let i = 0; i < 40; i += 1) {
      if (done()) return;
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
    }
    throw new Error(`timed out waiting for ${what}`);
  };

  test("the server refusing the month offers no Reintentar and does not blame the connection", async () => {
    const { client } = failing({ month: BUSINESS_OFF });
    const { act, host, root } = await renderMonthCloseView(client, now);
    unmounts.push(() => act(async () => root.unmount()));
    const error = () => host.querySelector('[data-testid="month-close-error"]');
    await settle(act, () => error() !== null, "the month error");
    assert.deepEqual(buttons(error()), [], "asking again gets the same refusal");
    assert.doesNotMatch(error()!.textContent ?? "", CONNECTION_BLAME);
    assert.match(error()!.textContent ?? "", /hola@cuadrao\.ai/, "the way out is to write to us");
    assert.equal(host.querySelector('[data-testid="month-close-empty"]'), null, "a refused month is not an empty one");
    assert.equal(host.querySelector('[data-testid="month-close-checklist-ready"]'), null, "nor a ready one");
  });

  for (const [name, fail] of [["a 500", SERVER_DOWN], ["a bank outage", BANK_DOWN], ["a dropped request", NETWORK]] as const) {
    test(`${name} on the month keeps Reintentar, and Reintentar asks again`, async () => {
      const { client, calls } = failing({ month: fail });
      const { act, host, root } = await renderMonthCloseView(client, now);
      unmounts.push(() => act(async () => root.unmount()));
      const error = () => host.querySelector('[data-testid="month-close-error"]');
      await settle(act, () => error() !== null, "the month error");
      assert.deepEqual(buttons(error()), ["Reintentar"]);
      const before = calls.month;
      await act(async () => [...error()!.querySelectorAll("button")][0].click());
      await settle(act, () => calls.month > before, "the second read");
    });
  }

  test("the server refusing Por cobrar and Por pagar offers no Reintentar, never a zero, and the month still shows", async () => {
    const { client } = failing({ open: BUSINESS_OFF });
    const { act, host, root } = await renderMonthCloseView(client, now);
    unmounts.push(() => act(async () => root.unmount()));
    const error = () => host.querySelector('[data-testid="month-close-money-error"]');
    await settle(act, () => error() !== null, "the open items error");
    assert.deepEqual(buttons(error()), []);
    assert.doesNotMatch(error()!.textContent ?? "", CONNECTION_BLAME);
    assert.match(error()!.textContent ?? "", /hola@cuadrao\.ai/);
    assert.equal(host.querySelector('[data-testid="month-close-receivable"]'), null, "no Todo cobrado beside a refusal");
    assert.ok(host.querySelector('[data-testid="month-close-checklist"]'), "the month's own read still shows");
  });

  test("a 500 on Por cobrar and Por pagar keeps Reintentar", async () => {
    const { client } = failing({ open: SERVER_DOWN });
    const { act, host, root } = await renderMonthCloseView(client, now);
    unmounts.push(() => act(async () => root.unmount()));
    const error = () => host.querySelector('[data-testid="month-close-money-error"]');
    await settle(act, () => error() !== null, "the open items error");
    assert.deepEqual(buttons(error()), ["Reintentar"]);
  });
});

describe("Inicio when the Business itself does not load", () => {
  async function mountInicio(overrides: Partial<BusinessDataSource>, ready = (host: HTMLElement) => host.querySelector('[data-testid="inicio-error"]') !== null) {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
    const { setChosenGrant } = await import("@/lib/business-grant");
    setChosenGrant(null);
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const source = { ...createFixtureBusinessDataSource({ chatAvailable: true }), captures: async () => ({ items: [] }), ...overrides };
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    let context: ReturnType<typeof useBusiness> | null = null;
    function Probe() { context = useBusiness(); return <BusinessPanel />; }
    const api = () => { if (!context) throw new Error("Business context did not mount"); return context; };
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <BusinessConsentTestProvider accepted>
            <BusinessWorkspaceProvider source={source as BusinessDataSource}>
              <Probe />
            </BusinessWorkspaceProvider>
          </BusinessConsentTestProvider>
        </I18nextProvider>,
      );
    });
    unmounts.push(() => act(async () => root.unmount()));
    const error = () => host.querySelector('[data-testid="inicio-error"]');
    const settle = async (done: () => boolean) => {
      for (let i = 0; i < 80 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      assert.ok(done(), "Inicio reached the expected state");
    };
    await settle(() => ready(host));
    return { host, act, error, api, settle };
  }

  test("the server refusing the Business offers no Reintentar and does not blame the connection", async () => {
    const view = await mountInicio({ overview: async () => { throw BUSINESS_OFF(); } });
    const error = view.error()!;
    assert.deepEqual(buttons(error), []);
    assert.doesNotMatch(error.textContent ?? "", CONNECTION_BLAME);
    assert.match(error.textContent ?? "", /Cuadrao Business aún no está disponible para tu cuenta\./);
    assert.match(error.textContent ?? "", /hola@cuadrao\.ai/);
  });

  test("the provider distinguishes a pending receipt read from a settled legacy response without counts", async () => {
    const loading = await mountInicio({ receiptPage: () => new Promise<never>(() => {}) }, (host) => host.querySelector('[data-testid="month-close-receipts-status"]') !== null);
    assert.match(loading.host.querySelector('[data-testid="month-close-receipts-status"]')?.textContent ?? "", /Cargando el conteo de recibos/);
    assert.equal(loading.host.querySelector('[data-testid="month-close-receipts-status"] button'), null);
    const unknown = await mountInicio({ receiptPage: undefined, receipts: async () => [] }, (host) => /El conteo de recibos no está disponible/.test(host.textContent ?? ""));
    assert.equal(unknown.api().records.inbox?.length, 0, "the read settled successfully");
    assert.equal(unknown.host.querySelector('[data-testid="month-close-receipts-status"] button'), null);
  });

  test("a failed refresh cannot reuse an earlier known-zero count, and adjacent retry reloads", async () => {
    let failed = false;
    let reads = 0;
    const view = await mountInicio({ receiptPage: async () => {
      reads += 1;
      if (failed) throw NETWORK();
      return { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0 } };
    } }, (host) => host.querySelector('[data-testid="month-close-task-settle"]') !== null);
    await view.settle(() => view.api().records.receiptActivity?.ready_to_review_count === 0);
    failed = true;
    await view.act(async () => view.api().reload());
    await view.settle(() => view.api().records.error);
    assert.equal(view.api().records.receiptActivity?.ready_to_review_count, 0, "the workspace retains its earlier answer");
    assert.match(view.host.querySelector('[data-testid="month-close-receipts-status"]')?.textContent ?? "", /No pudimos cargar el conteo de recibos/);
    assert.equal(Boolean(view.host.querySelector('[data-testid="month-close-close"]')), false);
    assert.equal(view.host.querySelectorAll('[data-testid="inicio-error"]').length, 1, "the failure appears once");
    const before = reads;
    failed = false;
    const retry = view.host.querySelector<HTMLButtonElement>('[data-testid="month-close-receipts-status"] button');
    assert.ok(retry);
    await view.act(async () => retry.click());
    await view.settle(() => !view.api().records.error);
    assert.ok(reads > before);
    assert.equal(view.host.querySelector('[data-testid="month-close-receipts-status"]'), null);
  });

  test("a dropped request keeps Reintentar", async () => {
    const view = await mountInicio({ overview: async () => { throw NETWORK(); } });
    const error = view.error()!;
    assert.deepEqual(buttons(error), ["Reintentar"]);
  });
});
