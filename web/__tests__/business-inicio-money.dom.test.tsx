import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createMockMonthCloseClient, MonthCloseError, monthCloseFiguresFrom, monthCloseFiscalRowsFrom, openItemsFrom, type MonthCloseClient, type MonthCloseDocument } from "../lib/business-month-close";
import type { BusinessContextValue } from "../components/business-app/BusinessWorkspace";

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

function openByStatus() {
  return {
    invoices: { pendiente: statusCell(1, 100000), cobrado: statusCell(0, 0) },
    receipts: { pendiente: statusCell(0, 0), pagado: statusCell(0, 0) },
  };
}


describe("Inicio month close source", () => {
  const liveWire = (month: string) => ({
    month,
    from: `${month}-01`,
    to: `${month}-28`,
    closed: false,
    reasons: [],
    currencies: [{ currency: "DOP", by_status: openByStatus() }],
    missing_rnc: [],
    missing_ncf: [],
    missing_fiscal_rows: [],
    cuentas_por_cobrar: [],
    cuentas_por_pagar: [],
  });

  async function renderPanel(mode: "live" | "fixture") {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("../public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("../components/business-app/BusinessWorkspace");
    const { default: MonthClosePanel, useMonthCloseSource } = await import("../components/business-app/BusinessMonthClosePanel");
    function Panel() {
      return <MonthClosePanel monthClose={useMonthCloseSource()} />;
    }
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const value = {
      source: { mode },
      chosen: { grant_id: "own-grant", capabilities: ["approve"], role: "owner", name: "Taller" },
      actions: { create: [] },
      records: { workspace: { settlement_available: true } },
    } as unknown as BusinessContextValue;
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <BusinessContext.Provider value={value}>
            <Panel />
          </BusinessContext.Provider>
        </I18nextProvider>,
      );
    });
    for (let i = 0; i < 20; i += 1) {
      await act(async () => { await Promise.resolve(); });
    }
    return { act, host, root };
  }

  test("the live client is what /biz loads, and a failure never shows sample numbers", async () => {
    const calls: { url: string; method: string }[] = [];
    const original = globalThis.fetch;
    const originalWindow = window.fetch;
    const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const spy = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      calls.push({ url, method: init?.method ?? "GET" });
      const month = new URL(url, "http://localhost").searchParams.get("month") ?? "";
      if (url.includes("/business/month-close?") && calls.filter((call) => call.url.includes("/business/month-close?")).length === 1) {
        return Response.json(liveWire(month));
      }
      return new Response(JSON.stringify({ code: "business_month_close_unavailable" }), { status: 503, headers: { "content-type": "application/json" } });
    };
    globalThis.fetch = spy;
    window.fetch = spy;
    try {
      const first = await renderPanel("live");
      const load = calls.find((call) => call.url.includes("/business/month-close?"));
      assert.equal(load?.method, "GET");
      assert.match(load?.url ?? "", /\/business\/month-close\?month=\d{4}-\d{2}$/);
      assert.equal(first.host.querySelector('[data-testid="month-close-sample"]'), null);
      assert.equal(first.host.textContent?.includes("Farmacia Central"), false);
      assert.match(first.host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /^Ingresos-/);
      assert.equal(first.host.querySelector('[data-testid="month-close-income"]')?.getAttribute("data-amount"), null);
      await first.act(async () => first.root.unmount());
      first.host.remove();

      calls.length = 0;
      const fail = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        calls.push({ url, method: init?.method ?? "GET" });
        return new Response(JSON.stringify({ code: "business_month_close_unavailable" }), { status: 503, headers: { "content-type": "application/json" } });
      };
      globalThis.fetch = fail;
      window.fetch = fail;
      const failed = await renderPanel("live");
      const error = failed.host.querySelector('[data-testid="month-close-error"]');
      const errorState = error?.querySelector('[data-empty-kind="error"]');
      assert.ok(errorState, "the failed month is an error empty state");
      assert.equal(errorState.getAttribute("role"), "alert");
      assert.equal(errorState.querySelector("h3")?.textContent, "No pudimos cargar el mes");
      assert.deepEqual([...errorState.querySelectorAll("button")].map((button) => button.textContent?.trim()), ["Reintentar"]);
      assert.equal(failed.host.textContent?.includes("Farmacia Central"), false);
      assert.equal(failed.host.querySelector('[data-testid="month-close-sample"]'), null);
      assert.equal(failed.host.querySelector('[data-testid="month-close-income"]'), null);
      await failed.act(async () => failed.root.unmount());
      failed.host.remove();
    } finally {
      globalThis.fetch = original;
      window.fetch = originalWindow;
      process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock;
    }
  });

  test("sample figures appear only for the preview source", async () => {
    const calls: string[] = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (input) => {
      calls.push(String(input));
      return new Response("{}", { status: 500 });
    };
    try {
      const page = await renderPanel("fixture");
      assert.match(page.host.textContent ?? "", /Farmacia Central/);
      assert.equal(calls.some((url) => url.includes("/business/month-close")), false);
      await page.act(async () => page.root.unmount());
      page.host.remove();
    } finally {
      globalThis.fetch = original;
    }
  });
});

