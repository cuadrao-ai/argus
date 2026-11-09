import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { businessSettlementAvailable } from "../lib/business-api";
import { createMockMonthCloseClient, readMonthCloseWire, type MonthCloseClient } from "../lib/business-month-close";
import { homeSectionOrder, savedSectionOrder } from "../components/business-app/inicio/HomeOverviewDraft";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const now = new Date(2026, 9, 18);

/**
 * The month read while settlement is off: no receivables, payables, line statuses, methods, counts by status or ITBIS
 * cobrado. The net is final unless a rate is pending, and here it is negative: income 1,000.00 minus expenses 1,600.00.
 */
function offWire(currencies: Record<string, unknown>[] = [{ currency: "DOP", income_before_itbis_minor: 100000, expense_before_itbis_minor: 160000, net_result_minor: -60000, itbis_charged_minor: 18000, itbis_owed_minor: 1800, net_result_final: true }]) {
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
    currencies,
    missing_rnc: [line],
    missing_ncf: [],
    missing_fiscal_data: [{ ...line, missing: ["rnc_missing"] }],
    unreviewed_movements_count: 0,
    filing_ready: false,
  };
}

/** A server with settlement off: the month reads; anything settlement would ask for fails the test. */
function offClient(wire = offWire()): MonthCloseClient {
  const refused = async () => { throw new Error("settlement is off"); };
  return { mode: "http", async load() { return readMonthCloseWire(wire); }, openItems: refused, markCobrado: refused, markPagado: refused, markPendiente: refused, closeMonth: refused };
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
    assert.deepEqual(snapshot.figures.map((block) => [block.net_before_itbis, block.itbis_charged, block.itbis_cobrado, block.pending_count, block.net_result_final]), [["-600.00", "180.00", null, null, true]]);
  });

  for (const layout of ["finance", "inicio"] as const) {
    test(`${layout}: no Por cobrar, Por pagar, mark, settle row or "left to mark" line, and the open items are never read`, async () => {
      const { calls, client } = counted(offClient());
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
      } finally {
        await act(async () => root.unmount());
        host.remove();
      }
    });

    test(`${layout}: the net is the server's income minus approved expenses, a plain negative, and ITBIS en ventas replaces ITBIS cobrado`, async () => {
      const { act, host, root } = await render(offClient(), false, layout);
      try {
        const net = host.querySelector<HTMLElement>('[data-testid="month-close-net"]')!;
        assert.equal(net.getAttribute("data-state"), "final");
        assert.equal(net.getAttribute("data-amount"), "-600.00");
        assert.match(net.textContent ?? "", /-RD\$ 600\.00/);
        assert.match(net.textContent ?? "", /Ingresos menos gastos aprobados/);
        assert.equal(/pérdida/i.test(host.textContent ?? ""), false);
        assert.equal([net, ...net.querySelectorAll("*")].some((element) => /9e2f39|d66d75|ec9aa0|red/.test(element.getAttribute("class") ?? "")), false, "no red on a negative month");
        const sales = host.querySelector('[data-testid="month-close-itbis-sales"]');
        assert.ok(sales);
        assert.match(host.querySelector('[data-testid="month-close-itbis"]')?.textContent ?? "", /ITBIS en ventas RD\$ 180\.00/);
        assert.equal(host.querySelector('[data-testid="month-close-itbis-cobrado"]'), null);
        assert.equal(host.textContent?.includes("ITBIS cobrado"), false);
      } finally {
        await act(async () => root.unmount());
        host.remove();
      }
    });

    test(`${layout}: a pending rate still holds the net while settlement is off`, async () => {
      const usd = { currency: "USD", income_before_itbis_minor: 5000, expense_before_itbis_minor: 0, net_result_minor: 5000, itbis_charged_minor: 0, itbis_owed_minor: 0, net_result_final: false };
      const { act, host, root } = await render(offClient(offWire([usd])), false, layout);
      try {
        const net = host.querySelector('[data-testid="month-close-net"]')!;
        assert.equal(net.getAttribute("data-state"), "pending");
        assert.match(net.textContent ?? "", /pendiente de tasa/);
        assert.equal(net.textContent?.includes("Ingresos menos gastos aprobados"), false);
      } finally {
        await act(async () => root.unmount());
        host.remove();
      }
    });

    test(`${layout}: the sample books answer as a server with settlement off`, async () => {
      const { act, host, root } = await render(createMockMonthCloseClient({ now, settlement: false }), false, layout);
      try {
        const net = host.querySelector('[data-testid="month-close-net"]')!;
        assert.equal(net.getAttribute("data-state"), "final");
        assert.match(net.textContent ?? "", /Ingresos menos gastos aprobados/);
        assert.equal(/pendiente de tasa|Falta marcar/.test(host.textContent ?? ""), false);
        assert.ok(host.querySelector('[data-testid="month-close-itbis-sales"]'));
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
        assert.ok(host.querySelector('[data-testid="month-close-itbis-cobrado"]'));
        assert.equal(host.querySelector('[data-testid="month-close-itbis-sales"]'), null);
        assert.equal(host.textContent?.includes("Ingresos menos gastos aprobados"), false);
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

  test("a saved place for Cobros y pagos survives Inicio loading before the workspace says settlement is on", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const { useHomeOrder } = await import("../components/business-app/inicio/HomeOverviewDraft");
    localStorage.setItem("cuadrao:home_section_order:v1", JSON.stringify({ "ana:biz": ["money", "work", "month"] }));
    const seen: string[][] = [];
    function Probe({ shown }: { shown: ("work" | "month" | "money")[] }) {
      seen.push(useHomeOrder("ana", "biz", shown).order);
      return null;
    }
    const host = document.createElement("div");
    const root = createRoot(host);
    try {
      await act(async () => root.render(<Probe shown={["work", "month"]} />));
      await act(async () => root.render(<Probe shown={["work", "month", "money"]} />));
      assert.deepEqual(seen.at(0), ["work", "month"]);
      assert.deepEqual(seen.at(-1), ["money", "work", "month"]);
    } finally {
      await act(async () => root.unmount());
      localStorage.removeItem("cuadrao:home_section_order:v1");
    }
  });

  test("reordering while Cobros y pagos is hidden keeps its saved place for when it shows again", () => {
    assert.deepEqual(savedSectionOrder(["money", "work", "month"], ["month", "work"]), ["money", "month", "work"]);
    assert.deepEqual(savedSectionOrder(["work", "money", "month"], ["month", "work"]), ["month", "money", "work"]);
    assert.deepEqual(savedSectionOrder(["work", "month", "money"], ["money", "month", "work"]), ["money", "month", "work"]);
  });
});
