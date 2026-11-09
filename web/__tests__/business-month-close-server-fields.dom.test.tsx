import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, type MonthCloseClient, type MonthCloseFigures, type MonthCloseSnapshot } from "../lib/business-month-close";
import type { BusinessContextValue } from "../components/business-app/BusinessWorkspace";
import english from "../public/locales/en/common.json";
import spanish from "../public/locales/es-419/common.json";
import { READ_VALUES, receiptLine } from "./fixtures/review-flags";

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

describe("Inicio waits for the server receipt count before closing", () => {
  test("Para cerrar carries no Bandeja count: only receipts still being read, which keep the month from a false ready state", async () => {
    const { client } = serverClient({});
    const view = await renderInicio(client, { count: 0, reading: 1 });
    try {
      assert.match(view.text("month-close-task-reading"), /1/);
      assert.equal(view.find("month-close-checklist-ready"), null);
      assert.equal(view.find("month-close-checklist-unknown"), null);
      assert.equal(view.find("month-close-close"), null);
      await view.setReview({ count: 4, reading: 1 });
      assert.equal(view.find("month-close-task-review"), null, "Necesita atención owns the Bandeja count");
      assert.equal(view.find("month-close-task-attention"), null);
      assert.match(view.text("month-close-task-reading"), /1/);
      assert.equal(view.find("month-close-checklist-footer"), null, "no empty footer divider remains without a status or action");
      assert.equal(view.find("month-close-nothing-open")?.querySelector("button"), null);
    } finally { await view.unmount(); }
  });
  for (const review of [null, undefined]) {
    test(`${review === null ? "failed or loading" : "missing"} receipt counts cannot claim ready or offer close`, async () => {
      const { client } = serverClient({});
      const view = await renderInicio(client, review);
      try {
        assert.ok(view.find("month-close-checklist"), "the month loaded successfully");
        assert.equal(Boolean(view.find("month-close-checklist-ready")), false, "unknown receipts are not zero receipts");
        assert.equal(Boolean(view.find("month-close-close")), false, "closing waits for the receipt count");
        assert.equal(view.text("month-close-checklist-unknown"), "-");
        assert.match(view.text("month-close-income"), /RD\$/, "the month's known figures still show");
      } finally { await view.unmount(); }
    });
  }

  test("a server-known zero keeps the all-settled message and still offers no close", async () => {
    const { client } = serverClient({});
    const view = await renderInicio(client, { count: 0 });
    try {
      assert.equal(view.text("month-close-checklist-ready").trim(), "Todo al día");
      assert.equal(view.find("month-close-close"), null, "there is no close action");
      assert.equal(view.find("month-close-task-review"), null);
    } finally { await view.unmount(); }
  });

  test("a positive Bandeja count adds no row: items waiting from other months do not hold this one", async () => {
    const { client } = serverClient({});
    const view = await renderInicio(client, { count: 2 });
    try {
      assert.equal(view.find("month-close-task-review"), null);
      assert.equal(view.text("month-close-checklist-ready").trim(), "Todo al día");
      assert.doesNotMatch(view.text("month-close-checklist"), /2/);
    } finally { await view.unmount(); }
  });
});

