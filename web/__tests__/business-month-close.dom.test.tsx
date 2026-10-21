import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, createMockMonthCloseClient, MonthCloseError, openItemsFrom, statementMissingBlocker, unmatchedCharges, type MonthCloseClient, type MonthCloseDocument, type MonthCloseSnapshot } from "../lib/business-month-close";
import type { BusinessContextValue } from "../components/business-app/BusinessWorkspace";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const now = new Date(2026, 9, 18);
const noOpenItems = async () => openItemsFrom([]);

function delayingFailure(inner: MonthCloseClient): MonthCloseClient {
  return {
    ...inner,
    async markCobrado() {
      await new Promise((resolve) => setTimeout(resolve, 40));
      throw new MonthCloseError("unavailable", "mark failed");
    },
    async markPagado() {
      await new Promise((resolve) => setTimeout(resolve, 40));
      throw new MonthCloseError("unavailable", "mark failed");
    },
  };
}

function statusCell(count: number, beforeItbisMinor: number) {
  return { count, before_itbis_minor: beforeItbisMinor };
}

function openByStatus() {
  return {
    invoices: { pendiente: statusCell(1, 100000), cobrado: statusCell(0, 0) },
    receipts: { pendiente: statusCell(0, 0), pagado: statusCell(0, 0) },
  };
}

function settledByStatus() {
  return {
    invoices: { pendiente: statusCell(0, 0), cobrado: statusCell(1, 100000) },
    receipts: { pendiente: statusCell(0, 0), pagado: statusCell(1, 50000) },
  };
}

