import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, createMockMonthCloseClient, MonthCloseError, openItemsFrom, type MonthCloseClient, type MonthCloseDocument, type MonthCloseSnapshot } from "../lib/business-month-close";
import { renderMonthCloseView } from "./helpers/month-close-view";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const now = new Date(2026, 9, 18);
const noOpenItems = async () => openItemsFrom([], "2026-10-18");

function statusCell(count: number, beforeItbisMinor: number) {
  return { count, before_itbis_minor: beforeItbisMinor };
}

describe("month selection", () => {
  test("the month picker offers supported months only, sends the chosen month, and returns focus", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("../public/locales/es-419/common.json")).default;
    const { BusinessMonthCloseView } = await import("../components/business-app/BusinessMonthClosePanel");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const loads: string[] = [];
    const inner = createMockMonthCloseClient({ now });
    const client: MonthCloseClient = {
      ...inner,
      async load(month, scope) {
        loads.push(month);
        return inner.load(month, scope);
      },
    };
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <BusinessMonthCloseView layout="finance" arrange={({ month, money }) => <>{month}{money}</>} settlement client={client} now={now} />
        </I18nextProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
    });
    const trigger = host.querySelector('[data-testid="month-close-month"]');
    assert.ok(trigger instanceof HTMLButtonElement);
    assert.equal(trigger.textContent, "Octubre 2026");
    assert.match(trigger.className, /text-\[18px\]/, "the month uses the card heading size");
    assert.match(trigger.className, /min-h-11/);
    assert.equal(trigger.closest("h1, h2, h3, h4"), null, "the switcher is not a heading");
    assert.match(trigger.className, /font-medium/);
    assert.doesNotMatch(trigger.className, /font-bold|font-semibold/);
    assert.equal(host.querySelector('[data-testid="month-close-month-next"]')?.hasAttribute("disabled"), true);
    const previous = host.querySelector('[data-testid="month-close-month-prev"]');
    const next = host.querySelector('[data-testid="month-close-month-next"]');
    assert.match(previous?.className ?? "", /h-11/);
    assert.match(previous?.className ?? "", /w-11/);
    assert.match(next?.className ?? "", /h-11/);
    assert.match(next?.className ?? "", /w-11/);

    await act(async () => {
      trigger.click();
    });
    const picker = document.querySelector('[data-testid="month-close-month-picker"]');
    assert.equal(picker?.getAttribute("role"), "listbox");
    const future = document.querySelector('[data-month="2026-11"]');
    const current = document.querySelector('[data-month="2026-10"]');
    assert.equal(future, null);
    assert.deepEqual(
      [...picker!.querySelectorAll<HTMLElement>('[role="option"]')].map((option) => option.dataset.month),
      ["2026-08", "2026-09", "2026-10"],
    );
    assert.equal(current?.getAttribute("aria-selected"), "true");
    assert.equal(loads.includes("2026-11"), false);
    assert.equal(trigger.textContent, "Octubre 2026");
    assert.ok(document.querySelector('[data-testid="month-close-month-picker"]'));

    trigger.focus();
    await act(async () => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    assert.equal(document.querySelector('[data-testid="month-close-month-picker"]'), null);
    assert.equal(document.activeElement, trigger);

    await act(async () => {
      trigger.click();
    });
    const september = document.querySelector('[data-month="2026-09"]');
    assert.equal(september?.getAttribute("aria-disabled"), null);
    await act(async () => {
      september?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await act(async () => {
      await Promise.resolve();
    });
    assert.equal(loads.includes("2026-09"), true);
    assert.equal(trigger.textContent, "Septiembre 2026");
    assert.equal(document.querySelector('[data-testid="month-close-month-picker"]'), null);
    assert.equal(document.activeElement, trigger);
    assert.equal(host.querySelector('[data-testid="month-close-month-next"]')?.hasAttribute("disabled"), false);

    await act(async () => root.unmount());
    host.remove();
  });
});