describe("receipt count recovery stays beside the hidden close action", () => {
  for (const [state, copy] of [
    ["loading", "Cargando el conteo de recibos. Aún no se puede cerrar el mes."],
    ["unknown", "El conteo de recibos no está disponible. Aún no se puede cerrar el mes."],
    ["failed", "No pudimos cargar el conteo de recibos. Aún no se puede cerrar el mes."],
    ["refused", "Cuadrao Business aún no está disponible para tu cuenta."],
  ] as const) {
    test(`${state} has its own reason, with retry only for a failed read`, async () => {
      let retries = 0;
      const { client } = serverClient({});
      const view = await renderInicio(client, state === "failed" ? { state, retry: () => { retries += 1; } } : { state });
      try {
        assert.match(view.text("month-close-receipts-status"), new RegExp(copy));
        assert.equal(view.text("month-close-checklist-unknown"), "-");
        assert.equal(Boolean(view.find("month-close-close")), false);
        const retry = view.find("month-close-receipts-status")?.querySelector("button");
        assert.equal(Boolean(retry), state === "failed");
        if (retry) {
          await view.act(async () => retry.click());
          assert.equal(retries, 1);
        }
      } finally { await view.unmount(); }
    });
  }

  test("a failed count keeps its reason and retry beside other checklist tasks", async () => {
    const { client } = serverClient({ month: () => ({ cuentas_por_cobrar: [line("pending", null)] }) });
    const view = await renderInicio(client, { state: "failed", retry: () => {} });
    try {
      assert.ok(view.find("month-close-task-settle"));
      assert.equal(Boolean(view.find("month-close-steps-note")), false, "unknown counts cannot promise closure after only the known steps");
      assert.match(view.text("month-close-receipts-status"), /No pudimos cargar el conteo de recibos/);
      assert.equal(view.find("month-close-checklist")?.contains(view.find("month-close-receipts-status")!), true);
    } finally { await view.unmount(); }
  });

  for (const branch of ["empty", "error"] as const) {
    test(`the ${branch} month branch keeps receipt-count recovery`, async () => {
      const { client } = serverClient({ month: () => ({ currencies: [] }) });
      const view = await renderInicio(branch === "error" ? { ...client, load: async () => { throw new Error("month read failed"); } } : client, { state: "failed", retry: () => {} });
      try {
        assert.ok(view.find(`month-close-${branch}`));
        assert.match(view.text("month-close-receipts-status"), /No pudimos cargar el conteo de recibos/);
        assert.equal(view.find("month-close-receipts-status")?.querySelector("button")?.textContent, "Reintentar");
      } finally { await view.unmount(); }
    });
  }
});

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
      closed_at: null,
      today: null,
      earliest_month: null,
      payment_methods: METHODS,
      dgii_forms: null,
      documents: [],
      blockers: [],
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
      async closeMonth() { return snapshot; },
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

  for (const layout of ["inicio", "finance"] as const) {
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

describe("the close card names a pending rate only when the month has one", () => {
  const readyReview = { count: 0 };

  function paid(currency: string, final: boolean): MonthCloseFigures {
    return {
      currency,
      income_before_itbis: "1200.00",
      expense_before_itbis: "240.00",
      net_before_itbis: "960.00",
      itbis_paid: "180.00",
      itbis_cobrado: "180.00",
      net_result_final: final,
      pending_count: 0,
    };
  }

  function octoberClient(figures: MonthCloseFigures[]): MonthCloseClient {
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      closed_at: null,
      today: "2026-10-18",
      earliest_month: "2026-10",
      payment_methods: METHODS,
      dgii_forms: null,
      documents: [],
      blockers: [],
      unreviewed_movements: 0,
      figures,
    };
    const none = { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] };
    return {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return { today: "2026-10-18", cuentas_por_cobrar: none, cuentas_por_pagar: none }; },
      async markCobrado() { throw new Error("unused"); },
      async markPagado() { throw new Error("unused"); },
      async markPendiente() { return undefined; },
      async closeMonth() { return snapshot; },
    };
  }

  const cases = [
    ["es-419", "one code", [paid("USD", false)], "Todo al día", "Los montos en USD pendientes de tasa no se incluyen en el 606/607."],
    ["es-419", "two codes", [paid("USD", false), paid("EUR", false)], "Todo al día", "Los montos en EUR y USD pendientes de tasa no se incluyen en el 606/607."],
    ["es-419", "no code", [paid("usd", false)], "Todo al día", "Los montos en moneda extranjera pendientes de tasa no se incluyen en el 606/607."],
    ["es-419", "no pending rate", [paid("DOP", true)], "Todo al día", null],
    ["en", "one code", [paid("USD", false)], "All settled", "Amounts in USD pending a rate are not included in the 606/607."],
    ["en", "two codes", [paid("USD", false), paid("EUR", false)], "All settled", "Amounts in EUR and USD pending a rate are not included in the 606/607."],
    ["en", "no code", [paid("usd", false)], "All settled", "Foreign-currency amounts pending a rate are not included in the 606/607."],
    ["en", "no pending rate", [paid("DOP", true)], "All settled", null],
  ] as const;

  for (const [language, name, figures, ready, rate] of cases) {
    test(`${language} close card, ${name}`, async () => {
      const view = await renderInicio(octoberClient([...figures]), readyReview, "inicio", language);
      try {
        assert.equal(view.text("month-close-checklist-ready").replace(/\s+/g, " ").trim(), ready);
        assert.equal(view.text("month-close-checklist-rate"), rate ?? "");
        if (rate === null) assert.equal(view.find("month-close-checklist-rate"), null);
      } finally {
        await view.unmount();
      }
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

describe("Exportar shows each form's own status from the packet", () => {
  const own = { space_id: "own-space", grant_id: "own-grant", name: "Taller Luna", role: "owner" as const, capabilities: ["read", "prepare", "approve"] as const, permissions: ["read", "prepare", "approve", "download", "export"] as const, access_seen: true };
  const original = { fetch: globalThis.fetch, auth: process.env.NEXT_PUBLIC_MOCK_AUTH };
  // Far from any real clock, so only the server's day can put these months on the control.
  const FAR_TODAY = "2031-03-15";
  const FORMS: Record<string, Record<string, string>> = {
    "2031-03": { "606": "needs_review", "607": "needs_review" },
    "2031-02": { "606": "prepared_candidate", "607": "no_operations" },
  };

  beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; });
  afterAll(() => {
    globalThis.fetch = original.fetch;
    if (original.auth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = original.auth;
  });

  async function renderExport(forms: (month: string) => unknown) {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("../public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("../components/business-app/BusinessWorkspace");
    const { setChosenGrant } = await import("../lib/business-grant");
    const ExportRecordsPanel = (await import("../components/business-app/ExportRecordsPanel")).default;
    const { useMonthCloseSource } = await import("../components/business-app/BusinessMonthClosePanel");
    function Panel() {
      return <ExportRecordsPanel monthClose={useMonthCloseSource()} onClose={() => undefined} />;
    }
    setChosenGrant(null);
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    globalThis.fetch = async (input) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname.endsWith("/business/fiscal-profile")) return Response.json({ name: "Taller Luna", tax_id: null, can_edit: false });
      const month = url.searchParams.get("month")!;
      const shape = forms(month);
      return Response.json({ month, today: FAR_TODAY, from: `${month}-01`, to: lastDay(month), closed: true, reasons: [], earliest_month: "2030-01", payment_methods: METHODS, ...(shape === undefined ? {} : { dgii_forms: shape }), currencies: [], missing_rnc: [], missing_ncf: [], missing_fiscal_rows: [], cuentas_por_cobrar: [], cuentas_por_pagar: [] });
    };
    const value = { source: { mode: "live" }, chosen: own } as unknown as BusinessContextValue;
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><Panel /></BusinessContext.Provider></I18nextProvider>);
    });
    const settle = async () => { for (let i = 0; i < 30; i += 1) await act(async () => { await Promise.resolve(); }); };
    await settle();
    const segment = (key: string) => document.querySelector<HTMLButtonElement>(`[data-testid="export-period"] [data-segment="${key}"]`);
    const form = (code: string) => document.querySelector<HTMLElement>(`[data-testid="export-form-${code}"]`);
    const fiscal = () => document.querySelector('[data-testid="export-fiscal"]')?.textContent ?? "";
    const unmount = async () => { await act(async () => root.unmount()); host.remove(); };
    return { act, segment, form, fiscal, settle, unmount };
  }

  test("the periods are the server's months, and a closed month still says what the packet says per form", async () => {
    const view = await renderExport((month) => FORMS[month]);
    try {
      assert.equal(view.segment("this_month")?.textContent, "Marzo");
      assert.equal(view.segment("last_month")?.textContent, "Febrero");
      assert.equal(view.segment("year")?.textContent, "2031");
      assert.equal(view.form("606")?.dataset.status, "needs_review");
      assert.equal(view.form("607")?.dataset.status, "needs_review");
      assert.doesNotMatch(view.fiscal(), /Incluido/, "closed is not the packet's word");
      assert.match(view.fiscal(), /606\s*Por revisar/);
      await view.act(async () => { view.segment("last_month")!.click(); });
      await view.settle();
      assert.equal(view.form("606")?.dataset.status, "prepared_candidate");
      assert.match(view.fiscal(), /606\s*Incluido/);
      assert.match(view.fiscal(), /607\s*Sin operaciones/);
    } finally {
      await view.unmount();
    }
  });

  test("an older server without dgii_forms shows the forms as unknown", async () => {
    const view = await renderExport(() => undefined);
    try {
      assert.equal(view.form("606"), null);
      assert.match(view.fiscal(), /606 y 607.*-$/);
      assert.doesNotMatch(view.fiscal(), /Incluido|Falta cerrar/);
    } finally {
      await view.unmount();
    }
  });
});

