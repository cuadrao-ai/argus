import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, createMockMonthCloseClient, MonthCloseError, statementMissingBlocker, unmatchedCharges, type MonthCloseClient, type MonthCloseDocument, type MonthCloseSnapshot } from "../lib/business-month-close";
import type { BusinessContextValue } from "../components/business-app/BusinessWorkspace";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const now = new Date(2026, 9, 18);

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
    assert.match(host.querySelector('[data-testid="month-close-toast"]')?.textContent ?? "", /volvió al anterior/);
    assert.equal(host.querySelector('[data-testid="month-close-close"]')?.hasAttribute("disabled"), true);
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
    assert.equal(host.querySelector('[data-testid="month-close-close"]')?.hasAttribute("disabled"), true);
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
    assert.match(trigger.className, /font-display/);
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
      markCobrado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPagado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
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
      markCobrado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      markPagado: () => Promise.reject(new MonthCloseError("unavailable", "mark failed")),
      closeMonth: () => Promise.reject(new MonthCloseError("unavailable", "close failed")),
    };
    const { act, host, root } = await renderView(client);
    const empty = host.querySelector('[data-testid="month-close-empty"]');
    assert.equal(empty?.getAttribute("data-layout"), "empty");
    assert.match(empty?.textContent ?? "", /Este mes no tiene documentos/);
    assert.match(empty?.textContent ?? "", /No hay facturas ni gastos en este mes/);
    const action = host.querySelector('[data-testid="month-close-empty-action"]');
    assert.ok(action instanceof HTMLButtonElement);
    assert.match(action.className, /min-h-11/);
    assert.equal(action.textContent, "Elegir mes");
    await act(async () => root.unmount());
    host.remove();
  });

  test("overdue rows sit inside the money columns marked Vencida, and settled rows leave them", async () => {
    const { act, host, root } = await renderView(createMockMonthCloseClient({ now }));
    const receivable = host.querySelector('[data-testid="month-close-receivable"]');
    const payable = host.querySelector('[data-testid="month-close-payable"]');
    const mark = host.querySelector('[data-testid="month-close-mark-cobrado"]');
    const close = host.querySelector('[data-testid="month-close-close"]');
    assert.match(mark?.className ?? "", /min-h-11/);
    assert.match(close?.className ?? "", /min-h-11/);
    assert.equal(host.querySelector('[data-testid="month-close-state-overdue"]'), null);
    assert.equal(host.querySelector('[data-testid="month-close-state-matched"]'), null);

    const farmacia = receivable?.querySelector('[data-document-id="inv-farmacia"]');
    assert.equal(farmacia?.getAttribute("data-overdue"), "true");
    assert.match(farmacia?.textContent ?? "", /Vencida · hace 16 días/);
    assert.equal(receivable?.querySelector('[data-document-id="inv-taller"]')?.getAttribute("data-overdue"), "false");
    assert.doesNotMatch(receivable?.querySelector('[data-document-id="inv-taller"]')?.textContent ?? "", /Vencida/);
    const transporte = payable?.querySelector('[data-document-id="rcpt-transporte"]');
    assert.equal(transporte?.getAttribute("data-overdue"), "true");
    assert.match(transporte?.textContent ?? "", /Vencida · hace 13 días/);
    assert.equal(payable?.querySelector('[data-document-id="rcpt-edenorte"]')?.getAttribute("data-overdue"), "false");

    assert.equal(host.querySelector('[data-document-id="inv-colmado"]'), null);
    assert.equal(host.querySelector('[data-document-id="rcpt-ferreteria"]'), null);
    assert.match(host.querySelector('[data-testid="month-close-task-settle"]')?.textContent ?? "", /2 vencidos/);
    await act(async () => root.unmount());
    host.remove();
  });

  test("a money column shows three rows, then Ver N más and Ver menos", async () => {
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
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
      async closeMonth() { throw new Error("no close"); },
    };
    const { act, host, root } = await renderView(client);
    const column = () => host.querySelector('[data-testid="month-close-receivable"]');
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 3);
    assert.equal(column()?.querySelector('[data-document-id="d"]'), null);
    assert.match(column()?.querySelector('[data-testid="month-close-receivable-total"]')?.textContent ?? "", /RD\$ 500\.00/);
    const toggle = () => [...(column()?.querySelectorAll("button") ?? [])].find((item) => item.hasAttribute("aria-expanded"));
    assert.equal(toggle()?.textContent, "Ver 2 más");
    await act(async () => { toggle()?.click(); });
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 5);
    assert.equal(toggle()?.textContent, "Ver menos");
    await act(async () => { toggle()?.click(); });
    assert.equal(column()?.querySelectorAll('[data-testid="month-close-row"]').length, 3);
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
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
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
      markCobrado(id, scope, day) {
        marks += 1;
        return inner.markCobrado(id, scope, day);
      },
      markPagado(id, scope, day) {
        marks += 1;
        return inner.markPagado(id, scope, day);
      },
      closeMonth: (month, scope) => inner.closeMonth(month, scope),
    };
    const { act, host, root } = await renderView(client);
    const income = host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "";
    assert.match(income, /RD\$/);
    assert.match(host.textContent ?? "", /Farmacia Central/);
    await act(async () => {
      host.querySelector<HTMLButtonElement>('[data-testid="month-close-month-prev"]')?.click();
    });
    assert.equal(host.querySelector('[data-testid="month-close-income"]')?.textContent, income);
    assert.match(host.textContent ?? "", /Farmacia Central/);
    assert.equal(host.textContent?.includes("Panadería Luna"), false);
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
    assert.match(host.textContent ?? "", /Panadería Luna/);
    assert.equal(host.textContent?.includes("Farmacia Central"), false);
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
    assert.equal(cobrado.textContent, "Marcar cobrado");
    assert.equal(pagado.textContent, "Marcar pagado");
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
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
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
      async markCobrado() { throw new Error("no mark"); },
      async markPagado() { throw new Error("no mark"); },
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
    const client = createHttpMonthCloseClient(async () => ({
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
    assert.match(host.querySelector('[data-testid="month-close-receivable-empty"]')?.textContent ?? "", /Nada por cobrar/);
    assert.match(host.querySelector('[data-testid="month-close-payable-empty"]')?.textContent ?? "", /Nada por pagar/);
    assert.match(host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /RD\$ 4,000\.00/);
    assert.equal(host.querySelector('[data-testid="month-close-empty"]'), null);
    assert.equal(host.textContent?.includes("Este mes no tiene documentos"), false);
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("foreign currency lines", () => {
  test("a USD line renders as US$, an EUR line renders as euro, and the DOP cards leave both out", async () => {
    const client = createHttpMonthCloseClient(async () => ({
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
      cuentas_por_cobrar: [{
        activity_id: "act-usd",
        document_kind: "invoice",
        currency: "USD",
        occurred_on: "2026-10-06",
        total_minor: 5000,
        before_itbis_minor: 5000,
        itbis_minor: null,
        status: "pendiente",
      }, {
        activity_id: "act-dop",
        document_kind: "invoice",
        currency: "DOP",
        occurred_on: "2026-10-04",
        total_minor: 118000,
        before_itbis_minor: 100000,
        itbis_minor: 18000,
        status: "pendiente",
      }],
      cuentas_por_pagar: [{
        activity_id: "act-eur",
        document_kind: "receipt",
        currency: "EUR",
        occurred_on: "2026-10-07",
        total_minor: 2000,
        before_itbis_minor: 2000,
        itbis_minor: null,
        status: "pendiente",
      }],
    }));
    const { act, host, root } = await renderView(client);
    const usd = host.querySelector('[data-document-id="act-usd"]');
    const eur = host.querySelector('[data-document-id="act-eur"]');
    assert.match(usd?.textContent ?? "", /US\$ 50\.00/);
    assert.match(eur?.textContent ?? "", /€ 20\.00/);
    assert.match(host.querySelector('[data-document-id="act-dop"]')?.textContent ?? "", /RD\$ 1,180\.00/);
    assert.match(host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /RD\$ 1,000\.00/);
    assert.equal(host.querySelector('[data-testid="month-close-income"]')?.textContent?.includes("US$"), false);
    assert.match(host.querySelector('[data-testid="month-close-receivable-total"]')?.textContent ?? "", /RD\$ 1,180\.00/);
    assert.equal(host.querySelector('[data-testid="month-close-receivable-total"]')?.textContent?.includes("1,230"), false);
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
    const Panel = (await import("../components/business-app/BusinessMonthClosePanel")).default;
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const value = {
      source: { mode },
      chosen: { grant_id: "own-grant", capabilities: ["approve"], role: "owner", name: "Taller" },
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
      if (url.includes("/business/month-close?") && calls.length === 1) {
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
      assert.match(failed.host.querySelector('[data-testid="month-close-error"]')?.textContent ?? "", /No pudimos cargar el mes/);
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
    const Panel = (await import("../components/business-app/ExportRecordsPanel")).default;
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
            <Panel month={startMonth ?? currentMonthKey()} onClose={() => undefined} />
          </BusinessContext.Provider>
        </I18nextProvider>,
      );
    });
    for (let i = 0; i < 20; i += 1) await act(async () => { await Promise.resolve(); });
    const panel = () => document.querySelector('[data-testid="export-records-panel"]');
    const button = () => [...(panel()?.querySelectorAll("button") ?? [])].find((item) => item.textContent?.includes("Descargar CSV, Excel y originales"));
    const exports = () => calls.filter((call) => call.url.pathname.endsWith("/business/exports"));
    return { act, host, root, panel, button, exports, currentMonthKey };
  }

  for (const chosen of [own, client]) test(`Inicio export downloads the open month ZIP for ${chosen.role}`, async () => {
    const view = await renderExport(chosen);
    try {
      const button = view.button();
      assert.ok(button instanceof HTMLButtonElement);
      assert.ok(view.panel()?.contains(button));
      const month = view.currentMonthKey();
      await view.act(async () => { button.click(); });
      const sent = view.exports();
      assert.equal(sent.length, 1);
      assert.equal(sent[0].url.searchParams.get("start"), `${month}-01`);
      assert.equal(sent[0].url.searchParams.get("end"), monthEnd(month));
      assert.equal(new Headers(sent[0].init?.headers).get("X-Business-Grant"), chosen.role === "accountant" ? chosen.grant_id : null);
      assert.equal(downloads.length, 1);
      assert.equal(downloads[0].filename, `business-export-${month}-01-${monthEnd(month)}.zip`);
      assert.ok(view.panel()?.textContent?.includes(chosen.name));
    } finally {
      await view.act(async () => view.root.unmount());
      view.host.remove();
    }
  });

  test("the download follows the month the panel opens on and the month picked in it", async () => {
    const { currentMonthKey, shiftMonthKey } = await import("../lib/business-month-close");
    const opened = shiftMonthKey(currentMonthKey(), -2);
    const view = await renderExport(own, opened);
    try {
      const previous = shiftMonthKey(opened, -1);
      const first = view.button();
      assert.ok(first instanceof HTMLButtonElement);
      await view.act(async () => { first.click(); });
      assert.equal(view.exports().at(-1)?.url.searchParams.get("start"), `${opened}-01`);
      assert.equal(view.exports().at(-1)?.url.searchParams.get("end"), monthEnd(opened));
      const control = view.panel()?.querySelector('[data-testid="month-close-month-prev"]');
      assert.ok(control instanceof HTMLButtonElement);
      await view.act(async () => { control.click(); });
      for (let i = 0; i < 20; i += 1) await view.act(async () => { await Promise.resolve(); });
      const button = view.button();
      assert.ok(button instanceof HTMLButtonElement);
      await view.act(async () => { button.click(); });
      const sent = view.exports();
      assert.equal(sent.at(-1)?.url.searchParams.get("start"), `${previous}-01`);
      assert.equal(sent.at(-1)?.url.searchParams.get("end"), monthEnd(previous));
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
        assert.match(view.panel()?.querySelector('[role="alert"]')?.textContent ?? "", pattern);
        assert.equal(downloads.length, 0);
        assert.equal(button.disabled, false);
        respond = async () => new Response(bytes, { headers: { "Content-Type": "application/zip" } });
        await view.act(async () => { button.click(); });
        assert.equal(downloads.length, 1);
        assert.equal(view.panel()?.querySelector('[role="alert"]'), null);
      } finally {
        await view.act(async () => view.root.unmount());
        view.host.remove();
      }
    });
  }
});
