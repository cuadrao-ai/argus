import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, type MonthCloseClient, type MonthCloseFigures, type MonthCloseSnapshot } from "../lib/business-month-close";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

/** The browser's clock: one day behind the server's, across a month end. */
const browser = new Date(2026, 9, 31, 23, 30);
const SERVER_TODAY = "2026-11-01";
const METHODS = ["efectivo", "transferencia", "tarjeta", "credito", "otro"];

function lastDay(month: string): string {
  const [year, index] = month.split("-").map(Number);
  return `${month}-${String(new Date(Date.UTC(year, index, 0)).getUTCDate()).padStart(2, "0")}`;
}

function byStatus(pending: number) {
  return { invoices: { pendiente: { count: pending, before_itbis_minor: 0 }, cobrado: { count: 0, before_itbis_minor: 0 } }, receipts: { pendiente: { count: 0, before_itbis_minor: 0 }, pagado: { count: 0, before_itbis_minor: 0 } } };
}

function block(currency: string, final: boolean, pending = 0) {
  return { currency, income_before_itbis_minor: 400000, expense_before_itbis_minor: 150000, net_result_minor: 250000, itbis_charged_minor: 72000, itbis_paid_minor: 18000, itbis_cobrado_minor: 45000, by_status: byStatus(pending), net_result_final: final };
}

function line(id: string, dueOn: string | null, currency = "DOP") {
  return { activity_id: id, document_kind: "invoice", currency, occurred_on: "2026-10-05", total_minor: 590000, itbis_minor: null, status: "pendiente", counterparty: `Cliente ${id}`, due_on: dueOn };
}

type Server = {
  month?: (month: string) => Record<string, unknown>;
  open?: Record<string, unknown>;
  patches?: { path: string; body: unknown }[];
};

function serverClient(server: Server): { client: MonthCloseClient; asked: string[] } {
  const asked: string[] = [];
  const client = createHttpMonthCloseClient(async (path, init) => {
    if (init?.method === "PATCH") {
      const body = JSON.parse(String(init.body));
      server.patches?.push({ path, body });
      return { activity_id: path.split("/").at(-1), document_kind: "invoice", status: body.status, settled_on: body.settled_on ?? null, payment_method: body.payment_method ?? null, changed: true };
    }
    if (path === "/business/open-items") {
      return server.open ?? { today: SERVER_TODAY, cuentas_por_cobrar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] }, cuentas_por_pagar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] } };
    }
    const month = new URLSearchParams(path.split("?")[1]).get("month")!;
    asked.push(month);
    return {
      month,
      today: SERVER_TODAY,
      from: `${month}-01`,
      to: lastDay(month),
      closed: false,
      reasons: [],
      earliest_month: "2026-09",
      payment_methods: METHODS,
      dgii_forms: { "606": "needs_review", "607": "needs_review" },
      currencies: [block("DOP", true)],
      missing_rnc: [],
      missing_ncf: [],
      missing_fiscal_rows: [],
      cuentas_por_cobrar: [],
      cuentas_por_pagar: [],
      ...server.month?.(month),
    };
  });
  return { client, asked };
}

async function renderInicio(client: MonthCloseClient, review?: Parameters<typeof import("../components/business-app/BusinessMonthClosePanel").BusinessMonthCloseView>[0]["review"], layout: "inicio" | "finance" = "inicio", language: "es-419" | "en" = "es-419", prepares = true) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("../public/locales/es-419/common.json")).default;
  const english = (await import("../public/locales/en/common.json")).default;
  const { BusinessMonthCloseView } = await import("../components/business-app/BusinessMonthClosePanel");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const opened: unknown[] = [];
  const render = () => root.render(<I18nextProvider i18n={i18n}><BusinessMonthCloseView settlement client={client} now={browser} scopeKey="own" businessCurrency="DOP" review={review} layout={layout} openRecords={prepares ? (focus) => opened.push(focus) : undefined} openBandeja={prepares ? () => opened.push("bandeja") : undefined} /></I18nextProvider>);
  await act(async () => { render(); });
  const setReview = async (next: typeof review) => { review = next; await act(async () => { render(); }); };
  const settle = async () => { for (let i = 0; i < 20; i += 1) await act(async () => { await Promise.resolve(); }); };
  await settle();
  const find = (id: string) => host.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const text = (id: string) => find(id)?.textContent ?? "";
  const unmount = async () => { await act(async () => root.unmount()); host.remove(); };
  return { act, host, find, text, settle, setReview, unmount, opened };
}

