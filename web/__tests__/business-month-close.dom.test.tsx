import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createMockMonthCloseClient, MonthCloseError, statementMissingBlocker, unmatchedCharges, type MonthCloseClient, type MonthCloseSnapshot } from "../lib/business-month-close";

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
});
