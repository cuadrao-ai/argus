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
    const row = () => host.querySelector('[data-document-id="inv-taller"]');
    assert.equal(row()?.getAttribute("data-status"), "pendiente");
    const button = host.querySelector('[data-document-id="inv-taller"] [data-testid="month-close-mark-cobrado"]');
    assert.ok(button instanceof HTMLButtonElement);
    await act(async () => {
      button.click();
      await Promise.resolve();
    });
    assert.equal(row()?.getAttribute("data-status"), "cobrado");
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60));
    });
    assert.equal(row()?.getAttribute("data-status"), "pendiente");
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
    assert.equal(host.querySelectorAll('[data-testid="month-close-loading-row"]').length, 6);
    assert.match(host.querySelector('[data-testid="month-close-loading-row"]')?.className ?? "", /min-h-11/);
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

  test("Vencidas filters to overdue rows, and settled rows use the matched bar", async () => {
    const { act, host, root } = await renderView(createMockMonthCloseClient({ now }));
    const overdueCard = host.querySelector('[data-testid="month-close-state-overdue"]');
    const matchedCard = host.querySelector('[data-testid="month-close-state-matched"]');
    const mark = host.querySelector('[data-testid="month-close-mark-cobrado"]');
    const close = host.querySelector('[data-testid="month-close-close"]');
    assert.ok(overdueCard instanceof HTMLButtonElement);
    assert.match(overdueCard.className, /min-h-11/);
    assert.match(mark?.className ?? "", /min-h-11/);
    assert.match(close?.className ?? "", /min-h-11/);
    assert.equal(host.querySelector('[data-document-id="inv-colmado"]')?.getAttribute("data-layout"), "matched");
    assert.equal(host.querySelector('[data-document-id="inv-farmacia"]')?.getAttribute("data-overdue"), "true");
    assert.equal(host.querySelector('[data-document-id="inv-taller"]')?.getAttribute("data-overdue"), "false");

    await act(async () => {
      overdueCard.click();
    });
    assert.equal(host.querySelector('[data-testid="month-close-overdue"]')?.getAttribute("data-layout"), "overdue");
    assert.ok(host.querySelector('[data-document-id="inv-farmacia"]'));
    assert.equal(host.querySelector('[data-document-id="inv-taller"]'), null);
    assert.equal(host.querySelector('[data-document-id="inv-farmacia"] [data-testid="month-close-status"]')?.textContent, "Vencida");

    await act(async () => {
      (matchedCard as HTMLButtonElement).click();
    });
    assert.equal(host.querySelector('[data-testid="month-close-matched"]')?.getAttribute("data-layout"), "matched");
    assert.equal(host.querySelector('[data-document-id="inv-colmado"]')?.getAttribute("data-layout"), "matched");
    assert.equal(host.querySelector('[data-document-id="inv-farmacia"]'), null);
    await act(async () => root.unmount());
    host.remove();
  });

  test("unknown figures say Pendiente and never a zero, and unrendered blockers stay off the screen", async () => {
    const snapshot: MonthCloseSnapshot = {
      month: "2026-10",
      from: "2026-10-01",
      to: "2026-10-31",
      currency: "DOP",
      closed_at: null,
      earliest_month: null,
      documents: [],
      figures: { income_before_itbis: null, expense_before_itbis: null, net_before_itbis: null, itbis_owed: null },
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
      assert.match(card?.textContent ?? "", /Pendiente/);
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
    assert.equal(host.textContent?.includes("Clínica Aurora"), false);
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
    assert.match(host.textContent ?? "", /Clínica Aurora/);
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

function statusCell(count: number, beforeItbisMinor: number) {
  return { count, before_itbis_minor: beforeItbisMinor };
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
    const filing = host.querySelector('[data-testid="month-close-filing"]');
    assert.equal(filing?.querySelector('[data-testid="month-close-filing-status"]')?.textContent, "Pendiente");
    assert.equal(
      filing?.querySelector('[data-testid="month-close-filing-line"]')?.textContent,
      "Ya tienes todo para el 606 y el 607. Cierra el mes cuando termines de marcar lo cobrado y lo pagado.",
    );
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
    assert.equal(host.querySelector('[data-testid="month-close-filing"]'), null);
    assert.equal(
      host.textContent?.includes("Ya tienes todo para el 606 y el 607. Cierra el mes cuando termines de marcar lo cobrado y lo pagado."),
      false,
    );
    await act(async () => root.unmount());
    host.remove();
  });

  test("an incomplete month shows neither the filing line nor a closed label", async () => {
    const client = createMockMonthCloseClient({ now });
    const { act, host, root } = await renderView(client);
    assert.equal(host.querySelector('[data-testid="month-close-filing"]'), null);
    assert.equal(
      host.textContent?.includes("Ya tienes todo para el 606 y el 607. Cierra el mes cuando termines de marcar lo cobrado y lo pagado."),
      false,
    );
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

  test("a negative ITBIS balance shows the credit label, the absolute amount, and the exact line", async () => {
    const { act, host, root } = await renderView(clientFor("-1250.00"));
    const card = host.querySelector('[data-testid="month-close-itbis"]');
    assert.equal(card?.querySelector("h4")?.textContent, "Saldo a favor de ITBIS");
    assert.equal(card?.querySelector("p")?.textContent, "RD$ 1,250.00");
    assert.equal(/-/.test(card?.querySelector("p")?.textContent ?? "missing"), false);
    assert.equal(
      card?.querySelector("p:last-of-type")?.textContent,
      "Este mes pagaste más ITBIS del que cobraste. Normalmente esa diferencia queda como saldo a favor para los próximos meses; tu contador lo confirma en el IT-1.",
    );
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
    assert.equal(card?.querySelector("h4")?.textContent, "ITBIS a pagar");
    assert.equal(card?.querySelector("p")?.textContent, "RD$ 1,250.00");
    assert.equal(card?.querySelector("p:last-of-type")?.textContent, "ITBIS de las facturas menos ITBIS de los gastos.");
    assert.equal(card?.textContent?.includes("Saldo a favor de ITBIS"), false);
    await act(async () => root.unmount());
    host.remove();
  });

  test("a zero ITBIS balance keeps ITBIS a pagar", async () => {
    const { act, host, root } = await renderView(clientFor("0.00"));
    const card = host.querySelector('[data-testid="month-close-itbis"]');
    assert.equal(card?.querySelector("h4")?.textContent, "ITBIS a pagar");
    assert.equal(card?.querySelector("p")?.textContent, "RD$ 0.00");
    assert.equal(card?.textContent?.includes("Saldo a favor de ITBIS"), false);
    assert.equal(card?.textContent?.includes("Este mes pagaste más ITBIS"), false);
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("a fully settled month", () => {
  test("collected and paid reads the settled counts, and the month is not empty", async () => {
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
    const matched = host.querySelector('[data-testid="month-close-state-matched"]');
    assert.match(matched?.textContent ?? "", /RD\$ 3,000\.00/);
    assert.match(matched?.textContent ?? "", /Cobradas y pagadas/);
    assert.match(matched?.textContent ?? "", /3 documentos/);
    assert.match(host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /RD\$ 4,000\.00/);
    assert.equal(host.querySelector('[data-testid="month-close-empty"]'), null);
    assert.equal(host.textContent?.includes("Este mes no tiene documentos"), false);
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
    currencies: [],
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
      assert.match(first.host.querySelector('[data-testid="month-close-income"]')?.textContent ?? "", /Pendiente/);
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
      assert.match(page.host.querySelector('[data-testid="month-close-sample"]')?.textContent ?? "", /Datos de muestra/);
      assert.match(page.host.textContent ?? "", /Farmacia Central/);
      assert.equal(calls.some((url) => url.includes("/business/month-close")), false);
      await page.act(async () => page.root.unmount());
      page.host.remove();
    } finally {
      globalThis.fetch = original;
    }
  });
});