describe("Faltan datos fiscales rows are the server's, each opening exactly what it counts", () => {
  const purchase = (id: string, currency = "DOP") => ({ ...receiptLine(id, `Proveedor ${id}`, null, SERVER_TODAY), currency, missing: ["expense_type_missing"] });
  for (const language of ["es-419", "en"] as const) {
    test(`${language}: one row per tab in its one currency, and Ver opens Registros on that tab, currency and month`, async () => {
      const copy = (language === "en" ? english : spanish).business.month_close.placeholder;
      const held = [purchase("p1"), purchase("p2")];
      const rows = [{ family: "purchase", currency: "DOP", count: 2, by_currency: false }, { family: "sale", currency: "DOP", count: 1, by_currency: false }];
      const { client } = serverClient({ month: () => ({ missing_fiscal_data: held, missing_fiscal_rows: rows }) });
      const view = await renderInicio(client, { count: 0 }, "finance", language);
      try {
        assert.equal(view.find("month-close-task-fiscal-purchase-DOP")?.querySelector("p")?.textContent, copy.checklist_fiscal_purchases_other.replace("{{count}}", "2"));
        assert.equal(view.find("month-close-task-fiscal-sale-DOP")?.querySelector("p")?.textContent, copy.checklist_fiscal_sales_one);
        assert.equal(view.host.querySelector('[aria-controls="month-close-blockers"]'), null, "no Ver cuáles");
        await view.act(async () => view.find("month-close-task-fiscal-purchase-DOP")!.querySelector("button")!.click());
        assert.deepEqual(view.opened, [{ family: "purchase", currency: "DOP", from: "2026-11-01", to: "2026-11-30", fiscal_data: "missing" }]);
        assert.equal(view.find("month-close-filing"), null, "a held document is never ready for the 606");
      } finally { await view.unmount(); }
    });
  }

  test("a row in a currency Registros cannot list keeps its count and offers no action, never a different list", async () => {
    const rows = [{ family: "purchase", currency: "CAD", count: 1, by_currency: true }, { family: "purchase", currency: "DOP", count: 1, by_currency: true }];
    const { client } = serverClient({ month: () => ({ missing_fiscal_data: [purchase("c1", "CAD"), purchase("p1")], missing_fiscal_rows: rows }) });
    const view = await renderInicio(client, { count: 0 }, "finance");
    try {
      assert.match(view.text("month-close-task-fiscal-purchase-CAD"), /1 compra/);
      assert.equal(view.find("month-close-task-fiscal-purchase-CAD")?.querySelector("button"), null);
      assert.ok(view.find("month-close-task-fiscal-purchase-DOP")?.querySelector("button"));
    } finally { await view.unmount(); }
  });

  test("a read-only person sees the same rows and counts without actions", async () => {
    const rows = [{ family: "purchase", currency: "DOP", count: 2, by_currency: false }];
    const { client } = serverClient({ month: () => ({ missing_fiscal_data: [purchase("p1"), purchase("p2")], missing_fiscal_rows: rows, reasons: [{ code: "movimientos_sin_revisar", count: 3 }], unreviewed_movements_count: 3 }) });
    const view = await renderInicio(client, { count: 3 }, "finance", "es-419", false);
    try {
      assert.equal(view.find("month-close-task-fiscal-purchase-DOP")?.querySelector("p")?.textContent, "Faltan datos fiscales en 2 compras");
      assert.ok(view.find("month-close-task-bandeja"));
      assert.equal(view.find("month-close-checklist")?.querySelectorAll("button").length, 0, "no action for someone who may not prepare");
    } finally { await view.unmount(); }
  });

  test("a tab whose held documents span two currencies splits into a row per currency, each naming its own", async () => {
    const rows = [{ family: "purchase", currency: "DOP", count: 1, by_currency: true }, { family: "purchase", currency: "USD", count: 2, by_currency: true }];
    const { client } = serverClient({ month: () => ({ missing_fiscal_data: [purchase("p1"), purchase("u1", "USD"), purchase("u2", "USD")], missing_fiscal_rows: rows }) });
    const view = await renderInicio(client, { count: 0 }, "finance");
    try {
      assert.equal(view.find("month-close-task-fiscal-purchase-DOP")?.querySelector("p")?.textContent, "Faltan datos fiscales en 1 compra en RD$");
      assert.equal(view.find("month-close-task-fiscal-purchase-USD")?.querySelector("p")?.textContent, "Faltan datos fiscales en 2 compras en US$");
      await view.act(async () => view.find("month-close-task-fiscal-purchase-USD")!.querySelector("button")!.click());
      assert.deepEqual(view.opened, [{ family: "purchase", currency: "USD", from: "2026-11-01", to: "2026-11-30", fiscal_data: "missing" }]);
      assert.equal(view.text("month-close-checklist-left"), "faltan 2");
    } finally { await view.unmount(); }
  });
});

