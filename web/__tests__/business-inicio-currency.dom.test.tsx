import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, type MonthCloseClient } from "../lib/business-month-close";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const now = new Date(2026, 9, 18);

function block(currency: string, income: number, expense: number, itbisOwed: number, pending = 0) {
  const byStatus = { invoices: { pendiente: { count: pending, before_itbis_minor: 0 }, cobrado: { count: 0, before_itbis_minor: 0 } }, receipts: { pendiente: { count: 0, before_itbis_minor: 0 }, pagado: { count: 0, before_itbis_minor: 0 } } };
  return { currency, income_before_itbis_minor: income, expense_before_itbis_minor: expense, net_result_minor: income - expense, itbis_owed_minor: itbisOwed, by_status: byStatus, net_result_final: pending === 0 };
}

function line(id: string, kind: "invoice" | "receipt", currency: string | undefined, totalMinor: number, extra: Record<string, unknown> = {}) {
  return { activity_id: id, document_kind: kind, ...(currency === undefined ? {} : { currency }), occurred_on: "2026-10-05", total_minor: totalMinor, itbis_minor: null, status: "pendiente", counterparty: `Cliente ${id}`, due_on: null, ...extra };
}

function serverWith(currencies: unknown[], lists: { cobrar?: unknown[]; pagar?: unknown[] } = {}): MonthCloseClient {
  const cobrar = lists.cobrar ?? [];
  const pagar = lists.pagar ?? [];
  const open = (items: unknown[]) => ({ count: items.length, totals: [], items });
  return createHttpMonthCloseClient(async (path) => path === "/business/open-items"
    ? { today: "2026-10-18", cuentas_por_cobrar: open(cobrar), cuentas_por_pagar: open(pagar) }
    : { month: "2026-10", today: "2026-10-18", from: "2026-10-01", to: "2026-10-31", closed: true, reasons: [], payment_methods: ["efectivo", "otro"], currencies, missing_rnc: [], missing_ncf: [], cuentas_por_cobrar: cobrar, cuentas_por_pagar: pagar });
}

const DOP_AND_USD = [block("DOP", 400000, 150000, 18000), block("USD", 120000, 2400, 21600)];

async function renderView(client: MonthCloseClient, options: { scopeKey: string; businessCurrency?: string | null; language?: "es-419" | "en" }) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("../public/locales/es-419/common.json")).default;
  const english = (await import("../public/locales/en/common.json")).default;
  const { BusinessMonthCloseView } = await import("../components/business-app/BusinessMonthClosePanel");
  const language = options.language ?? "es-419";
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessMonthCloseView client={client} now={now} scopeKey={options.scopeKey} businessCurrency={options.businessCurrency ?? null} />
      </I18nextProvider>,
    );
  });
  await act(async () => {
    await Promise.resolve();
  });
  const text = (id: string) => host.querySelector(`[data-testid="${id}"]`)?.textContent ?? "";
  const unmount = async () => {
    await act(async () => root.unmount());
    host.remove();
  };
  return { act, host, text, unmount };
}