describe("month close layouts", () => {
  const renderView = (client: MonthCloseClient, businessCurrency: string | null = null) => renderMonthCloseView(client, now, businessCurrency);

  test("loading keeps the month card and money-card skeletons", async () => {
    const client: MonthCloseClient = {
      mode: "mock",
      load: () => new Promise(() => undefined),
      openItems: () => new Promise(() => undefined),
      markCobrado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPagado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPendiente: () => Promise.reject(new MonthCloseError("unavailable", "undo failed")),
    };
    const { act, host, root } = await renderView(client);
    const loading = host.querySelector('[data-testid="home-month-body"]');
    assert.equal(loading?.getAttribute("data-state"), "loading");
    assert.equal(loading?.getAttribute("aria-busy"), "true");
    assert.ok(host.querySelector('[data-testid="month-close-money-loading"]'));
    assert.equal(host.querySelector('[data-testid="home-month-income"]'), null);
    await act(async () => root.unmount());
    host.remove();
  });

  test("a first month shows zero figures and keeps the month picker", async () => {
    const client: MonthCloseClient = {
      mode: "mock",
      async load(month) {
        return { month, from: `${month}-01`, to: `${month}-31`, unreviewed_movements: 0, earliest_month: null, today: "2026-10-18", payment_methods: ["otro"], dgii_forms: null, documents: [], figures: [], fiscal_rows: [], not_ready_rows: [] };
      },
      openItems: noOpenItems,
      markCobrado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPagado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPendiente: () => Promise.reject(new MonthCloseError("unavailable", "undo failed")),
    };
    const { act, host, root } = await renderView(client, "DOP");
    assert.ok(host.querySelector('[data-testid="home-month-first-day"]'));
    assert.equal(host.querySelector('[data-testid="home-month-income"]')?.getAttribute("data-amount"), "0");
    const action = host.querySelector<HTMLButtonElement>('[data-testid="month-close-month"]')!;
    assert.equal(host.querySelector('[data-testid="month-close-month-picker"]'), null);
    await act(async () => { action.click(); });
    assert.ok(document.body.querySelector('[data-testid="month-close-month-picker"]'), "Elegir mes opens the month picker");
    await act(async () => root.unmount());
    host.remove();
  });

  test("overdue rows sit inside the money cards with how late they are, and settled rows leave them", async () => {
    const { act, host, root } = await renderView(createMockMonthCloseClient({ now }));
    const receivable = host.querySelector('[data-testid="month-close-receivable"]');
    const payable = host.querySelector('[data-testid="month-close-payable"]');
    const mark = host.querySelector('[data-testid="month-close-mark-cobrado"]');
    assert.equal(mark, null, "Inicio has no one-tap settlement control");
    assert.equal(host.querySelector('[data-testid="month-close-state-overdue"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-state-matched"]'), null);

    const farmacia = receivable?.querySelector('[data-document-id="inv-farmacia"]');
    assert.equal(farmacia?.getAttribute("data-overdue"), "true");
    assert.equal(farmacia?.querySelector('[data-testid="month-close-lateness"]')?.textContent, "16 días tarde");
    assert.equal(farmacia?.querySelector('[data-testid="month-close-lateness"]')?.getAttribute("data-tone"), "overdue");
    assert.equal(receivable?.querySelector('[data-document-id="inv-taller"]')?.getAttribute("data-overdue"), "false");
    assert.equal(receivable?.querySelector('[data-document-id="inv-taller"] [data-testid="month-close-lateness"]')?.textContent, "vence en 10 días");
    const transporte = payable?.querySelector('[data-document-id="rcpt-transporte"]');
    assert.equal(transporte?.getAttribute("data-overdue"), "true");
    assert.match(transporte?.textContent ?? "", /13 días tarde/);
    assert.equal(payable?.querySelector('[data-document-id="rcpt-edenorte"]')?.getAttribute("data-overdue"), "false");
    assert.match(payable?.querySelector('[data-document-id="rcpt-edenorte"]')?.textContent ?? "", /vence en 7 días/);
    assert.ok(receivable?.querySelector('[data-document-id="inv-luna"]'), "a September invoice still pending stays in Por cobrar while October is open");
    assert.ok(payable?.querySelector('[data-document-id="rcpt-rosa"]'), "a September receipt still pending stays in Por pagar");

    assert.equal(host.querySelector('[data-document-id="inv-colmado"]'), null);
    assert.equal(host.querySelector('[data-document-id="rcpt-ferreteria"]'), null);
    await act(async () => root.unmount());
    host.remove();
  });

  test("a money card shows three rows, then Ver las N and Ver menos", async () => {
    const invoice = (id: string, day: number): MonthCloseDocument => ({
      id,
      kind: "invoice",
      currency: "DOP",
      counterparty: `Cliente ${id}`,
      occurred_on: "2026-10-04",
      due_on: `2026-10-${String(day).padStart(2, "0")}`,
      amount: "100.00",
      itbis: null,
      rnc: "101-23456-7",
      ncf: "B0100000042",
      ecf: null,
      status: "pendiente",
    });
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      today: "2026-10-18",
      payment_methods: ["efectivo", "otro"],
      from: "2026-10-01",
      to: "2026-10-31",
      unreviewed_movements: 0,
      earliest_month: null, dgii_forms: null,
      documents: [invoice("a", 20), invoice("b", 21), invoice("c", 22), invoice("d", 23), invoice("e", 24)],
      figures: [], fiscal_rows: [], not_ready_rows: [],
    };
    const client: MonthCloseClient = {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return openItemsFrom(snapshot.documents, "2026-10-18"); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
    };
    const { act, host, root } = await renderView(client);
    const column = () => host.querySelector('[data-testid="month-close-receivable"]');
    const order = [...host.querySelectorAll('[data-testid="month-close-receivable"], [data-testid="month-close-payable"], [data-testid="home-month"]')].map((node) => node.getAttribute("data-testid"));
    assert.deepEqual(order, ["home-month", "month-close-receivable", "month-close-payable"], "the month's figures, then what is pending from every month");
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 3);
    assert.equal(column()?.querySelector('[data-document-id="e"]'), null);
    assert.equal(column()?.querySelector("h4")?.textContent, "Por cobrar");
    assert.equal(column()?.querySelector('[data-testid="month-close-receivable-total"]')?.textContent, "RD$ 500.00", "the total carries the currency, so a row is the number");
    assert.equal(column()?.querySelector('[data-document-id="a"] .cuadrao-amount')?.textContent, "100.00");
    assert.match(column()?.querySelector('[data-document-id="a"] .cuadrao-amount')?.className ?? "", /text-right.*tabular-nums/);
    const toggle = () => [...(column()?.querySelectorAll("button") ?? [])].find((item) => item.hasAttribute("aria-expanded"));
    assert.equal(toggle()?.textContent, "Ver las 5");
    await act(async () => { toggle()?.click(); });
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 5);
    assert.equal(toggle()?.textContent, "Ver menos");
    await act(async () => { toggle()?.click(); });
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 3);
    await act(async () => root.unmount());
    host.remove();
  });

  test("unknown figures say a short dash and never a zero", async () => {
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      today: "2026-10-18",
      payment_methods: ["efectivo", "otro"],
      from: "2026-10-01",
      to: "2026-10-31",
      unreviewed_movements: 0,
      earliest_month: null, dgii_forms: null,
      documents: [], fiscal_rows: [], not_ready_rows: [],
      figures: [{ currency: "DOP", income_before_itbis: null, expense_before_itbis: null, net_before_itbis: null, itbis_paid: null }],
    };
    const client: MonthCloseClient = {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return openItemsFrom(snapshot.documents, "2026-10-18"); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
    };
    const { host, root, act } = await renderView(client);
    for (const id of ["home-month-income", "home-month-expenses", "home-month-net", "home-month-itbis-sales", "home-month-itbis-purchases"]) {
      const card = host.querySelector(`[data-testid="${id}"]`);
      assert.equal(card?.getAttribute("data-state"), "unknown");
      assert.equal(card?.getAttribute("data-amount"), null);
      assert.ok((card?.textContent ?? "").includes("-"));
      assert.ok(!(card?.textContent ?? "").includes("—"), "never the long dash");
      assert.doesNotMatch(card?.textContent ?? "", /RD\$/);
      assert.doesNotMatch(card?.textContent ?? "", /0[,.]00/);
    }
    assert.ok(!(host.textContent ?? "").includes("\u2014"), "the month close never shows the long dash");
    assert.equal(host.textContent?.includes("Sube el estado de cuenta"), false);
    assert.equal(host.textContent?.includes("sin comprobante"), false);
    assert.equal(host.querySelectorAll('[data-primary="true"]').length, 0);
    await act(async () => root.unmount());
    host.remove();
  });

  test("switching months keeps previous numbers until the new month arrives", async () => {
    const inner = createMockMonthCloseClient({ now });
    let calls = 0;
    let marks = 0;
    let release: (value: MonthCloseSnapshot) => void = () => {};
    const client: MonthCloseClient = {
      mode: "mock",
      load(month, scope) {
        calls += 1;
        if (calls === 1) return inner.load(month, scope);
        return new Promise((resolve) => { release = resolve; });
      },
      openItems: (scope) => inner.openItems(scope),
      markCobrado(id, scope, day) {
        marks += 1;
        return inner.markCobrado(id, scope, day);
      },
      markPagado(id, scope, day) {
        marks += 1;
        return inner.markPagado(id, scope, day);
      },
      markPendiente: (id, scope) => inner.markPendiente(id, scope),
    };
    const { act, host, root } = await renderView(client);
    const income = host.querySelector('[data-testid="home-month-income"]')?.textContent ?? "";
    assert.match(income, /RD\$ 58,400(?![.\d])/);
    assert.match(host.textContent ?? "", /Farmacia Central/);
    await act(async () => {
      host.querySelector<HTMLButtonElement>('[data-testid="month-close-month-prev"]')?.click();
    });
    assert.equal(host.querySelector('[data-testid="home-month-income"]')?.textContent, income);
    assert.match(host.textContent ?? "", /Farmacia Central/);
    assert.equal(host.querySelector('[data-testid="home-month-body"]')?.getAttribute("data-state"), "ready");
    await act(async () => {
      release(await inner.load("2026-09"));
      await Promise.resolve();
    });
    assert.match(host.querySelector('[data-testid="home-month-income"]')?.textContent ?? "", /RD\$ 17,000(?![.\d])/);
    assert.ok(host.querySelector('[data-testid="month-close-receivable"] [data-document-id="inv-farmacia"]'), "the columns are every month's pending documents, so a month change keeps them");
    assert.equal(marks, 0, "changing months never settles documents");
    await act(async () => root.unmount());
    host.remove();
  });