describe("ready for the 606 and 607 follows the export verdict, not month completion", () => {
  const reviewed = { count: 0 };
  /** Approved and paid, with its RNC and B01 NCF: month completion is satisfied, the 606 still holds it. */
  const paidPurchase = { activity_id: "rcpt-held", document_kind: "receipt", currency: "DOP", occurred_on: "2026-10-03", total_minor: 118000, itbis_minor: 18000, status: "pagado", counterparty: "Ferretería Prueba", due_on: null, rnc: "199990021", ncf: "B0100000021", ecf: null, sin_comprobante: false, payment_form: null };

  test("a complete month the 606 still holds names what the export is missing and claims nothing", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: { "606": "needs_review", "607": "no_operations" }, missing_fiscal_data: [{ ...paidPurchase, missing: ["expense_type_missing", "payment_method_missing"] }], missing_fiscal_rows: [{ family: "purchase", currency: "DOP", count: 1, by_currency: false }] }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.equal(view.find("month-close-filing"), null, "month completion does not say the 606 is ready");
      assert.equal(view.find("month-close-checklist-ready"), null);
      assert.equal(view.text("month-close-task-fiscal-purchase-DOP"), "Faltan datos fiscales en 1 compraVer");
      assert.equal(view.find("month-close-close"), null, "there is no close action");
      assert.equal(view.find("month-close-steps-note"), null, "no promise that the steps close the month");
    } finally { await view.unmount(); }
  });

  test("the export's own verdict says the 606 and 607 are ready, with no close action", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: { "606": "prepared_candidate", "607": "no_operations" }, missing_fiscal_data: [], filing_ready: true }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.equal(view.text("month-close-filing").trim(), "Ya tienes todo para el 606 y el 607.");
      assert.equal(view.find("month-close-close"), null);
      assert.equal(view.host.querySelector('[data-testid^="month-close-task-fiscal"]'), null);
      assert.doesNotMatch(view.host.textContent ?? "", /Cierra el mes|podrás cerrar|Todo listo para cerrar/);
    } finally { await view.unmount(); }
  });

  test("a month the export holds for a reason no document carries claims nothing and lists nothing", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: { "606": "needs_review", "607": "needs_review" }, missing_fiscal_data: [] }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.equal(view.find("month-close-filing"), null);
      assert.equal(view.host.querySelector('[data-testid^="month-close-task-fiscal"]'), null);
      assert.equal(view.text("month-close-checklist-ready").trim(), "Todo al día");
    } finally { await view.unmount(); }
  });

  test("an older server that sends no fiscal rows leaves the card unknown, never all settled", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: { "606": "needs_review", "607": "no_operations" }, missing_fiscal_data: [{ ...paidPurchase, missing: ["expense_type_missing"] }], missing_fiscal_rows: undefined }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.equal(view.find("month-close-checklist-ready"), null);
      assert.equal(view.find("month-close-filing"), null);
      assert.equal(view.text("month-close-checklist-unknown"), "-");
    } finally { await view.unmount(); }
  });

  test("an older server without the verdict claims nothing", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: undefined }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.equal(view.find("month-close-filing"), null);
      assert.equal(view.find("month-close-close"), null);
    } finally { await view.unmount(); }
  });
});

