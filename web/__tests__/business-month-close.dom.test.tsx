import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createHttpMonthCloseClient, createMockMonthCloseClient, MonthCloseError, monthCloseFiguresFrom, openItemsFrom, statementMissingBlocker, unmatchedCharges, type MonthCloseClient, type MonthCloseDocument, type MonthCloseSnapshot } from "../lib/business-month-close";

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

  test("a document igualada with the bank says the bank match settled it, offers no Reintentar, and leaves Pendiente hoy", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("../public/locales/es-419/common.json")).default;
    const { BusinessMonthCloseView } = await import("../components/business-app/BusinessMonthClosePanel");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const inner = createMockMonthCloseClient({ now });
    // The server: Transacciones already matched this invoice to a deposit, which wrote cobrado; the PATCH is refused.
    const matched = createHttpMonthCloseClient(async () => { throw Object.assign(new Error("matched"), { status: 409, code: "business_document_matched" }); });
    const client: MonthCloseClient = {
      ...inner,
      async markCobrado(documentId, scope, settledOn) {
        await inner.markCobrado(documentId, scope, settledOn);
        return matched.markCobrado(documentId, scope, settledOn);
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
    const button = host.querySelector('[data-document-id="inv-taller"] [data-testid="month-close-mark-cobrado"]');
    assert.ok(button instanceof HTMLButtonElement);
    await act(async () => {
      button.click();
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    const problem = host.querySelector('[data-testid="month-close-work-problem"]');
    assert.equal(problem?.getAttribute("role"), "alert");
    assert.match(problem?.textContent ?? "", /ya está igualada con un depósito del banco/);
    assert.match(problem?.textContent ?? "", /desiguálala en Transacciones/);
    assert.doesNotMatch(problem?.textContent ?? "", /volvió al anterior/);
    assert.equal(problem?.querySelectorAll("button").length, 0, "trying again cannot work, so nothing offers it");
    assert.equal(host.querySelector('[data-testid="month-close-receivable"] [data-document-id="inv-taller"]'), null, "the reread shows it settled");
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
  async function renderView(client: MonthCloseClient, businessCurrency: string | null = null) {
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
          <BusinessMonthCloseView client={client} now={now} businessCurrency={businessCurrency} />
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
        return { month, from: `${month}-01`, to: `${month}-31`, closed_at: null, earliest_month: null, documents: [], figures: [] };
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
      closed_at: null,
      earliest_month: null,
      documents: [invoice("a", 20), invoice("b", 21), invoice("c", 22), invoice("d", 23), invoice("e", 24)],
      figures: [],
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

  test("unknown figures say a short dash and never a zero, and unrendered blockers stay off the screen", async () => {
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      closed_at: null,
      earliest_month: null,
      documents: [],
      figures: [{ currency: "DOP", income_before_itbis: null, expense_before_itbis: null, net_before_itbis: null, itbis_owed: null }],
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
          income_before_itbis_minor: 400000, income_before_itbis: "4000.00",
          expense_before_itbis_minor: 50000, expense_before_itbis: "500.00",
          net_result_minor: 350000, net_result: "3500.00",
          itbis_charged_minor: 72000, itbis_charged: "720.00",
          itbis_owed_minor: 18000, itbis_owed: "180.00",
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
      closed_at: "2026-10-18T15:00:00",
      closed: true,
      earliest_month: null,
      documents: [invoice, receipt],
      figures: monthCloseFiguresFrom([invoice, receipt]),
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
      closed_at: "2026-10-18T15:00:00",
      closed: true,
      earliest_month: null,
      documents: [{ ...september, id: "inv-october", occurred_on: "2026-10-04", status: "cobrado" }],
      figures: [],
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
      closed_at: null,
      earliest_month: null,
      documents: [],
      figures: [{
        currency: "DOP",
        income_before_itbis: "1000.00",
        expense_before_itbis: "2000.00",
        net_before_itbis: "-1000.00",
        itbis_owed: itbisOwed,
      }],
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
        income_before_itbis_minor: 400000, income_before_itbis: "4000.00",
        expense_before_itbis_minor: 100000, expense_before_itbis: "1000.00",
        net_result_minor: 300000, net_result: "3000.00",
        itbis_charged_minor: 72000, itbis_charged: "720.00",
        itbis_owed_minor: 18000, itbis_owed: "180.00",
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
      from: "2026-10-01",
      to: "2026-10-31",
      closed: false,
      reasons: [],
      currencies: [{
        currency: "DOP",
        income_before_itbis_minor: 100000, income_before_itbis: "1000.00",
        expense_before_itbis_minor: 0, expense_before_itbis: "0.00",
        net_result_minor: 100000, net_result: "1000.00",
        itbis_owed_minor: 1800, itbis_owed: "18.00",
      }],
      missing_rnc: [],
      missing_ncf: [],
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
    assert.match(host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /RD\$ 1,000\.00/);
    assert.equal(host.querySelector('[data-testid="month-close-income"]')?.textContent?.includes("US$"), false);
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
      currencies: [{ currency: "DOP", income_before_itbis_minor: 0, income_before_itbis: "0.00", expense_before_itbis_minor: 0, expense_before_itbis: "0.00", net_result_minor: 0, net_result: "0.00", itbis_owed_minor: 0, itbis_owed: "0.00", by_status: settledByStatus() }],
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
      async load(month) { return { month, from: `${month}-01`, to: `${month}-31`, closed_at: null, earliest_month: null, documents: [], figures: [] }; },
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