describe("Pendiente hoy cards", () => {
  async function renderCards(client: MonthCloseClient, openDocument?: (document: MonthCloseDocument) => (() => void) | null) {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("../public/locales/es-419/common.json")).default;
    const { BusinessMonthCloseView } = await import("../components/business-app/BusinessMonthClosePanel");
    const { useToasts, clearToasts } = await import("../components/business-app/foundation/toasts");
    clearToasts();
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const toasts: { current: ReturnType<typeof useToasts> } = { current: [] };
    function Probe() {
      toasts.current = useToasts();
      return null;
    }
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <BusinessMonthCloseView settlement client={client} now={now} openDocument={openDocument} />
          <Probe />
        </I18nextProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
    });
    const card = (testId: string) => host.querySelector(`[data-testid="${testId}"]`);
    const rowIds = (testId: string) => [...(card(testId)?.querySelectorAll('[data-testid="month-close-row"]') ?? [])].map((row) => row.getAttribute("data-document-id"));
    const cleanup = async () => {
      await act(async () => root.unmount());
      host.remove();
      clearToasts();
    };
    return { act, host, card, rowIds, toasts, cleanup };
  }

  test("each card leads with its total in RD$, then a red line with what is overdue, summed exactly", async () => {
    const view = await renderCards(createMockMonthCloseClient({ now }));
    const receivable = view.card("month-close-receivable");
    assert.equal(receivable?.querySelector("h4")?.textContent, "Por cobrar");
    const total = receivable?.querySelector('[data-testid="month-close-receivable-total"]');
    assert.equal(total?.textContent, "RD$ 33,540.00");
    assert.match(total?.className ?? "", /cuadrao-amount/);
    assert.match(total?.className ?? "", /text-\[22px\].*tabular-nums/);
    const overdue = receivable?.querySelector('[data-testid="month-close-receivable-overdue"]');
    assert.equal(overdue?.textContent, "2 vencidas · RD$ 12,300.00");
    assert.equal(overdue?.querySelector(".cuadrao-amount")?.textContent, "RD$ 12,300.00", "Ocultar montos hides the overdue sum too");
    assert.equal(view.card("month-close-payable")?.querySelector('[data-testid="month-close-payable-overdue"]')?.textContent, "2 vencidas · RD$ 2,444.00");
    assert.equal(view.host.querySelector("#month-close-money-title")?.tagName, "H3");
    assert.equal(view.host.querySelector("#month-close-money-title")?.textContent, "Pendiente hoy");
    await view.cleanup();
  });

  test("overdue rows lead oldest first, then the nearest due, and a card shows four before Ver las N", async () => {
    const invoice = (id: string, due_on: string | null): MonthCloseDocument => ({ id, kind: "invoice", currency: "DOP", counterparty: `Cliente ${id}`, occurred_on: "2026-09-01", due_on, amount: "100.00", itbis: null, rnc: "101-23456-7", ncf: "B0100000042", ecf: null, status: "pendiente" });
    const documents = [invoice("soon", "2026-10-26"), invoice("none", null), invoice("late-1", "2026-10-17"), invoice("today", "2026-10-18"), invoice("late-30", "2026-09-18"), invoice("far", "2026-11-30")];
    const client: MonthCloseClient = { ...createMockMonthCloseClient({ now }), async openItems() { return openItemsFrom(documents, "2026-10-18"); } };
    const view = await renderCards(client);
    assert.deepEqual(view.rowIds("month-close-receivable"), ["late-30", "late-1", "today", "soon"]);
    const chip = (id: string) => view.host.querySelector(`[data-document-id="${id}"] [data-testid="month-close-lateness"]`)?.textContent;
    assert.equal(chip("late-30"), "30 días tarde");
    assert.equal(chip("late-1"), "1 día tarde");
    assert.equal(chip("today"), "vence hoy");
    assert.equal(chip("soon"), "vence en 8 días");
    const reveal = view.host.querySelector('[data-testid="month-close-receivable-reveal"]');
    assert.equal(reveal?.textContent, "Ver las 6");
    await view.act(async () => { (reveal as HTMLButtonElement).click(); });
    assert.deepEqual(view.rowIds("month-close-receivable"), ["late-30", "late-1", "today", "soon", "far", "none"]);
    assert.equal(view.host.querySelector('[data-document-id="none"] [data-testid="month-close-issued"]')?.getAttribute("datetime"), "2026-09-01", "no due day shows the issue day, never a made-up lateness");
    await view.cleanup();
  });

  test("the round check removes the row, Deshacer brings it back, and the totals follow the server", async () => {
    const view = await renderCards(createMockMonthCloseClient({ now }));
    const check = view.host.querySelector('[data-document-id="inv-luna"] [data-testid="month-close-mark-cobrado"]');
    assert.ok(check instanceof HTMLButtonElement);
    assert.equal(check.getAttribute("aria-label"), "Marcar cobrado, Panadería Luna");
    assert.match(check.className, /h-11 w-11/, "a 44px target");
    assert.equal(view.host.querySelectorAll('[data-testid="month-close-row"] button:not([aria-label])').length, 0, "no row repeats a Marcar text link");
    await view.act(async () => {
      check.click();
      await Promise.resolve();
    });
    assert.equal(view.rowIds("month-close-receivable").includes("inv-luna"), false);
    await view.act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    assert.equal(view.card("month-close-receivable")?.querySelector('[data-testid="month-close-receivable-total"]')?.textContent, "RD$ 27,640.00");
    const toast = view.toasts.current.at(-1);
    assert.equal(toast?.kind, "success");
    assert.equal(toast?.text, "Factura de Panadería Luna cobrada.");
    assert.equal(toast?.action?.label, "Deshacer");
    await view.act(async () => {
      toast?.action?.run();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    assert.equal(view.rowIds("month-close-receivable").includes("inv-luna"), true);
    assert.equal(view.card("month-close-receivable")?.querySelector('[data-testid="month-close-receivable-total"]')?.textContent, "RD$ 33,540.00");
    await view.cleanup();
  });

  test("marks in a row share one toast, its Deshacer brings them all back, and a finished card says so", async () => {
    const view = await renderCards(createMockMonthCloseClient({ now }));
    for (const id of view.rowIds("month-close-receivable")) {
      await view.act(async () => {
        (view.host.querySelector(`[data-document-id="${id}"] [data-testid="month-close-mark-cobrado"]`) as HTMLButtonElement).click();
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
    }
    const marked = view.toasts.current.filter((toast) => toast.kind === "success");
    assert.equal(marked.length, 1, "one toast, not a stack");
    assert.equal(marked[0]?.text, "3 facturas cobradas.");
    const done = view.host.querySelector('[data-testid="month-close-receivable-empty"]');
    assert.equal(done?.querySelector("[data-empty-kind]")?.getAttribute("data-empty-kind"), "done");
    assert.match(done?.textContent ?? "", /Todo cobrado/);
    await view.act(async () => {
      marked[0]?.action?.run();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    assert.equal(view.rowIds("month-close-receivable").length, 3, "Deshacer reopens every row the toast named");
    await view.cleanup();
  });

  test("a failed Deshacer says so and leaves the row marked", async () => {
    const client: MonthCloseClient = { ...createMockMonthCloseClient({ now }), async markPendiente() { throw new MonthCloseError("unavailable", "undo failed"); } };
    const view = await renderCards(client);
    await view.act(async () => {
      (view.host.querySelector('[data-document-id="rcpt-rosa"] [data-testid="month-close-mark-pagado"]') as HTMLButtonElement).click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    assert.equal(view.toasts.current.at(-1)?.text, "Gasto de Limpieza Rosa pagado.");
    await view.act(async () => {
      view.toasts.current.at(-1)?.action?.run();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    assert.equal(view.toasts.current.some((toast) => toast.kind === "error"), false, "toasts only confirm");
    assert.match(view.host.querySelector('[data-testid="month-close-work-problem"]')?.textContent ?? "", /No pudimos deshacer el cambio\. Inténtalo de nuevo\.Reintentar/);
    assert.equal(view.rowIds("month-close-payable").includes("rcpt-rosa"), false);
    await view.cleanup();
  });

  test("a row with a record opens it; a row without one is not a button", async () => {
    const opened: string[] = [];
    const view = await renderCards(createMockMonthCloseClient({ now }), (document) => (document.kind === "receipt" ? () => opened.push(document.id) : null));
    assert.equal(view.card("month-close-receivable")?.querySelector('[data-testid="month-close-row-open"]'), null);
    const open = view.host.querySelector('[data-document-id="rcpt-edenorte"] [data-testid="month-close-row-open"]');
    assert.ok(open instanceof HTMLButtonElement);
    await view.act(async () => { open.click(); });
    assert.deepEqual(opened, ["rcpt-edenorte"]);
    assert.equal(view.toasts.current.length, 0, "opening a row never marks it");
    await view.cleanup();
  });
});

describe("Inicio in two columns", () => {
  const document_ = (over: Partial<MonthCloseDocument>): MonthCloseDocument => ({ id: "inv-1", kind: "invoice", currency: "DOP", counterparty: "Colmado Don Luis", occurred_on: "2026-10-04", due_on: null, amount: "1180.00", itbis: "180.00", rnc: "101-23456-7", ncf: "B0100000042", ecf: null, status: "cobrado", ...over });
  const clientOf = (documents: MonthCloseDocument[]): MonthCloseClient => ({
    mode: "mock",
    async load() { return { month: "2026-10", today: "2026-10-18", from: "2026-10-01", to: "2026-10-31", unreviewed_movements: 0, earliest_month: null, payment_methods: ["otro"], dgii_forms: null, documents, figures: monthCloseFiguresFrom(documents), fiscal_rows: monthCloseFiscalRowsFrom(documents) }; },
    async openItems() { return openItemsFrom(documents, "2026-10-18"); },
    async markCobrado() { throw new Error("no mark"); },
    async markPagado() { throw new Error("no mark"); },
    async markPendiente() { throw new Error("no undo"); },
  });
  async function renderView(client: MonthCloseClient, review?: Parameters<typeof import("../components/business-app/BusinessMonthClosePanel").BusinessMonthCloseView>[0]["review"], headingAction = false) {
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
      root.render(<I18nextProvider i18n={i18n}><BusinessMonthCloseView settlement client={client} now={now} review={review} headingAction={headingAction ? <button data-testid="home-heading-add">Agregar</button> : undefined} header={(switcher) => <div data-testid="inicio-greeting-row"><h2>Hola</h2>{switcher}</div>} /></I18nextProvider>);
    });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    return { act, host, close: async () => { await act(async () => root.unmount()); host.remove(); } };
  }

  for (const state of ["loading", "error", "empty", "ready"] as const) test(`desktop Pendiente hoy keeps one Add action when the month is ${state}`, async () => {
    const base = clientOf(state === "ready" ? [document_({ status: "pendiente" })] : []);
    const client: MonthCloseClient = state === "loading" ? {
      ...base,
      load: async () => new Promise<never>(() => {}),
      openItems: async () => new Promise<never>(() => {}),
    } : state === "error" ? { ...base, load: async () => { throw new MonthCloseError("unavailable", "Unavailable"); } } : base;
    const view = await renderView(client, undefined, true);
    try {
      assert.equal(view.host.querySelectorAll('[data-testid="month-close-money"]').length, 1);
      assert.equal(view.host.querySelectorAll('[data-testid="home-heading-add"]').length, 1);
      assert.ok(view.host.querySelector('[data-testid="month-close-money"] [data-testid="home-heading-add"]'));
      if (state === "loading") assert.ok(view.host.querySelector('[data-testid="month-close-money-loading"]'));
      if (state === "error") assert.ok(view.host.querySelector('[data-testid="month-close-error"]'));
      if (state === "empty") assert.ok(view.host.querySelector('[data-testid="month-close-empty"]'));
      if (state === "error" || state === "empty") assert.ok(view.host.querySelector('[data-testid="month-close-nothing-open"]'), "independently loaded open items retain their confirmed empty state");
    } finally { await view.close(); }
  });

  test("38fr and 62fr, 24px apart: greeting beside Pendiente hoy, then the month's figures as two cards on the same columns", async () => {
    const view = await renderView(createMockMonthCloseClient({ now }));
    try {
      const grid = view.host.querySelector<HTMLElement>('[data-testid="month-close"]')!;
      const classes = (selector: string) => view.host.querySelector<HTMLElement>(selector)!.className;
      assert.ok(grid.parentElement!.classList.contains("@container"), "the columns follow the canvas, not the window");
      assert.match(grid.className, /@min-\[56rem\]:grid-cols-\[38fr_62fr\]/);
      assert.match(grid.className, /@min-\[56rem\]:gap-6(\s|$)/);
      assert.match(classes('[data-testid="month-close-head"]'), /@min-\[56rem\]:col-start-1 @min-\[56rem\]:row-start-1/);
      assert.ok(view.host.querySelector('[data-testid="month-close-head"] [data-testid="inicio-greeting-row"]'), "the greeting row heads the left column");
      const money = classes('[data-testid="month-close-money"]');
      assert.match(money, /@min-\[56rem\]:col-start-2/);
      assert.match(money, /@min-\[56rem\]:row-span-2 @min-\[56rem\]:row-start-1 @min-\[56rem\]:grid @min-\[56rem\]:grid-rows-subgrid/, "its heading shares row 1, its cards row 2");
      assert.match(classes("#month-close-money-title"), /@min-\[56rem\]:text-\[26px\]/, "Pendiente hoy at the greeting's size");
      const cards = view.host.querySelector<HTMLElement>('[data-testid="month-close-cards"]')!;
      assert.match(cards.className, /@min-\[56rem\]:col-span-2 @min-\[56rem\]:grid-cols-subgrid/);
      const month = cards.querySelector('[data-testid="month-close-cards-month"]')!;
      const result = cards.querySelector<HTMLElement>('[data-testid="month-close-cards-result"]')!;
      assert.deepEqual([...month.children].map((node) => node.getAttribute("data-testid")), ["month-close-income", "month-close-expenses", "month-close-net"]);
      assert.deepEqual([...result.children].map((node) => node.getAttribute("data-testid")), ["month-close-itbis-sales", "month-close-itbis-purchases"]);
      // Twice the card's 20px padding plus the 24px between Por cobrar and Por pagar puts the two ITBIS totals on their columns.
      assert.match(result.className, /p-5/);
      assert.match(result.className, /@min-\[56rem\]:gap-x-16/);
      const order = [...view.host.querySelectorAll('[data-testid="month-close-head"], [data-testid="month-close-cards"], [data-testid="month-close-money"]')].map((node) => node.getAttribute("data-testid"));
      assert.deepEqual(order, ["month-close-head", "month-close-cards", "month-close-money"], "one column keeps today's order");
    } finally { await view.close(); }
  });
});