describe("the ready line is the server's one fact, and never shows while a step remains", () => {
  const reviewed = { count: 0 };
  const prepared = { "606": "prepared_candidate", "607": "no_operations" } as const;

  test("prepared forms alone do not make the month ready", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: prepared, missing_fiscal_data: [], filing_ready: false }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.equal(view.find("month-close-filing"), null);
      assert.equal(view.text("month-close-checklist-ready").trim(), "Todo al día");
    } finally { await view.unmount(); }
  });

  test("the server's ready fact shows the line once nothing remains", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: prepared, missing_fiscal_data: [], filing_ready: true }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.equal(view.text("month-close-filing").trim(), "Ya tienes todo para el 606 y el 607.");
      assert.equal(view.find("month-close-checklist-ready"), null);
    } finally { await view.unmount(); }
  });

  test("receipts still being read hide the line even when the server says ready", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: prepared, missing_fiscal_data: [], filing_ready: true }) });
    const view = await renderInicio(client, { count: 0, reading: 2 });
    try {
      assert.match(view.text("month-close-task-reading"), /2/);
      assert.equal(view.find("month-close-filing"), null, "a receipt still being read is not in the export yet");
      assert.equal(view.find("month-close-checklist-ready"), null);
    } finally { await view.unmount(); }
  });

  test("a document still to mark hides the line and shows the step", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: prepared, missing_fiscal_data: [], filing_ready: true, cuentas_por_cobrar: [line("pending", null)] }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.ok(view.find("month-close-task-settle"));
      assert.equal(view.find("month-close-filing"), null);
    } finally { await view.unmount(); }
  });

  test("an older server without the fact never shows the line", async () => {
    const { client } = serverClient({ month: () => ({ closed: true, dgii_forms: prepared, missing_fiscal_data: [] }) });
    const view = await renderInicio(client, reviewed);
    try {
      assert.equal(view.find("month-close-filing"), null);
    } finally { await view.unmount(); }
  });
});