describe("Inicio reads today from the server", () => {
  test("a browser clock one day behind opens the server's month and judges overdue by the server's day", async () => {
    const open = {
      today: SERVER_TODAY,
      cuentas_por_cobrar: {
        count: 130,
        totals: [{ currency: "DOP", total_minor: 76700000 }],
        overdue: { count: 7, totals: [{ currency: "DOP", total_minor: 1230000 }, { currency: "USD", total_minor: 5000 }] },
        items: [line("late", "2026-10-31"), line("soon", "2026-11-05")],
      },
      cuentas_por_pagar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] },
    };
    const { client, asked } = serverClient({ open });
    const view = await renderInicio(client);
    try {
      assert.equal(view.text("month-close-month"), "Noviembre 2026");
      assert.equal(asked.at(-1), "2026-11");
      assert.equal(view.find("month-close-month-next")?.hasAttribute("disabled"), true, "the server's month is the last one");
      const overdue = view.text("month-close-receivable-overdue");
      assert.match(overdue, /^7 vencidas/, "the count is the server's, not the two rows on the page");
      assert.match(overdue, /RD\$\s?12,300\.00/);
      assert.match(overdue, /US\$\s?50\.00/);
      const late = view.host.querySelector('[data-document-id="late"] [data-testid="month-close-lateness"]');
      assert.equal(late?.textContent, "1 día tarde", "due on the browser's today is already late on the server's");
    } finally {
      await view.unmount();
    }
  });

  test("a browser clock one day ahead stays on the server's month", async () => {
    const { client } = serverClient({ month: () => ({ today: "2026-10-31" }), open: { today: "2026-10-31", cuentas_por_cobrar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] }, cuentas_por_pagar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] } } });
    const { act } = await import("react");
    const ahead = new Date(2026, 10, 1, 0, 30);
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
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessMonthCloseView settlement client={client} now={ahead} scopeKey="own" /></I18nextProvider>); });
    for (let i = 0; i < 20; i += 1) await act(async () => { await Promise.resolve(); });
    try {
      assert.equal(host.querySelector('[data-testid="month-close-month"]')?.textContent, "Octubre 2026");
      assert.equal(host.querySelector('[data-testid="month-close-month-next"]')?.hasAttribute("disabled"), true);
    } finally {
      await act(async () => root.unmount());
      host.remove();
    }
  });

  test("earliest_month is the first month the picker offers", async () => {
    const { client } = serverClient({});
    const view = await renderInicio(client);
    try {
      await view.act(async () => { view.find("month-close-month")!.click(); });
      const months = [...document.querySelectorAll<HTMLElement>('[data-testid="month-close-month-picker"] [role="option"]')];
      assert.equal(months[0]?.dataset.month, "2026-09");
      assert.deepEqual(months.filter((option) => option.getAttribute("aria-disabled") !== "true").map((option) => option.dataset.month), ["2026-09", "2026-10", "2026-11"]);
    } finally {
      await view.unmount();
    }
  });
});

describe("the net result follows net_result_final", () => {
  test("false shows the waiting line with the server's count, even when the web holds no pending row", async () => {
    const { client } = serverClient({ month: () => ({ currencies: [block("DOP", false, 3)] }) });
    const view = await renderInicio(client);
    try {
      assert.equal(view.find("month-close-net")?.dataset.state, "pending");
      assert.match(view.text("month-close-net"), /Falta marcar 3 documentos/);
      assert.doesNotMatch(view.text("month-close-net"), /2,500/);
    } finally {
      await view.unmount();
    }
  });

  test("true shows the figure, even with a pending row in the month's lists", async () => {
    const { client } = serverClient({ month: () => ({ currencies: [block("DOP", true)], cuentas_por_cobrar: [line("still", null)] }) });
    const view = await renderInicio(client);
    try {
      assert.equal(view.find("month-close-net")?.dataset.state, "final");
      assert.match(view.text("month-close-net"), /RD\$\s?2,500(?![.\d])/);
    } finally {
      await view.unmount();
    }
  });

  test("ITBIS cobrado sits under ITBIS en ventas, from the block", async () => {
    const { client } = serverClient({});
    const view = await renderInicio(client);
    try {
      assert.match(view.text("month-close-itbis-sales"), /ITBIS cobrado/);
      assert.match(view.text("month-close-itbis-sales"), /RD\$\s?450(?![.\d])/);
    } finally {
      await view.unmount();
    }
  });
});