describe("month close optimistic marks", () => {
  test("a failed mark shows the new status, then rolls it back and tells the person", async () => {
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
    const client = delayingFailure(createMockMonthCloseClient({ now }));
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <BusinessMonthCloseView client={client} now={now} />
        </I18nextProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
    });
    const row = () => host.querySelector('[data-testid="month-close-receivable"] [data-document-id="inv-taller"]');
    const settleTask = () => host.querySelector('[data-testid="month-close-task-settle"]')?.textContent ?? "";
    assert.equal(row()?.getAttribute("data-status"), "pendiente");
    assert.match(settleTask(), /Marca 4 documentos/);
    const button = host.querySelector('[data-document-id="inv-taller"] [data-testid="month-close-mark-cobrado"]');
    assert.ok(button instanceof HTMLButtonElement);
    await act(async () => {
      button.click();
      await Promise.resolve();
    });
    assert.equal(row(), null);
    assert.match(settleTask(), /Marca 3 documentos/);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60));
    });
    assert.equal(row()?.getAttribute("data-status"), "pendiente");
    assert.match(settleTask(), /Marca 4 documentos/);
    const problem = host.querySelector('[data-testid="month-close-work-problem"]');
    assert.equal(problem?.getAttribute("role"), "alert", "a failed mark says so beside the work, not in a toast");
    assert.match(problem?.textContent ?? "", /volvió al anterior/);
    assert.ok([...(problem?.querySelectorAll("button") ?? [])].some((button) => button.textContent === "Reintentar"));
    assert.equal(host.querySelector('[data-testid="month-close-close"]'), null, "Cerrar stays hidden while steps remain");
    await act(async () => root.unmount());
    host.remove();
  });

  test("without approval permission the month cannot be marked or closed", async () => {
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
          <BusinessMonthCloseView client={createMockMonthCloseClient({ now })} now={now} scopeKey="grant-read" canMutate={false} />
        </I18nextProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
    });
    assert.equal(host.querySelector('[data-testid="month-close-close"]'), null);
    assert.match(host.querySelector('[data-testid="month-close-reason"]')?.textContent ?? "", /permiso de aprobación/);
    assert.equal(host.querySelector('[data-testid="month-close-mark-cobrado"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-mark-pagado"]'), null);
    await act(async () => root.unmount());
    host.remove();
  });

  test("the month picker sends the chosen month, returns focus, and disables future months", async () => {
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
          <BusinessMonthCloseView client={client} now={now} />
        </I18nextProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
    });
    const trigger = host.querySelector('[data-testid="month-close-month"]');
    assert.ok(trigger instanceof HTMLButtonElement);
    assert.equal(trigger.textContent, "Octubre 2026");
    assert.match(trigger.className, /text-\[16px\]/, "the month is a control, not a title");
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
    assert.equal(future?.getAttribute("aria-disabled"), "true");
    assert.equal(current?.getAttribute("aria-selected"), "true");
    await act(async () => {
      future?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
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
  async function renderView(client: MonthCloseClient) {
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
          <BusinessMonthCloseView client={client} now={now} />
        </I18nextProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
    });
    return { act, host, root };
  }

  test("loading keeps the summary cards and the row skeleton", async () => {
    const client: MonthCloseClient = {
      mode: "mock",
      load: () => new Promise(() => undefined),
      openItems: () => new Promise(() => undefined),
      markCobrado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPagado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPendiente: () => Promise.reject(new MonthCloseError("unavailable", "undo failed")),
      closeMonth: () => Promise.reject(new MonthCloseError("unavailable", "close failed")),
    };
    const { act, host, root } = await renderView(client);
    const loading = host.querySelector('[data-testid="month-close-loading"]');
    assert.equal(loading?.getAttribute("data-layout"), "loading");
    assert.equal(host.querySelectorAll('[data-testid="month-close-loading-card"]').length, 4);
    assert.equal(host.querySelectorAll('[data-testid="month-close-loading-row"]').length, 3);
    await act(async () => root.unmount());
    host.remove();
  });

  test("an empty month is a centered title, a line, and a month button", async () => {
    const client: MonthCloseClient = {
      mode: "mock",
      async load(month) {
        return { month, from: `${month}-01`, to: `${month}-31`, currency: "DOP", closed_at: null, earliest_month: null, documents: [] };
      },
      openItems: noOpenItems,
      markCobrado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPagado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPendiente: () => Promise.reject(new MonthCloseError("unavailable", "undo failed")),
      closeMonth: () => Promise.reject(new MonthCloseError("unavailable", "close failed")),
    };
    const { act, host, root } = await renderView(client);
    const empty = host.querySelector('[data-testid="month-close-empty"]');
    assert.equal(empty?.getAttribute("data-layout"), "empty");
    const state = empty?.querySelector('[data-empty-kind="first_run"]');
    assert.ok(state, "the empty month is a first-run empty state");
    assert.ok(state.querySelector("svg[data-mark]"), "the empty month is drawn");
    assert.equal(state.querySelector("h3")?.textContent, "Este mes no tiene documentos");
    assert.equal(state.querySelector("p")?.textContent, "Agrega los recibos y facturas de este mes para ver tus ingresos, gastos e ITBIS.");
    const buttons = [...(empty?.querySelectorAll("button") ?? [])];
    assert.deepEqual(buttons.map((button) => button.textContent?.trim()), ["Elegir mes"], "without an add door only the month button shows");
    const action = buttons[0];
    assert.match(action.className, /min-h-11/);
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
    assert.match(mark?.className ?? "", /h-11 w-11/);
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
    assert.match(host.querySelector('[data-testid="month-close-task-settle"]')?.textContent ?? "", /2 vencidos/);
    await act(async () => root.unmount());
    host.remove();
  });

  test("a money card shows four rows, then Ver las N and Ver menos", async () => {
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
      from: "2026-10-01",
      to: "2026-10-31",
      currency: "DOP",
      closed_at: null,
      earliest_month: null,
      documents: [invoice("a", 20), invoice("b", 21), invoice("c", 22), invoice("d", 23), invoice("e", 24)],
    };
    const client: MonthCloseClient = {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return openItemsFrom(snapshot.documents); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
      async closeMonth() { throw new Error("no close"); },
    };
    const { act, host, root } = await renderView(client);
    const column = () => host.querySelector('[data-testid="month-close-receivable"]');
    const order = [...host.querySelectorAll('[data-testid="month-close-checklist"], [data-testid="month-close-receivable"], [data-testid="month-close-payable"], [data-testid="month-close-cards"]')].map((node) => node.getAttribute("data-testid"));
    assert.deepEqual(order, ["month-close-checklist", "month-close-cards", "month-close-receivable", "month-close-payable"], "the month and its figures, then what is pending from every month");
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 4);
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
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 4);
    await act(async () => root.unmount());
    host.remove();
  });

  test("unknown figures say — and never a zero, and unrendered blockers stay off the screen", async () => {
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      currency: "DOP",
      closed_at: null,
      earliest_month: null,
      documents: [],
      figures: { income_before_itbis: null, expense_before_itbis: null, net_before_itbis: null, itbis_owed: null, by_status: openByStatus() },
      blockers: [statementMissingBlocker, unmatchedCharges(2)],
    };
    const client: MonthCloseClient = {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return openItemsFrom(snapshot.documents); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
      async closeMonth() { throw new Error("no close"); },
    };
    const { host, root, act } = await renderView(client);
    for (const id of ["month-close-income", "month-close-expenses", "month-close-net", "month-close-itbis"]) {
      const card = host.querySelector(`[data-testid="${id}"]`);
      assert.equal(card?.getAttribute("data-state"), "pending");
      assert.equal(card?.getAttribute("data-amount"), null);
      assert.match(card?.textContent ?? "", /—/);
      assert.doesNotMatch(card?.textContent ?? "", /RD\$/);
      assert.doesNotMatch(card?.textContent ?? "", /0[,.]00/);
    }
    assert.equal(host.textContent?.includes("Sube el estado de cuenta"), false);
    assert.equal(host.textContent?.includes("sin comprobante"), false);
    assert.equal(host.querySelectorAll('[data-primary="true"]').length, 0);
    await act(async () => root.unmount());
    host.remove();
  });

  test("switching months keeps the previous numbers and shows the loading line", async () => {
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
      closeMonth: (month, scope) => inner.closeMonth(month, scope),
    };
    const { act, host, root } = await renderView(client);
    const income = host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "";
    assert.match(income, /RD\$ 58\.4 mil/);
    assert.match(host.textContent ?? "", /Farmacia Central/);
    await act(async () => {
      host.querySelector<HTMLButtonElement>('[data-testid="month-close-month-prev"]')?.click();
    });
    assert.equal(host.querySelector('[data-testid="month-close-income"]')?.textContent, income);
    assert.match(host.textContent ?? "", /Farmacia Central/);
    assert.equal(host.querySelector('[data-testid="month-close-cards"]')?.getAttribute("data-loading"), "true");
    assert.equal(host.querySelector('[data-testid="month-close-loading"]'), null);
    assert.match(host.querySelector('[data-testid="month-close-refreshing"]')?.textContent ?? "", /Cargando el mes/);
    const marksWhileLoading = [...host.querySelectorAll('[data-testid="month-close-mark-cobrado"], [data-testid="month-close-mark-pagado"]')];
    assert.ok(marksWhileLoading.length >= 2);
    assert.ok(marksWhileLoading.every((button) => button instanceof HTMLButtonElement && button.disabled));
    await act(async () => {
      (marksWhileLoading[0] as HTMLButtonElement).click();
      await Promise.resolve();
    });
    assert.equal(marks, 0);
    await act(async () => {
      release(await inner.load("2026-09"));
      await Promise.resolve();
    });
    assert.match(host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /RD\$ 17 mil/);
    assert.ok(host.querySelector('[data-testid="month-close-receivable"] [data-document-id="inv-farmacia"]'), "the columns are every month's pending documents, so a month change keeps them");
    assert.equal(host.querySelector('[data-testid="month-close-cards"]')?.getAttribute("data-loading"), null);
    await act(async () => root.unmount());
    host.remove();
  });