describe("Inicio ITBIS totals", () => {
  function clientFor(figures: { itbis_paid: string; itbis_charged: string; net: string }): MonthCloseClient {
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10", today: "2026-10-18", from: "2026-10-01", to: "2026-10-31",
      unreviewed_movements: 0, earliest_month: null, payment_methods: ["otro"], dgii_forms: null,
      documents: [], fiscal_rows: [], not_ready_rows: [],
      figures: [{ currency: "DOP", income_before_itbis: "1000.00", expense_before_itbis: "2000.00", net_before_itbis: figures.net, itbis_paid: figures.itbis_paid, itbis_charged: figures.itbis_charged, itbis_cobrado: null, net_result_final: true, pending_count: 0 }],
    };
    return {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return openItemsFrom(snapshot.documents, "2026-10-18"); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
    };
  }
  const BALANCE = /saldo|a favor|a pagar|por pagar|in your favor|to pay|balance|pérdida/i;

  for (const [paid, charged] of [["1250.49", "180.00"], ["180.00", "1250.50"], ["0.00", "0.00"]] as const) {
    test(`ITBIS en ventas ${charged} and ITBIS en compras ${paid} are two plain totals, never a balance`, async () => {
      const { act, host, root } = await renderView(clientFor({ itbis_paid: paid, itbis_charged: charged, net: "-1000.00" }));
      const read = (testId: string) => host.querySelector(`[data-testid="${testId}"]`)?.textContent;
      const whole = (amount: string) => `RD$ ${Number(amount.split(".")[0]) + (Number(amount.split(".")[1]) >= 50 ? 1 : 0)}`.replace(/(\d)(?=(\d{3})+$)/g, "$1,");
      assert.equal(read("home-month-itbis-sales"), whole(charged));
      assert.match(host.querySelector('[data-testid="home-month"]')?.textContent ?? "", /ITBIS en ventas/);
      assert.equal(read("home-month-itbis-purchases"), whole(paid));
      assert.match(host.querySelector('[data-testid="home-month"]')?.textContent ?? "", /ITBIS en compras/);
      assert.equal(host.querySelector('[data-testid="home-month-itbis-sales"]')?.getAttribute("data-amount"), charged);
      assert.equal(host.querySelector('[data-testid="home-month-itbis-purchases"]')?.getAttribute("data-amount"), paid);
      assert.equal(host.querySelector('[data-testid="month-close-itbis"]'), null, "no balance card");
      assert.doesNotMatch(host.querySelector('[data-testid="home-month"]')?.textContent ?? "", BALANCE);
      await act(async () => root.unmount());
      host.remove();
    });
  }

  test("a negative Resultado neto is a plain minus sign in the normal text color", async () => {
    const { act, host, root } = await renderView(clientFor({ itbis_paid: "0.00", itbis_charged: "0.00", net: "-1000.00" }));
    const amount = host.querySelector('[data-testid="home-month-net"]');
    assert.equal(amount?.textContent, "-RD$ 1,000");
    assert.match(amount?.className ?? "", /text-\[#172b26\]|text-\[#7d8a84\]/);
    assert.doesNotMatch(amount?.className ?? "", /9e2f39|red/);
    assert.doesNotMatch(host.textContent ?? "", /pérdida/i);
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("a fully settled month", () => {
  test("a month with everything collected and paid is not empty and has nothing left in the money columns", async () => {
    const client = createHttpMonthCloseClient(async (path) => path === "/business/open-items" ? ({
      today: "2026-10-18",
      cuentas_por_cobrar: { count: 0, totals: [], items: [] },
      cuentas_por_pagar: { count: 0, totals: [], items: [] },
    }) : ({
      month: "2026-10",
      today: "2026-10-18",
      payment_methods: ["efectivo", "otro"],
      from: "2026-10-01",
      to: "2026-10-31",
      closed: true,
      reasons: [],
      dgii_forms: { "606": "prepared_candidate", "607": "prepared_candidate" },
      currencies: [{
        currency: "DOP",
        income_before_itbis_minor: 400000, income_before_itbis: "4000.00",
        expense_before_itbis_minor: 100000, expense_before_itbis: "1000.00",
        net_result_minor: 300000, net_result: "3000.00",
        itbis_charged_minor: 72000, itbis_charged: "720.00",
        itbis_paid_minor: 18000, itbis_paid: "180.00",
        by_status: {
          invoices: { pendiente: statusCell(0, 0), cobrado: statusCell(2, 200000) },
          receipts: { pendiente: statusCell(0, 0), pagado: statusCell(1, 100000) },
        },
        net_result_final: true,
      }],
      missing_rnc: [],
      missing_ncf: [],
      missing_fiscal_rows: [],
      missing_fiscal_data: [],
      cuentas_por_cobrar: [],
      cuentas_por_pagar: [],
    }));
    const { act, host, root } = await renderMonthCloseView(client, now, null, { count: 0 });
    assert.match(host.querySelector('[data-testid="home-month-net"]')?.textContent ?? "", /RD\$ 3,000(?![.\d])/);
    assert.equal(host.querySelector('[data-testid="month-close-close"]'), null, "there is no close action");
    assert.equal(host.textContent?.includes("Ya tienes todo para el 606 y el 607"), false, "no filing line");
    assert.match(host.querySelector('[data-testid="month-close-nothing-open"]')?.textContent ?? "", /Todo al día/);
    assert.equal(host.querySelector('[data-testid="month-close-receivable"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-payable"]'), null);
    const order = [...host.querySelectorAll('[data-testid="month-close-nothing-open"], [data-testid="home-month"]')].map((node) => node.getAttribute("data-testid"));
    assert.deepEqual(order, ["home-month", "month-close-nothing-open"]);
    assert.match(host.querySelector('[data-testid="home-month-income"]')?.textContent ?? "", /RD\$ 4,000(?![.\d])/);
    assert.equal(host.querySelector('[data-testid="month-close-empty"]'), null);
    assert.equal(host.textContent?.includes("Este mes no tiene documentos"), false);
    await act(async () => root.unmount());
    host.remove();
  });
});
});