describe("a non-final block with no documents left names the pending rate", () => {
  const aside = "Estos montos no están incluidos en el resultado.";

  function rateClient(currencies: string[]) {
    return serverClient({ month: () => ({ currencies: currencies.map((currency) => block(currency, false, 0)) }) }).client;
  }

  function unreadableClient(): MonthCloseClient {
    const figure: MonthCloseFigures = {
      currency: "usd",
      income_before_itbis: null,
      expense_before_itbis: null,
      net_before_itbis: null,
      itbis_paid: null,
      itbis_cobrado: null,
      net_result_final: false,
      pending_count: 0,
    };
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      today: null,
      earliest_month: null,
      payment_methods: METHODS,
      dgii_forms: null,
      documents: [],
      unreviewed_movements: 0,
      figures: [figure],
    };
    const none = { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] };
    return {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return { today: null, cuentas_por_cobrar: none, cuentas_por_pagar: none }; },
      async markCobrado() { throw new Error("unused"); },
      async markPagado() { throw new Error("unused"); },
      async markPendiente() { return undefined; },
    };
  }

  async function expectRate(client: MonthCloseClient, headline: string, layout: "inicio" | "finance", plain = false) {
    const view = await renderInicio(client, undefined, layout);
    try {
      const net = view.text("month-close-net");
      assert.equal(view.find("month-close-net")?.dataset.state, "pending");
      assert.ok(net.includes(headline), net);
      assert.ok(net.includes(aside), net);
      assert.equal(net.includes("pendiente de tasa en"), !plain, net);
      assert.doesNotMatch(net, /Falta marcar/);
      assert.doesNotMatch(net, /2,500/);
    } finally {
      await view.unmount();
    }
  }

  // Inicio's month card shows no caption under the net: its own tests cover a pending rate.
  for (const layout of ["inicio"] as const) {
    test(`${layout} shows one currency`, async () => {
      await expectRate(rateClient(["USD"]), "Moneda extranjera: pendiente de tasa en USD", layout);
    });

    test(`${layout} shows two currencies in alphabetical order`, async () => {
      await expectRate(rateClient(["USD", "EUR"]), "Moneda extranjera: pendiente de tasa en EUR y USD", layout);
    });

    test(`${layout} shows three currencies with a final y`, async () => {
      await expectRate(rateClient(["USD", "DOP", "EUR"]), "Moneda extranjera: pendiente de tasa en DOP, EUR y USD", layout);
    });

    test(`${layout} drops an unreadable code`, async () => {
      await expectRate(unreadableClient(), "Moneda extranjera: pendiente de tasa", layout, true);
    });
  }
});

describe("a mark sends the server's day and a method the server lists", () => {
  const open = (items: unknown[]) => ({ today: SERVER_TODAY, cuentas_por_cobrar: { count: items.length, totals: [{ currency: "DOP", total_minor: 590000 }], overdue: { count: 0, totals: [] }, items }, cuentas_por_pagar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] } });

  test("the PATCH carries the server's today, not the browser's, and the listed method", async () => {
    const patches: { path: string; body: unknown }[] = [];
    const { client } = serverClient({ open: open([line("act-1", "2026-11-05")]), patches });
    const view = await renderInicio(client);
    try {
      await view.act(async () => { view.find("month-close-mark-cobrado")!.click(); });
      await view.settle();
      assert.deepEqual(patches, [{ path: "/business/month-close/documents/act-1", body: { status: "cobrado", settled_on: SERVER_TODAY, payment_method: "otro" } }]);
    } finally {
      await view.unmount();
    }
  });

  test("a server whose list has no method for a one-tap mark offers no mark", async () => {
    const { client } = serverClient({ month: () => ({ payment_methods: ["efectivo", "transferencia"] }), open: open([line("act-1", null)]) });
    const view = await renderInicio(client);
    try {
      assert.ok(view.host.querySelector('[data-document-id="act-1"]'));
      assert.equal(view.find("month-close-mark-cobrado"), null);
    } finally {
      await view.unmount();
    }
  });
});