function wireLine(activityId: string, kind: "invoice" | "receipt", totalMinor: number, itbisMinor: number) {
  return {
    activity_id: activityId,
    document_kind: kind,
    currency: "DOP",
    occurred_on: "2026-10-04",
    total_minor: totalMinor,
    before_itbis_minor: totalMinor - itbisMinor,
    itbis_minor: itbisMinor,
    status: "pendiente",
  };
}

describe("fiscal complete months stay editable", () => {
  test("a month with complete fiscal data still allows Marcar cobrado and Marcar pagado", async () => {
    const calls: { path: string; method: string; body?: string }[] = [];
    const client = createHttpMonthCloseClient(async (path, init) => {
      calls.push({ path, method: init?.method ?? "GET", body: typeof init?.body === "string" ? init.body : undefined });
      if (init?.method === "PATCH") {
        return { activity_id: "act-invoice", document_kind: "invoice", status: "cobrado", settled_on: "2026-10-18", payment_method: "otro", changed: true };
      }
      if (path === "/business/open-items") {
        const marked = calls.some((call) => call.method === "PATCH");
        return {
          cuentas_por_cobrar: marked ? { count: 0, totals: [], items: [] } : { count: 1, totals: [{ currency: "DOP", total_minor: 118000, total: "1180.00" }], items: [wireLine("act-invoice", "invoice", 118000, 18000)] },
          cuentas_por_pagar: { count: 1, totals: [{ currency: "DOP", total_minor: 59000, total: "590.00" }], items: [wireLine("act-receipt", "receipt", 59000, 9000)] },
        };
      }
      return {
        month: "2026-10",
        from: "2026-10-01",
        to: "2026-10-31",
        closed: true,
        reasons: [],
        currencies: [{
          currency: "DOP",
          income_before_itbis: "4000.00",
          expense_before_itbis: "500.00",
          net_result: "3500.00",
          itbis_charged: "720.00",
          itbis_owed: "180.00",
          by_status: {
            invoices: { pendiente: statusCell(1, 100000), cobrado: statusCell(0, 0) },
            receipts: { pendiente: statusCell(1, 50000), pagado: statusCell(0, 0) },
          },
        }],
        missing_rnc: [],
        missing_ncf: [],
        cuentas_por_cobrar: [wireLine("act-invoice", "invoice", 118000, 18000)],
        cuentas_por_pagar: [wireLine("act-receipt", "receipt", 59000, 9000)],
      };
    });
    const { act, host, root } = await renderView(client);
    const cobrado = host.querySelector('[data-testid="month-close-mark-cobrado"]');
    const pagado = host.querySelector('[data-testid="month-close-mark-pagado"]');
    assert.ok(cobrado instanceof HTMLButtonElement);
    assert.ok(pagado instanceof HTMLButtonElement);
    assert.equal(cobrado.disabled, false);
    assert.equal(pagado.disabled, false);
    assert.equal(cobrado.getAttribute("aria-label"), "Marcar cobrado, Factura");
    assert.equal(pagado.getAttribute("aria-label"), "Marcar pagado, Gasto");
    assert.equal(host.querySelector('[data-testid="month-close-closed"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close"]')?.getAttribute("data-closed"), "false");
    assert.equal(host.querySelector('[data-testid="month-close-task-fiscal"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-checklist-left"]')?.textContent, "falta 1");
    assert.equal(host.querySelector('[data-testid="month-close-checklist-ready"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-reason"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-close-note"]'), null);
    assert.match(host.querySelector('[data-testid="month-close-filing"]')?.textContent ?? "", /Ya tienes todo para el 606 y el 607/);
    assert.equal(host.textContent?.includes("Listo"), false);
    assert.equal(host.textContent?.includes("Mes cerrado"), false);
    await act(async () => {
      cobrado.click();
      await Promise.resolve();
    });
    const patch = calls.find((call) => call.method === "PATCH");
    assert.equal(patch?.path, "/business/month-close/documents/act-invoice");
    assert.deepEqual(JSON.parse(patch?.body ?? "{}"), {
      status: "cobrado",
      settled_on: "2026-10-18",
      payment_method: "otro",
    });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    assert.equal(calls.filter((call) => call.path === "/business/open-items").length, 2, "marking rereads the open items");
    assert.equal(host.querySelector('[data-document-id="act-invoice"]'), null, "the reread no longer lists it");
    assert.match(host.querySelector('[data-testid="month-close-receivable-empty"]')?.textContent ?? "", /Todo cobrado/);
    await act(async () => root.unmount());
    host.remove();
  });

  test("an explicit closed_at locks both mark buttons", async () => {
    const invoice: MonthCloseDocument = {
      id: "inv-ready",
      kind: "invoice",
      currency: "DOP",
      counterparty: "Colmado Don Luis",
      occurred_on: "2026-10-04",
      due_on: "2026-10-20",
      amount: "1180.00",
      itbis: "180.00",
      rnc: "101-23456-7",
      ncf: "B0100000042",
      ecf: null,
      status: "pendiente",
    };
    const receipt: MonthCloseDocument = {
      ...invoice,
      id: "rcpt-ready",
      kind: "receipt",
      counterparty: "Ferretería La Esquina",
      amount: "590.00",
      itbis: "90.00",
      status: "pendiente",
    };
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      currency: "DOP",
      closed_at: "2026-10-18T15:00:00",
      closed: true,
      earliest_month: null,
      documents: [invoice, receipt],
    };
    const client: MonthCloseClient = {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return openItemsFrom(snapshot.documents); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
      async closeMonth() { throw new Error("no close"); },
    };
    const { act, host, root } = await renderView(client);
    assert.equal(host.querySelector('[data-testid="month-close-mark-cobrado"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-mark-pagado"]'), null);
    assert.match(host.querySelector('[data-testid="month-close-closed"]')?.textContent ?? "", /Mes cerrado/);
    assert.equal(host.querySelector('[data-testid="month-close"]')?.getAttribute("data-closed"), "true");
    assert.equal(host.querySelector('[data-testid="month-close-checklist"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-close"]'), null);
    assert.equal(host.textContent?.includes("Ya puedes cerrar"), false);
    await act(async () => root.unmount());
    host.remove();
  });

  test("a closed month still shows Pendiente hoy, and other months' items stay markable", async () => {
    const september: MonthCloseDocument = {
      id: "inv-september",
      kind: "invoice",
      currency: "DOP",
      counterparty: "Panadería Luna",
      occurred_on: "2026-09-10",
      due_on: "2026-09-20",
      amount: "5900.00",
      itbis: "900.00",
      rnc: "101-23456-7",
      ncf: "B0100000043",
      ecf: null,
      status: "pendiente",
    };
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      currency: "DOP",
      closed_at: "2026-10-18T15:00:00",
      closed: true,
      earliest_month: null,
      documents: [{ ...september, id: "inv-october", occurred_on: "2026-10-04", status: "cobrado" }],
    };
    const client: MonthCloseClient = {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return openItemsFrom([september]); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
      async closeMonth() { throw new Error("no close"); },
    };
    const { act, host, root } = await renderView(client);
    assert.ok(host.querySelector('[data-testid="month-close-money"]'), "Pendiente hoy covers every month, closed or not");
    const check = host.querySelector<HTMLButtonElement>('[data-testid="month-close-mark-cobrado"]');
    assert.ok(check && !check.disabled, "September's invoice can still be marked from a closed October");
    await act(async () => root.unmount());
    host.remove();
  });

  test("an incomplete month shows neither the filing line nor a closed label", async () => {
    const client = createMockMonthCloseClient({ now });
    const { act, host, root } = await renderView(client);
    assert.equal(host.querySelector('[data-testid="month-close-close-note"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-checklist-ready"]'), null);
    assert.equal(host.textContent?.includes("Listo"), false);
    assert.equal(host.textContent?.includes("Mes cerrado"), false);
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("Inicio ITBIS balance", () => {
  function amountSnapshot(itbisOwed: string): MonthCloseSnapshot {
    return {
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      currency: "DOP",
      closed_at: null,
      earliest_month: null,
      documents: [],
      figures: {
        income_before_itbis: "1000.00",
        expense_before_itbis: "2000.00",
        net_before_itbis: "-1000.00",
        itbis_owed: itbisOwed,
        by_status: settledByStatus(),
      },
    };
  }

  function clientFor(itbisOwed: string): MonthCloseClient {
    const snapshot = amountSnapshot(itbisOwed);
    return {
      mode: "mock",
      async load() { return snapshot; },
      async openItems() { return openItemsFrom(snapshot.documents); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
      async closeMonth() { throw new Error("no close"); },
    };
  }

  test("a negative ITBIS balance shows the credit label and the absolute amount", async () => {
    const { act, host, root } = await renderView(clientFor("-1250.00"));
    const card = host.querySelector('[data-testid="month-close-itbis"]');
    const [label, amount] = [...(card?.querySelectorAll("p") ?? [])].map((item) => item.textContent);
    assert.equal(label, "Saldo a favor de ITBIS");
    assert.equal(amount, "RD$ 1,250.00");
    assert.equal(/-/.test(amount ?? "missing"), false);
    assert.equal(card?.getAttribute("data-amount"), "1250.00");
    assert.equal(card?.textContent?.includes("reembolso"), false);
    assert.equal(card?.textContent?.includes("devuelven"), false);
    assert.equal(host.textContent?.includes("reembolso"), false);
    assert.equal(host.textContent?.includes("devuelven"), false);
    assert.equal(card?.textContent?.includes("ITBIS a pagar"), false);
    await act(async () => root.unmount());
    host.remove();
  });

  test("a positive ITBIS balance keeps ITBIS a pagar", async () => {
    const { act, host, root } = await renderView(clientFor("1250.00"));
    const card = host.querySelector('[data-testid="month-close-itbis"]');
    const [label, amount] = [...(card?.querySelectorAll("p") ?? [])].map((item) => item.textContent);
    assert.equal(label, "ITBIS a pagar");
    assert.equal(amount, "RD$ 1,250.00");
    assert.equal(card?.textContent?.includes("Saldo a favor de ITBIS"), false);
    await act(async () => root.unmount());
    host.remove();
  });

  test("a zero ITBIS balance keeps ITBIS a pagar", async () => {
    const { act, host, root } = await renderView(clientFor("0.00"));
    const card = host.querySelector('[data-testid="month-close-itbis"]');
    const [label, amount] = [...(card?.querySelectorAll("p") ?? [])].map((item) => item.textContent);
    assert.equal(label, "ITBIS a pagar");
    assert.equal(amount, "RD$ 0.00");
    assert.equal(card?.textContent?.includes("Saldo a favor de ITBIS"), false);
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("a fully settled month", () => {
  test("a month with everything collected and paid is not empty, is ready to close, and has nothing left in the money columns", async () => {
    const client = createHttpMonthCloseClient(async (path) => path === "/business/open-items" ? ({
      cuentas_por_cobrar: { count: 0, totals: [], items: [] },
      cuentas_por_pagar: { count: 0, totals: [], items: [] },
    }) : ({
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      closed: true,
      reasons: [],
      currencies: [{
        currency: "DOP",
        income_before_itbis: "4000.00",
        expense_before_itbis: "1000.00",
        net_result: "3000.00",
        itbis_charged: "720.00",
        itbis_owed: "180.00",
        by_status: {
          invoices: { pendiente: statusCell(0, 0), cobrado: statusCell(2, 200000) },
          receipts: { pendiente: statusCell(0, 0), pagado: statusCell(1, 100000) },
        },
      }],
      missing_rnc: [],
      missing_ncf: [],
      cuentas_por_cobrar: [],
      cuentas_por_pagar: [],
    }));
    const { act, host, root } = await renderView(client);
    assert.match(host.querySelector('[data-testid="month-close-net"]')?.textContent ?? "", /RD\$ 3,000\.00/);
    assert.match(host.querySelector('[data-testid="month-close-checklist-ready"]')?.textContent ?? "", /Todo listo para cerrar octubre\./);
    assert.equal(host.querySelector('[data-testid="month-close-checklist-left"]'), null);
    assert.match(host.querySelector('[data-testid="month-close-nothing-open"]')?.textContent ?? "", /Todo al día/);
    assert.equal(host.querySelector('[data-testid="month-close-receivable"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-payable"]'), null);
    const order = [...host.querySelectorAll('[data-testid="month-close-checklist"], [data-testid="month-close-nothing-open"], [data-testid="month-close-cards"]')].map((node) => node.getAttribute("data-testid"));
    assert.deepEqual(order, ["month-close-checklist", "month-close-cards", "month-close-nothing-open"]);
    assert.match(host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /RD\$ 4,000\.00/);
    assert.equal(host.querySelector('[data-testid="month-close-empty"]'), null);
    assert.equal(host.textContent?.includes("Este mes no tiene documentos"), false);
    await act(async () => root.unmount());
    host.remove();
  });
});

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

  test("the total names RD$, a USD row keeps US$, each currency has its own total, and the DOP cards leave both out", async () => {
    const client = createHttpMonthCloseClient(async (path) => path === "/business/open-items" ? ({
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
      from: "2026-10-01",
      to: "2026-10-31",
      closed: false,
      reasons: [],
      currencies: [{
        currency: "DOP",
        income_before_itbis: "1000.00",
        expense_before_itbis: "0.00",
        net_result: "1000.00",
        itbis_owed: "18.00",
      }],
      missing_rnc: [],
      missing_ncf: [],
      cuentas_por_cobrar: [line("act-usd", "invoice", "USD", "2026-10-06", 5000, null)],
      cuentas_por_pagar: [line("act-eur", "receipt", "EUR", "2026-10-07", 2000, null)],
    }));
    const { act, host, root } = await renderView(client);
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
    assert.match(host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /RD\$ 1,000\.00/);
    assert.equal(host.querySelector('[data-testid="month-close-income"]')?.textContent?.includes("US$"), false);
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("open items across months", () => {
  test("pending documents past the cap say how many more exist, and Ver las N reveals only loaded ones", async () => {
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
      cuentas_por_cobrar: { count: 107, totals: [{ currency: "DOP", total_minor: 10700000, total: "107000.00" }], items },
      cuentas_por_pagar: { count: 0, totals: [], items: [] },
    }) : ({
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      closed: true,
      reasons: [],
      currencies: [{ currency: "DOP", income_before_itbis: "0.00", expense_before_itbis: "0.00", net_result: "0.00", itbis_owed: "0.00", by_status: settledByStatus() }],
      missing_rnc: [],
      missing_ncf: [],
      cuentas_por_cobrar: [],
      cuentas_por_pagar: [],
    }));
    const { act, host, root } = await renderView(client);
    const column = () => host.querySelector('[data-testid="month-close-receivable"]');
    assert.ok(column()?.querySelector('[data-document-id="act-0"]'), "an April invoice shows while October is open");
    assert.equal(column()?.querySelector('[data-testid="month-close-receivable-total"]')?.textContent, "RD$ 107,000.00", "the total is the server's, past the cap, exact");
    assert.equal(column()?.querySelector('[data-testid="month-close-receivable-beyond"]')?.textContent, "Y 102 más que no se muestran aquí.");
    const toggle = [...(column()?.querySelectorAll("button") ?? [])].find((item) => item.hasAttribute("aria-expanded"));
    assert.equal(toggle?.textContent, "Ver las 5");
    await act(async () => { toggle?.click(); });
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 5);
    assert.ok(host.querySelector('[data-testid="month-close-payable-empty"]'));
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
      async load(month) { return { month, from: `${month}-01`, to: `${month}-31`, currency: "DOP", closed_at: null, earliest_month: null, documents: [] }; },
      async openItems() { return openItemsFrom([pending]); },
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async markPendiente() { throw new Error("no undo"); },
      async closeMonth() { throw new Error("no close"); },
    };
    const { act, host, root } = await renderView(client);
    assert.ok(host.querySelector('[data-testid="month-close-empty"]'));
    assert.match(host.querySelector('[data-document-id="inv-sept"]')?.textContent ?? "", /Clínica Aurora/);
    assert.match(host.querySelector('[data-document-id="inv-sept"]')?.textContent ?? "", /12 sept/);
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

describe("headline figures", () => {
  test("a row with a figure from 10,000 up reads short in one unit, with the exact amount in the tooltip and for a screen reader", async () => {
    const { act, host, root } = await renderView(createMockMonthCloseClient({ now }));
    const income = host.querySelector('[data-testid="month-close-income"]');
    const headline = income?.querySelector<HTMLElement>('[data-testid="month-close-headline"]');
    assert.ok(headline, "58,400 is a headline figure");
    assert.equal(headline.querySelector('[aria-hidden="true"]')?.textContent, "RD$ 58.4 mil");
    assert.equal(headline.querySelector(".sr-only")?.textContent, "RD$ 58,400.00");
    assert.equal(headline.tabIndex, 0, "keyboard focus reaches the exact amount");
    assert.ok(headline.closest(".cuadrao-amount"), "Ocultar montos still hides it");
    await act(async () => {
      headline.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 350));
    });
    assert.equal(document.querySelector('[role="tooltip"]')?.textContent, "RD$ 58,400.00");
    const expenses = host.querySelector('[data-testid="month-close-expenses"]');
    const beside = expenses?.querySelector<HTMLElement>('[data-testid="month-close-headline"]');
    assert.equal(beside?.querySelector('[aria-hidden="true"]')?.textContent, "RD$ 9.6 mil", "9,600 beside 58,400 shares its unit");
    assert.equal(beside?.querySelector(".sr-only")?.textContent, "RD$ 9,600.00");
    const column = host.querySelector('[data-testid="month-close-receivable"]');
    assert.equal(column?.querySelector('[data-testid="month-close-headline"]'), null, "a column stays exact");
    await act(async () => root.unmount());
    host.remove();
  });
});

});

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
      assert.match(first.host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /—/);
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

describe("Inicio export records panel", () => {
  const bytes = new Uint8Array([80, 75, 3, 4, 0, 255]);
  const own = { space_id: "own-space", grant_id: "own-grant", name: "Taller Luna", role: "owner" as const, capabilities: ["read", "prepare", "approve"] as const, access_seen: true };
  const client = { ...own, space_id: "client-space", grant_id: "client-grant", name: "Colmado Sol", role: "accountant" as const, capabilities: ["read"] as const };
  let calls: { url: URL; init?: RequestInit }[] = [];
  let downloads: { filename: string; blob: Blob }[] = [];
  let respond: (init?: RequestInit) => Promise<Response> = async () => new Response(bytes, { headers: { "Content-Type": "application/zip" } });
  const original = { fetch: globalThis.fetch, create: URL.createObjectURL, revoke: URL.revokeObjectURL, auth: process.env.NEXT_PUBLIC_MOCK_AUTH };

  function monthEnd(month: string): string {
    const [year, monthNumber] = month.split("-").map(Number);
    return `${month}-${String(new Date(year, monthNumber, 0).getDate()).padStart(2, "0")}`;
  }

  beforeAll(() => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    URL.createObjectURL = (blob) => {
      downloads.push({ filename: "", blob: blob as Blob });
      return "blob:export";
    };
    URL.revokeObjectURL = () => undefined;
    HTMLAnchorElement.prototype.click = function click() {
      downloads.at(-1)!.filename = this.download;
    };
  });

  afterAll(async () => {
    (await import("../lib/business-grant")).setChosenGrant(null);
    globalThis.fetch = original.fetch;
    URL.createObjectURL = original.create;
    URL.revokeObjectURL = original.revoke;
    if (original.auth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = original.auth;
  });

  async function renderExport(chosen: typeof own | typeof client = own, startMonth?: string) {
    calls = [];
    downloads = [];
    respond = async () => new Response(bytes, { headers: { "Content-Type": "application/zip" } });
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("../public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("../components/business-app/BusinessWorkspace");
    const { setChosenGrant } = await import("../lib/business-grant");
    const { currentMonthKey } = await import("../lib/business-month-close");
    const ExportRecordsPanel = (await import("../components/business-app/ExportRecordsPanel")).default;
    const { useMonthCloseSource } = await import("../components/business-app/BusinessMonthClosePanel");
    function Panel({ month }: { month: string }) {
      return <ExportRecordsPanel month={month} monthClose={useMonthCloseSource()} onClose={() => undefined} />;
    }
    setChosenGrant(chosen.role === "owner" ? null : chosen.grant_id);
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    globalThis.fetch = async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname.endsWith("/business/fiscal-profile")) return Response.json({ name: "Taller Luna", tax_id: null, can_edit: false });
      calls.push({ url, init });
      if (url.pathname.endsWith("/business/exports")) return respond(init);
      const month = url.searchParams.get("month") ?? currentMonthKey();
      return Response.json({
        month,
        from: `${month}-01`,
        to: monthEnd(month),
        closed: false,
        reasons: [],
        currencies: [],
        missing_rnc: [],
        missing_ncf: [],
        cuentas_por_cobrar: [],
        cuentas_por_pagar: [],
      });
    };
    const value = {
      source: { mode: "live" },
      chosen,
    } as unknown as BusinessContextValue;
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <BusinessContext.Provider value={value}>
            <Panel month={startMonth ?? currentMonthKey()} />
          </BusinessContext.Provider>
        </I18nextProvider>,
      );
    });
    for (let i = 0; i < 20; i += 1) await act(async () => { await Promise.resolve(); });
    const panel = () => document.querySelector('[data-testid="export-records-panel"]');
    const button = () => document.querySelector<HTMLButtonElement>('[data-testid="export-download"]');
    const exports = () => calls.filter((call) => call.url.pathname.endsWith("/business/exports"));
    const segment = (key: string) => document.querySelector<HTMLButtonElement>(`[data-testid="export-period"] [data-segment="${key}"]`);
    const fiscal = () => document.querySelector('[data-testid="export-fiscal"]')?.textContent ?? "";
    const settle = async () => { for (let i = 0; i < 20; i += 1) await act(async () => { await Promise.resolve(); }); };
    return { act, host, root, panel, button, exports, segment, fiscal, settle, currentMonthKey };
  }

  for (const chosen of [own, client]) test(`Inicio export downloads the open month ZIP for ${chosen.role}`, async () => {
    const view = await renderExport(chosen);
    try {
      const button = view.button();
      assert.ok(button instanceof HTMLButtonElement);
      assert.equal(button.textContent, "Exportar");
      const month = view.currentMonthKey();
      await view.act(async () => { button.click(); });
      const sent = view.exports();
      assert.equal(sent.length, 1);
      assert.equal(sent[0].url.searchParams.get("start"), `${month}-01`);
      assert.equal(sent[0].url.searchParams.get("end"), monthEnd(month));
      assert.equal(new Headers(sent[0].init?.headers).get("X-Business-Grant"), chosen.role === "accountant" ? chosen.grant_id : null);
      assert.equal(downloads.length, 1);
      assert.equal(downloads[0].filename, `business-export-${month}-01-${monthEnd(month)}.zip`);
      assert.ok(document.body.textContent?.includes(chosen.name));
    } finally {
      await view.act(async () => view.root.unmount());
      view.host.remove();
    }
  });

  test("the download follows the month the panel opens on and the period picked in it", async () => {
    const { currentMonthKey, shiftMonthKey } = await import("../lib/business-month-close");
    const opened = shiftMonthKey(currentMonthKey(), -2);
    const view = await renderExport(own, opened);
    try {
      assert.ok(document.querySelector('[data-testid="export-custom-range"]'), "an older month opens as typed dates");
      assert.equal(view.segment("this_month")?.getAttribute("aria-checked"), "false");
      await view.act(async () => { view.button()!.click(); });
      assert.equal(view.exports().at(-1)?.url.searchParams.get("start"), `${opened}-01`);
      assert.equal(view.exports().at(-1)?.url.searchParams.get("end"), monthEnd(opened));
      const previous = shiftMonthKey(currentMonthKey(), -1);
      await view.act(async () => { view.segment("last_month")!.click(); });
      await view.settle();
      assert.equal(view.segment("last_month")?.getAttribute("aria-checked"), "true");
      await view.act(async () => { view.button()!.click(); });
      assert.equal(view.exports().at(-1)?.url.searchParams.get("start"), `${previous}-01`);
      assert.equal(view.exports().at(-1)?.url.searchParams.get("end"), monthEnd(previous));
      const year = currentMonthKey().slice(0, 4);
      await view.act(async () => { view.segment("year")!.click(); });
      await view.act(async () => { view.button()!.click(); });
      assert.equal(view.exports().at(-1)?.url.searchParams.get("start"), `${year}-01-01`);
      assert.equal(view.exports().at(-1)?.url.searchParams.get("end"), `${year}-12-31`);
    } finally {
      await view.act(async () => view.root.unmount());
      view.host.remove();
    }
  });

  test("the 606 and 607 line follows the month close and asks for a whole month", async () => {
    const view = await renderExport(own);
    try {
      await view.settle();
      const month = new Intl.DateTimeFormat("es-419", { month: "long" }).format(new Date());
      assert.match(view.fiscal(), new RegExp(`Falta cerrar ${month}`));
      await view.act(async () => { view.segment("year")!.click(); });
      assert.match(view.fiscal(), /Solo por mes completo/);
      await view.act(async () => { document.querySelector<HTMLButtonElement>('[data-testid="export-other-dates"]')!.click(); });
      assert.ok(document.querySelector('[data-testid="export-custom-range"]'));
      assert.equal(view.segment("year")?.getAttribute("aria-checked"), "false");
    } finally {
      await view.act(async () => view.root.unmount());
      view.host.remove();
    }
  });

  for (const [status, pattern] of [[403, /acceso actual/], [413, /período más corto/], [503, /No se pudo descargar/]] as const) {
    test(`Inicio export refusal ${status} keeps the Gastos error and permits retry`, async () => {
      const view = await renderExport(client);
      try {
        respond = async () => new Response(JSON.stringify({ code: "export_refused" }), { status });
        const button = view.button();
        assert.ok(button instanceof HTMLButtonElement);
        await view.act(async () => { button.click(); });
        assert.match(document.querySelector('[role="alert"]')?.textContent ?? "", pattern);
        assert.equal(downloads.length, 0);
        assert.equal(button.disabled, false);
        respond = async () => new Response(bytes, { headers: { "Content-Type": "application/zip" } });
        await view.act(async () => { button.click(); });
        assert.equal(downloads.length, 1);
        assert.equal(document.querySelector('[role="alert"]'), null);
      } finally {
        await view.act(async () => view.root.unmount());
        view.host.remove();
      }
    });
  }
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
          <BusinessMonthCloseView client={client} now={now} openDocument={openDocument} />
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
    const client: MonthCloseClient = { ...createMockMonthCloseClient({ now }), async openItems() { return openItemsFrom(documents); } };
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
    async load() { return { month: "2026-10", from: "2026-10-01", to: "2026-10-31", currency: "DOP", closed_at: null, earliest_month: null, documents }; },
    async openItems() { return openItemsFrom(documents); },
    async markCobrado() { throw new Error("no mark"); },
    async markPagado() { throw new Error("no mark"); },
    async markPendiente() { throw new Error("no undo"); },
    async closeMonth() { throw new Error("no close"); },
  });
  async function renderView(client: MonthCloseClient) {
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
      root.render(<I18nextProvider i18n={i18n}><BusinessMonthCloseView client={client} now={now} header={(switcher) => <div data-testid="inicio-greeting-row"><h2>Hola</h2>{switcher}</div>} /></I18nextProvider>);
    });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    return { act, host, close: async () => { await act(async () => root.unmount()); host.remove(); } };
  }

  test("38fr and 62fr, 24px apart: greeting beside Pendiente hoy, the checklist beside Por cobrar and Por pagar, then the month's figures as two cards on the same columns", async () => {
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
      assert.match(classes('[data-testid="month-close-checklist"]'), /@min-\[56rem\]:col-start-1 @min-\[56rem\]:row-start-2/);
      const cards = view.host.querySelector<HTMLElement>('[data-testid="month-close-cards"]')!;
      assert.match(cards.className, /@min-\[56rem\]:col-span-2 @min-\[56rem\]:grid-cols-subgrid/);
      const month = cards.querySelector('[data-testid="month-close-cards-month"]')!;
      const result = cards.querySelector<HTMLElement>('[data-testid="month-close-cards-result"]')!;
      assert.deepEqual([...month.children].map((node) => node.getAttribute("data-testid")), ["month-close-income", "month-close-expenses"]);
      assert.deepEqual([...result.children].map((node) => node.getAttribute("data-testid")), ["month-close-net", "month-close-itbis"]);
      // Twice the card's 20px padding plus the 24px between Por cobrar and Por pagar puts Neto and ITBIS on their columns.
      assert.match(result.className, /p-5/);
      assert.match(result.className, /@min-\[56rem\]:gap-x-16/);
      const order = [...view.host.querySelectorAll('[data-testid="month-close-head"], [data-testid="month-close-checklist"], [data-testid="month-close-cards"], [data-testid="month-close-money"]')].map((node) => node.getAttribute("data-testid"));
      assert.deepEqual(order, ["month-close-head", "month-close-checklist", "month-close-cards", "month-close-money"], "one column keeps today's order");
    } finally { await view.close(); }
  });

  test("while steps remain, Cerrar hides and one quiet line says how many and which month", async () => {
    const view = await renderView(clientOf([document_({ id: "inv-1", status: "pendiente" }), document_({ id: "inv-2", rnc: null, ncf: null })]));
    try {
      assert.equal(view.host.querySelector('[data-testid="month-close-close"]'), null);
      assert.equal(view.host.querySelector('[data-testid="month-close-steps-note"]')?.textContent, "Cuando termines los 2 pasos, podrás cerrar octubre.");
    } finally { await view.close(); }
    const one = await renderView(clientOf([document_({ id: "inv-1", status: "pendiente" })]));
    try {
      assert.equal(one.host.querySelector('[data-testid="month-close-steps-note"]')?.textContent, "Cuando termines el paso que falta, podrás cerrar octubre.");
    } finally { await one.close(); }
  });

  test("when the month can close, the green Cerrar appears in the line's place", async () => {
    const view = await renderView(clientOf([document_({ id: "inv-1" }), document_({ id: "rcpt-1", kind: "receipt", counterparty: "Edenorte", status: "pagado" })]));
    try {
      assert.equal(view.host.querySelector('[data-testid="month-close-steps-note"]'), null);
      const close = view.host.querySelector<HTMLButtonElement>('[data-testid="month-close-close"]')!;
      assert.equal(close.textContent, "Cerrar octubre");
      assert.equal(close.disabled, false);
      assert.match(close.className, /bg-\[var\(--cuadrao-green\)\]/);
    } finally { await view.close(); }
  });
});
