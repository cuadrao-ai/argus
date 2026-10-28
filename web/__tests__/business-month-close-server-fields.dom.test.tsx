import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, type MonthCloseClient } from "../lib/business-month-close";
import type { BusinessContextValue } from "../components/business-app/BusinessWorkspace";

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
  return { currency, income_before_itbis_minor: 400000, expense_before_itbis_minor: 150000, net_result_minor: 250000, itbis_owed_minor: 18000, itbis_cobrado_minor: 45000, by_status: byStatus(pending), net_result_final: final };
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
      cuentas_por_cobrar: [],
      cuentas_por_pagar: [],
      ...server.month?.(month),
    };
  });
  return { client, asked };
}

async function renderInicio(client: MonthCloseClient, review?: Parameters<typeof import("../components/business-app/BusinessMonthClosePanel").BusinessMonthCloseView>[0]["review"]) {
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
  const render = () => root.render(<I18nextProvider i18n={i18n}><BusinessMonthCloseView client={client} now={browser} scopeKey="own" businessCurrency="DOP" review={review} /></I18nextProvider>);
  await act(async () => { render(); });
  const setReview = async (next: typeof review) => { review = next; await act(async () => { render(); }); };
  const settle = async () => { for (let i = 0; i < 20; i += 1) await act(async () => { await Promise.resolve(); }); };
  await settle();
  const find = (id: string) => host.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const text = (id: string) => find(id)?.textContent ?? "";
  const unmount = async () => { await act(async () => root.unmount()); host.remove(); };
  return { act, host, find, text, settle, setReview, unmount };
}

describe("Inicio waits for the server receipt count before closing", () => {
  test("known reading and attention groups stay separate and prevent a false ready state", async () => {
    const { client } = serverClient({});
    const view = await renderInicio(client, { count: 0, detail: null, reading: 1, attention: 0, open() {} });
    try {
      assert.ok(view.find("month-close-reading"));
      assert.equal(view.find("month-close-checklist-ready"), null);
      assert.equal(view.find("month-close-checklist-unknown"), null);
      assert.equal(view.find("month-close-close"), null);
      await view.setReview({ count: 4, detail: null, reading: 1, attention: 5, open() {} });
      assert.match(view.text("month-close-task-review"), /4/);
      assert.match(view.text("month-close-task-attention"), /5/);
      assert.match(view.text("month-close-reading"), /1/);
      assert.equal(view.find("month-close-steps-note"), null, "finishing tasks cannot promise closure while reading still blocks it");
      assert.equal(view.find("month-close-checklist-footer"), null, "no empty footer divider remains without a status or action");
      assert.equal(view.find("month-close-close"), null);
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

  test("a server-known zero keeps the ready message and close action", async () => {
    const { client } = serverClient({});
    const view = await renderInicio(client, { count: 0, detail: null, open: () => {} });
    try {
      assert.match(view.text("month-close-checklist-ready"), /Todo listo para cerrar noviembre/);
      assert.ok(view.find("month-close-close"));
      assert.equal(view.find("month-close-task-review"), null);
    } finally { await view.unmount(); }
  });

  test("a receipt count lost after opening confirmation cannot close the month", async () => {
    let closes = 0;
    const { client } = serverClient({});
    const view = await renderInicio({ ...client, closeMonth: async (month) => { closes += 1; return client.load(month); } }, { count: 0, detail: null, open: () => {} });
    try {
      await view.act(async () => view.find("month-close-close")!.click());
      const dialog = document.querySelector('[role="alertdialog"]');
      assert.ok(dialog, "the known zero allows opening confirmation");
      await view.setReview(null);
      const confirm = [...dialog.querySelectorAll("button")].find((button) => button.textContent === "Sí, cerrar mes");
      assert.ok(confirm);
      await view.act(async () => confirm.click());
      assert.equal(closes, 0, "an open confirmation cannot bypass unknown receipts");
      assert.equal(Boolean(document.querySelector('[role="alertdialog"]')), false, "the stale confirmation returns to the unknown checklist");
    } finally { await view.unmount(); }
  });

  test("a positive server count keeps the review task and its action", async () => {
    let opened = false;
    const { client } = serverClient({});
    const view = await renderInicio(client, { count: 2, detail: null, open: () => { opened = true; } });
    try {
      assert.match(view.text("month-close-task-review"), /2 por revisar en la Bandeja/);
      assert.equal(view.find("month-close-checklist-ready"), null);
      assert.equal(view.find("month-close-close"), null);
      await view.act(async () => view.find("month-close-task-review")!.querySelector("button")!.click());
      assert.equal(opened, true);
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
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessMonthCloseView client={client} now={ahead} scopeKey="own" /></I18nextProvider>); });
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
      assert.match(view.text("month-close-net"), /RD\$\s?2,500\.00/);
    } finally {
      await view.unmount();
    }
  });

  test("ITBIS cobrado sits under the ITBIS card, from the block", async () => {
    const { client } = serverClient({});
    const view = await renderInicio(client);
    try {
      assert.match(view.text("month-close-itbis"), /ITBIS cobrado/);
      assert.match(view.text("month-close-itbis"), /RD\$\s?450\.00/);
    } finally {
      await view.unmount();
    }
  });
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
      return Response.json({ month, today: FAR_TODAY, from: `${month}-01`, to: lastDay(month), closed: true, reasons: [], earliest_month: "2030-01", payment_methods: METHODS, ...(shape === undefined ? {} : { dgii_forms: shape }), currencies: [], missing_rnc: [], missing_ncf: [], cuentas_por_cobrar: [], cuentas_por_pagar: [] });
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