describe("Inicio figures in every currency the month holds", () => {
  test("a USD-only month shows its own figures, not unknown, with no menu", async () => {
    const view = await renderView(serverWith([block("USD", 120000, 2400, 21600)]), { scopeKey: "usd-only" });
    assert.equal(view.host.querySelector('[data-testid="month-close-income"]')?.getAttribute("data-state"), "final");
    assert.match(view.text("month-close-income"), /US\$ 1,200\.00/);
    assert.match(view.text("month-close-expenses"), /US\$ 24\.00/);
    assert.match(view.text("month-close-net"), /US\$ 1,176\.00/);
    assert.match(view.text("month-close-itbis"), /US\$ 216\.00/);
    assert.equal(view.host.querySelector('[data-testid="month-close-currency"]'), null, "one currency needs no menu");
    assert.doesNotMatch(view.host.textContent ?? "", /RD\$/);
    await view.unmount();
  });

  test("a DOP and USD month shows DOP by default, then USD once the person chooses it, and remembers it for this Business", async () => {
    const view = await renderView(serverWith(DOP_AND_USD), { scopeKey: "two-currencies" });
    assert.match(view.text("month-close-income"), /RD\$ 4,000\.00/);
    const button = view.host.querySelector('[data-testid="month-close-currency"]');
    assert.ok(button instanceof HTMLButtonElement);
    assert.equal(button.getAttribute("aria-haspopup"), "listbox");
    assert.equal(button.getAttribute("aria-label"), "Moneda: DOP");
    assert.equal(view.text("month-close-currency-others"), "También hay movimientos en US$.");
    await view.act(async () => button.click());
    const options = [...document.querySelectorAll('[data-testid="month-close-currency-picker"] [role="option"]')];
    assert.deepEqual(options.map((option) => option.getAttribute("data-currency")), ["DOP", "USD"]);
    assert.equal(options[0]?.getAttribute("aria-selected"), "true");
    await view.act(async () => (options[1] as HTMLElement).click());
    assert.equal(document.querySelector('[data-testid="month-close-currency-picker"]'), null, "the menu closes on a choice");
    assert.match(view.text("month-close-income"), /US\$ 1,200\.00/);
    assert.match(view.text("month-close-expenses"), /US\$ 24\.00/);
    assert.match(view.text("month-close-net"), /US\$ 1,176\.00/);
    assert.match(view.text("month-close-itbis"), /US\$ 216\.00/);
    assert.doesNotMatch(view.text("month-close-cards-month"), /RD\$/);
    assert.equal(view.host.querySelector('[data-testid="month-close-currency"]')?.getAttribute("aria-label"), "Moneda: USD");
    assert.equal(view.text("month-close-currency-others"), "También hay movimientos en RD$.");
    assert.match(view.text("month-close-currency-announce"), /USD/);
    await view.unmount();

    const again = await renderView(serverWith(DOP_AND_USD), { scopeKey: "two-currencies" });
    assert.match(again.text("month-close-income"), /US\$ 1,200\.00/, "the choice is kept for this Business");
    await again.unmount();
    const other = await renderView(serverWith(DOP_AND_USD), { scopeKey: "another-business" });
    assert.match(other.text("month-close-income"), /RD\$ 4,000\.00/, "another Business keeps its own default");
    await other.unmount();
  });

  test("the Business currency is the default when the month holds it", async () => {
    const view = await renderView(serverWith(DOP_AND_USD), { scopeKey: "us-business", businessCurrency: "USD" });
    assert.match(view.text("month-close-income"), /US\$ 1,200\.00/);
    await view.act(async () => (view.host.querySelector('[data-testid="month-close-currency"]') as HTMLButtonElement).click());
    const options = [...document.querySelectorAll('[data-testid="month-close-currency-picker"] [role="option"]')];
    assert.deepEqual(options.map((option) => option.getAttribute("data-currency")), ["USD", "DOP"], "the Business currency leads the list");
    assert.match(options[0]?.textContent ?? "", /Moneda del negocio/);
    await view.unmount();
  });

  test("a pending USD document holds back only the USD net, and the waiting line names its currency", async () => {
    const view = await renderView(serverWith([DOP_AND_USD[0], block("USD", 120000, 2400, 21600, 1)], { cobrar: [line("usd-pending", "invoice", "USD", 5000)] }), { scopeKey: "pending-usd" });
    const net = view.host.querySelector('[data-testid="month-close-net"]');
    assert.equal(net?.getAttribute("data-state"), "final");
    assert.match(net?.textContent ?? "", /RD\$ 2,500\.00/);
    await view.act(async () => (view.host.querySelector('[data-testid="month-close-currency"]') as HTMLButtonElement).click());
    await view.act(async () => (document.querySelector('[data-testid="month-close-currency-picker"] [data-currency="USD"]') as HTMLElement).click());
    assert.equal(view.host.querySelector('[data-testid="month-close-net"]')?.getAttribute("data-state"), "pending");
    assert.match(view.text("month-close-net"), /Falta marcar 1 documento en US\$/);
    await view.unmount();
  });

  test("zero and three decimal currencies show exactly", async () => {
    const view = await renderView(serverWith([block("BHD", 12345678, 1050, 50), block("JPY", 1500, 25, 0)]), { scopeKey: "odd-digits", businessCurrency: "JPY" });
    assert.match(view.text("month-close-income"), /¥ 1,500(?![.\d])/);
    assert.match(view.text("month-close-expenses"), /¥ 25(?![.\d])/);
    await view.act(async () => (view.host.querySelector('[data-testid="month-close-currency"]') as HTMLButtonElement).click());
    await view.act(async () => (document.querySelector('[data-testid="month-close-currency-picker"] [data-currency="BHD"]') as HTMLElement).click());
    assert.match(view.text("month-close-expenses"), /BHD 1\.050(?!\d)/);
    assert.equal(view.host.querySelector('[data-testid="month-close-income"] [data-exact]')?.getAttribute("data-exact"), "BHD 12,345.678");
    await view.unmount();
  });

  test("a row with no currency shows an unknown amount, never pesos", async () => {
    const view = await renderView(serverWith([block("DOP", 100000, 0, 0)], { cobrar: [line("bare", "invoice", undefined, 5000), line("pesos", "invoice", "DOP", 9000)] }), { scopeKey: "bare-row" });
    const amount = view.host.querySelector('[data-testid="month-close-receivable"] [data-document-id="bare"] .cuadrao-amount')?.textContent;
    assert.equal(amount, "-");
    assert.equal(view.host.querySelector('[data-testid="month-close-receivable"] [data-document-id="pesos"] .cuadrao-amount')?.textContent, "90.00");
    await view.unmount();
  });
});

describe("a document with no counterparty", () => {
  for (const [language, invoice, expense] of [["es-419", "Factura", "Gasto"], ["en", "Invoice", "Expense"]] as const) {
    test(`is named by its kind from the catalog in ${language}`, async () => {
      const view = await renderView(serverWith([block("DOP", 100000, 0, 0)], {
        cobrar: [line("sale", "invoice", "DOP", 5000, { counterparty: null })],
        pagar: [line("cost", "receipt", "DOP", 3000, { counterparty: null })],
      }), { scopeKey: `nameless-${language}`, language });
      assert.match(view.host.querySelector('[data-document-id="sale"]')?.textContent ?? "", new RegExp(invoice));
      assert.match(view.host.querySelector('[data-document-id="cost"]')?.textContent ?? "", new RegExp(expense));
      assert.match(view.host.querySelector('[data-document-id="sale"] [data-testid="month-close-mark-cobrado"]')?.getAttribute("aria-label") ?? "", new RegExp(invoice));
      await view.unmount();
    });
  }
});
