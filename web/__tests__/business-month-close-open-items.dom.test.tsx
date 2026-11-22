import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, createMockMonthCloseClient, MonthCloseError, openItemsFrom, type MonthCloseClient, type MonthCloseDocument } from "../lib/business-month-close";
import { renderMonthCloseView } from "./helpers/month-close-view";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const now = new Date(2026, 9, 18);

function statusCell(count: number, beforeItbisMinor: number) {
  return { count, before_itbis_minor: beforeItbisMinor };
}

function settledByStatus() {
  return {
    invoices: { pendiente: statusCell(0, 0), cobrado: statusCell(1, 100000) },
    receipts: { pendiente: statusCell(0, 0), pagado: statusCell(1, 50000) },
  };
}


const renderView = (client: MonthCloseClient, businessCurrency: string | null = null) => renderMonthCloseView(client, now, businessCurrency);

describe("foreign currency lines", () => {
  const line = (activityId: string, kind: "invoice" | "receipt", currency: string, occurredOn: string, totalMinor: number, itbisMinor: number | null) => ({
    activity_id: activityId,
    document_kind: kind,
    currency,
    occurred_on: occurredOn,
    total_minor: totalMinor,
    before_itbis_minor: totalMinor - (itbisMinor ?? 0),
    itbis_minor: itbisMinor,
    status: "pendiente",
    counterparty: `Cliente ${activityId}`,
  });

  const mixedCurrencyClient = () =>
    createHttpMonthCloseClient(async (path) => path === "/business/open-items" ? ({
      cuentas_por_cobrar: {
        count: 2,
        totals: [{ currency: "USD", total_minor: 5000, total: "50.00" }, { currency: "DOP", total_minor: 118000, total: "1180.00" }],
        items: [line("act-dop", "invoice", "DOP", "2026-09-04", 118000, 18000), line("act-usd", "invoice", "USD", "2026-10-06", 5000, null)],
      },
      cuentas_por_pagar: {
        count: 1,
        totals: [{ currency: "EUR", total_minor: 2000, total: "20.00" }],
        items: [line("act-eur", "receipt", "EUR", "2026-10-07", 2000, null)],
      },
    }) : ({
      month: "2026-10",
      today: "2026-10-18",
      payment_methods: ["efectivo", "otro"],
      from: "2026-10-01",
      to: "2026-10-31",
      closed: false,
      reasons: [],
      currencies: [{
        currency: "DOP",
        income_before_itbis_minor: 100000, income_before_itbis: "1000.00",
        expense_before_itbis_minor: 0, expense_before_itbis: "0.00",
        net_result_minor: 100000, net_result: "1000.00",
        itbis_paid_minor: 1800, itbis_paid: "18.00",
      }],
      missing_rnc: [],
      missing_ncf: [],
      missing_fiscal_rows: [],
      cuentas_por_cobrar: [line("act-usd", "invoice", "USD", "2026-10-06", 5000, null)],
      cuentas_por_pagar: [line("act-eur", "receipt", "EUR", "2026-10-07", 2000, null)],
    }));

  test("the total names RD$, a USD row keeps US$, each currency has its own total, and the DOP cards leave both out", async () => {
    const { act, host, root } = await renderView(mixedCurrencyClient(), "DOP");
    const receivable = host.querySelector('[data-testid="month-close-receivable"]');
    const payable = host.querySelector('[data-testid="month-close-payable"]');
    const amountOf = (id: string) => host.querySelector(`[data-document-id="${id}"] .cuadrao-amount`)?.textContent;
    assert.equal(receivable?.querySelector("h4")?.textContent, "Por cobrar");
    assert.equal(amountOf("act-dop"), "1,180.00", "a row in the total's currency is the number alone");
    assert.equal(amountOf("act-usd"), "US$ 50.00", "a row in another currency keeps its own symbol");
    assert.match(host.querySelector('[data-document-id="act-dop"]')?.textContent ?? "", /Cliente act-dop/, "the open item names its counterparty");
    const totals = [...(receivable?.querySelectorAll('[data-testid="month-close-receivable-total"]') ?? [])].map((node) => [node.getAttribute("data-currency"), node.textContent]);
    assert.deepEqual(totals, [["DOP", "RD$ 1,180.00"], ["USD", "US$ 50.00"]], "one total per currency, DOP first, never added together");
    assert.equal(receivable?.textContent?.includes("1,230"), false);
    assert.equal(payable?.querySelector("h4")?.textContent, "Por pagar");
    assert.equal(payable?.querySelector('[data-testid="month-close-payable-total"]')?.textContent, "€ 20.00");
    assert.equal(amountOf("act-eur"), "20.00");
    assert.match(host.querySelector('[data-testid="home-month-income"]')?.textContent ?? "", /RD\$ 1,000(?![.\d])/);
    assert.equal(host.querySelector('[data-testid="home-month-income"]')?.textContent?.includes("US$"), false);
    await act(async () => root.unmount());
    host.remove();
  });

  test("with no known Business currency no header is guessed: every row keeps its own symbol and totals keep the server's order", async () => {
    const { act, host, root } = await renderView(mixedCurrencyClient());
    const receivable = host.querySelector('[data-testid="month-close-receivable"]');
    const amountOf = (id: string) => host.querySelector(`[data-document-id="${id}"] .cuadrao-amount`)?.textContent;
    assert.equal(amountOf("act-dop"), "RD$ 1,180.00");
    assert.equal(amountOf("act-usd"), "US$ 50.00");
    const totals = [...(receivable?.querySelectorAll('[data-testid="month-close-receivable-total"]') ?? [])].map((node) => node.getAttribute("data-currency"));
    assert.deepEqual(totals, ["USD", "DOP"]);
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("open items across months", () => {
  test.each(["DOP", null])("pending totals remain visible, including empty payable with currency %s", async (businessCurrency) => {
    const items = Array.from({ length: 5 }, (_, index) => ({
      activity_id: `act-${index}`,
      document_kind: "invoice",
      currency: "DOP",
      occurred_on: `2026-0${index + 4}-10`,
      total_minor: 100000,
      before_itbis_minor: 100000,
      itbis_minor: null,
      status: "pendiente",
      counterparty: `Cliente ${index}`,
    }));
    const client = createHttpMonthCloseClient(async (path) => path === "/business/open-items" ? ({
      today: "2026-10-18",
      cuentas_por_cobrar: { count: 107, totals: [{ currency: "DOP", total_minor: 10700000, total: "107000.00" }], items },
      cuentas_por_pagar: { count: 0, totals: [], items: [] },
    }) : ({
      month: "2026-10",
      today: "2026-10-18",
      payment_methods: ["efectivo", "otro"],
      from: "2026-10-01",
      to: "2026-10-31",
      closed: true,
      reasons: [],
      currencies: [{ currency: "DOP", income_before_itbis_minor: 0, income_before_itbis: "0.00", expense_before_itbis_minor: 0, expense_before_itbis: "0.00", net_result_minor: 0, net_result: "0.00", itbis_paid_minor: 0, itbis_paid: "0.00", by_status: settledByStatus(), net_result_final: true }],
      missing_rnc: [],
      missing_ncf: [],
      missing_fiscal_rows: [],
      cuentas_por_cobrar: [],
      cuentas_por_pagar: [],
    }));
    const { act, host, root } = await renderView(client, businessCurrency);
    const column = () => host.querySelector('[data-testid="month-close-receivable"]');
    assert.ok(column()?.querySelector('[data-document-id="act-0"]'), "an April invoice shows while October is open");
    assert.equal(column()?.querySelector('[data-testid="month-close-receivable-total"]')?.textContent, "RD$ 107,000.00", "the total is the server's, past the cap, exact");
    assert.equal(column()?.querySelector('[data-testid="month-close-receivable-beyond"]')?.textContent, "Y 102 más que no se muestran aquí.");
    const toggle = [...(column()?.querySelectorAll("button") ?? [])].find((item) => item.hasAttribute("aria-expanded"));
    assert.equal(toggle?.textContent, "Ver las 5");
    await act(async () => { toggle?.click(); });
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 5);
    assert.match(host.querySelector('[data-testid="month-close-payable-empty"]')?.textContent ?? "", /No tienes cuentas esperando pago/);
    const payableTotal = host.querySelector('[data-testid="month-close-payable-total"]');
    assert.ok(payableTotal, "an empty card keeps the total header");
    assert.equal(payableTotal.getAttribute("data-currency"), businessCurrency);
    if (businessCurrency) assert.equal(payableTotal.textContent, "RD$ 0.00");
    else assert.ok(!payableTotal.textContent?.includes("0.00"), "unknown currency must not become a zero balance");
    await act(async () => root.unmount());
    host.remove();
  });

  test("an empty month still shows what earlier months left pending", async () => {
    const pending: MonthCloseDocument = {
      id: "inv-sept",
      kind: "invoice",
      currency: "DOP",
      counterparty: "Clínica Aurora",
      occurred_on: "2026-09-12",
      due_on: null,
      amount: "59.00",
      itbis: "9.00",
      rnc: "101-88877-6",
      ncf: "B0100000001",
      ecf: null,
      status: "pendiente",
    };
    const client: MonthCloseClient = {
      mode: "mock",
      async load(month) { return { month, from: `${month}-01`, to: `${month}-31`, closed_at: null, unreviewed_movements: 0, earliest_month: null, today: "2026-10-18", payment_methods: ["otro"], dgii_forms: null, documents: [], figures: [], fiscal_rows: [], not_ready_rows: [] }; },
      async openItems() { return openItemsFrom([pending], "2026-10-18"); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
    };
    const { act, host, root } = await renderView(client);
    assert.ok(host.querySelector('[data-testid="home-month-first-day"]'));
    assert.match(host.querySelector('[data-document-id="inv-sept"]')?.textContent ?? "", /Clínica Aurora/);
    assert.match(host.querySelector('[data-document-id="inv-sept"]')?.textContent ?? "", /12 Sept/);
    assert.ok(!(host.textContent ?? "").includes("\u2014"), "Pendiente hoy never shows the long dash");
    await act(async () => root.unmount());
    host.remove();
  });

  test("a failed open-items read says so with Reintentar and never shows a zero", async () => {
    let fail = true;
    const inner = createMockMonthCloseClient({ now });
    const client: MonthCloseClient = {
      ...inner,
      async openItems(scope) {
        if (fail) throw new MonthCloseError("unavailable", "down");
        return inner.openItems(scope);
      },
    };
    const { act, host, root } = await renderView(client);
    const error = host.querySelector('[data-testid="month-close-money-error"]');
    assert.match(error?.textContent ?? "", /No pudimos cargar lo que falta por cobrar y por pagar/);
    assert.equal(host.querySelector('[data-testid="month-close-nothing-open"]'), null);
    fail = false;
    await act(async () => { error?.querySelector("button")?.click(); });
    await act(async () => { await Promise.resolve(); });
    assert.ok(host.querySelector('[data-testid="month-close-receivable"] [data-document-id="inv-luna"]'));
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("overview figures", () => {
  test("Inicio's totals read in whole units through the one formatter, never compact; the list rows keep their cents", async () => {
    const { act, host, root } = await renderView(createMockMonthCloseClient({ now }));
    const amount = (testId: string) => host.querySelector(`[data-testid="${testId}"]`)?.textContent;
    assert.equal(amount("home-month-income"), "RD$ 58,400");
    assert.equal(amount("home-month-expenses"), "RD$ 9,600");
    assert.doesNotMatch(host.querySelector('[data-testid="home-month"]')?.textContent ?? "", /\bmil\b|\d M\b/, "no compact form");
    assert.match(host.querySelector('[data-testid="month-close-receivable"]')?.textContent ?? "", /\d\.\d\d/, "a row keeps its cents");
    await act(async () => root.unmount());
    host.remove();
  });
});


describe("compact settled guidance", () => {
  test("keeps the explanation and calls the supplied next action", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const { EmptyState } = await import("../components/business-app/foundation/EmptyState");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    let added = 0;
    try {
      await act(async () => {
        root.render(<EmptyState kind="done" settled title="Todo pagado" body="No tienes cuentas esperando pago." action={{ label: "Agregar", run: () => { added += 1; } }} />);
      });
      assert.match(host.textContent ?? "", /No tienes cuentas esperando pago/);
      const button = host.querySelector("button");
      assert.ok(button, "settled guidance must not discard its supplied action");
      await act(async () => button.click());
      assert.equal(added, 1);
    } finally {
      await act(async () => root.unmount());
      host.remove();
    }
  });
});


test.each([
  ["receivable", "receipt", "Nadie te debe ahora mismo."],
  ["payable", "invoice", "No tienes cuentas esperando pago."],
] as const)("empty %s keeps its explanation and zero total without an Add action", async (card, remainingKind, explanation) => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("../public/locales/es-419/common.json")).default;
  const { BusinessMonthCloseView } = await import("../components/business-app/BusinessMonthClosePanel");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const inner = createMockMonthCloseClient({ now });
  const client: MonthCloseClient = {
    ...inner,
    async openItems(scope) {
      const items = await inner.openItems(scope);
      return openItemsFrom([...items.cuentas_por_cobrar.items, ...items.cuentas_por_pagar.items].filter((item) => item.kind === remainingKind), items.today);
    },
  };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  try {
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessMonthCloseView layout="finance" arrange={({ month, money }) => <>{month}{money}</>} settlement client={client} now={now} businessCurrency="DOP" /></I18nextProvider>); });
    const empty = host.querySelector(`[data-testid="month-close-${card}-empty"]`);
    assert.ok(empty?.textContent?.includes(explanation), "either settled balance explains why its list is empty");
    const button = empty?.querySelector("button");
    assert.equal(button, null, "Inicio offers no Add action inside a settled card");
    assert.equal(host.querySelector(`[data-testid="month-close-${card}-total"]`)?.textContent, "RD$ 0.00");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
