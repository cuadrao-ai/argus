import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { businessSettlementAvailable } from "../lib/business-api";
import { createMockMonthCloseClient, readMonthCloseWire, type MonthCloseClient } from "../lib/business-month-close";
import { homeSectionOrder } from "../components/business-app/inicio/HomeOverviewDraft";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const now = new Date(2026, 9, 18);

/** The month read while settlement is off: no receivables, payables, line statuses or methods. The figures keep their meaning. */
function offWire() {
  const line = { activity_id: "sale-1", document_kind: "invoice", currency: "DOP", occurred_on: "2026-10-05", total_minor: 11800, total: "118.00", before_itbis_minor: 10000, before_itbis: "100.00", itbis_minor: 1800, itbis: "18.00", counterparty: "Colmado Ana", rnc: null, ncf: "B0100000001", ecf: null, sin_comprobante: false, due_on: null };
  return {
    month: "2026-10",
    today: "2026-10-18",
    from: "2026-10-01",
    to: "2026-10-31",
    closed: false,
    reasons: [{ code: "missing_rnc", activity_id: "sale-1", document_kind: "invoice" }],
    earliest_month: "2026-10",
    dgii_forms: { "606": "no_operations", "607": "needs_review" },
    currencies: [{ currency: "DOP", income_before_itbis_minor: 10000, expense_before_itbis_minor: 0, net_result_minor: 10000, itbis_owed_minor: 1800, itbis_cobrado_minor: 0, net_result_final: false, by_status: { invoices: { pendiente: { count: 1, before_itbis_minor: 10000 }, cobrado: { count: 0, before_itbis_minor: 0 } }, receipts: { pendiente: { count: 0, before_itbis_minor: 0 }, pagado: { count: 0, before_itbis_minor: 0 } } } }],
    missing_rnc: [line],
    missing_ncf: [],
    missing_fiscal_data: [{ ...line, missing: ["rnc_missing"] }],
    unreviewed_movements_count: 0,
    filing_ready: false,
  };
}

/** Counts every call, so a test can say the open items were never read. */
function counted(client: MonthCloseClient) {
  const calls: string[] = [];
  const wrap = <K extends keyof MonthCloseClient>(name: K) => (async (...args: unknown[]) => {
    calls.push(String(name));
    return (client[name] as (...rest: unknown[]) => Promise<unknown>)(...args);
  }) as MonthCloseClient[K];
  const spy: MonthCloseClient = { ...client, load: wrap("load"), openItems: wrap("openItems"), markCobrado: wrap("markCobrado"), markPagado: wrap("markPagado"), markPendiente: wrap("markPendiente") };
  return { calls, client: spy };
}

async function render(client: MonthCloseClient, settlement: boolean, layout: "finance" | "inicio") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("../public/locales/es-419/common.json")).default;
  const { BusinessMonthCloseView } = await import("../components/business-app/BusinessMonthClosePanel");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessMonthCloseView client={client} now={now} businessCurrency="DOP" settlement={settlement} layout={layout} review={{ count: 0, detail: null, open() {} }} />
      </I18nextProvider>,
    );
  });
  for (let i = 0; i < 10; i += 1) await act(async () => { await Promise.resolve(); });
  // Finance keeps the close steps behind "Ver cuáles": open them so every step is in the page.
  const toggle = host.querySelector<HTMLButtonElement>('[data-testid="month-close-tasks-toggle"]');
  if (toggle) await act(async () => { toggle.click(); });
  return { act, host, root };
}

describe("Por cobrar and Por pagar while settlement is off", () => {
  test("only the server's explicit answer turns settlement on", () => {
    assert.equal(businessSettlementAvailable(null), false);
    assert.equal(businessSettlementAvailable({} as never), false);
    assert.equal(businessSettlementAvailable({ settlement_available: false } as never), false);
    assert.equal(businessSettlementAvailable({ settlement_available: true } as never), true);
  });

  test("the month read without settlement state parses, and no document carries a status", () => {
    const snapshot = readMonthCloseWire(offWire());
    assert.deepEqual(snapshot.documents.map((document) => [document.id, document.status, document.missing]), [["sale-1", null, ["rnc_missing"]]]);
    assert.equal(snapshot.payment_methods, null);
    assert.deepEqual(snapshot.figures.map((block) => [block.itbis_cobrado, block.pending_count, block.net_result_final]), [["0.00", 1, false]]);
  });

  for (const layout of ["finance", "inicio"] as const) {
    test(`${layout}: no Por cobrar, Por pagar, mark, settle row or "left to mark" line, and the open items are never read`, async () => {
      const { calls, client } = counted(createMockMonthCloseClient({ now }));
      const { act, host, root } = await render(client, false, layout);
      try {
        assert.ok(host.querySelector('[data-testid="month-close-cards"]'), "the month's figures still show");
        for (const id of ["month-close-money", "month-close-receivable", "month-close-payable", "month-close-task-settle", "month-close-mark-cobrado", "month-close-mark-pagado", "month-close-nothing-open", "month-close-money-loading"]) {
          assert.equal(host.querySelector(`[data-testid="${id}"]`), null, id);
        }
        for (const words of ["Por cobrar", "Por pagar", "pagado", "Falta marcar", "Faltan marcar", "vencid"]) {
          assert.equal(host.textContent?.includes(words), false, words);
        }
        assert.deepEqual([...new Set(calls)], ["load"]);
        // The net and ITBIS cobrado keep the server's meaning; only the line asking for a mark goes.
        assert.ok(host.querySelector('[data-testid="month-close-itbis-cobrado"]'));
      } finally {
        await act(async () => root.unmount());
        host.remove();
      }
    });

    test(`${layout}: with settlement on, Por cobrar and Por pagar show as before`, async () => {
      const { calls, client } = counted(createMockMonthCloseClient({ now }));
      const { act, host, root } = await render(client, true, layout);
      try {
        assert.ok(host.querySelector('[data-testid="month-close-receivable"]'));
        assert.ok(host.querySelector('[data-testid="month-close-payable"]'));
        assert.ok(host.querySelector('[data-testid="month-close-task-settle"]'));
        assert.ok(calls.includes("openItems"));
        assert.match(host.querySelector('[data-testid="month-close-net"]')?.textContent ?? "", /Falta marcar/);
      } finally {
        await act(async () => root.unmount());
        host.remove();
      }
    });
  }

  test("Inicio's sections leave out Cobros y pagos while it is off, and keep the person's order of the rest", () => {
    assert.deepEqual(homeSectionOrder(undefined, ["work", "month"]), ["work", "month"]);
    assert.deepEqual(homeSectionOrder(["money", "month", "work"], ["work", "month"]), ["month", "work"]);
    assert.deepEqual(homeSectionOrder(["month", "work"], ["work", "month", "money"]), ["month", "work", "money"]);
    assert.deepEqual(homeSectionOrder(["money", "month", "work"], ["work", "month", "money"]), ["money", "month", "work"]);
    assert.deepEqual(homeSectionOrder("broken", ["work", "month", "money"]), ["work", "month", "money"]);
  });
});
