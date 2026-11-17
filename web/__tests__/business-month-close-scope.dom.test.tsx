import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createMockMonthCloseClient, openItemsFrom, type MonthCloseClient, type MonthCloseSnapshot } from "../lib/business-month-close";
import { clearToasts, useToasts } from "../components/business-app/foundation/toasts";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  clearToasts();
  await GlobalRegistrator.unregister();
});

function ToastProbe() {
  const items = useToasts();
  return <div data-testid="scope-toasts">{items.map((item) => item.text).join(" ")}</div>;
}

async function renderScopes(client: MonthCloseClient) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { createInstance } = await import("i18next");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessMonthCloseView } = await import("../components/business-app/BusinessMonthClosePanel");
  const spanish = (await import("../public/locales/es-419/common.json")).default;
  const now = new Date(2026, 9, 18);
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = async (scopeKey: "A" | "B") => {
    await act(async () => root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessMonthCloseView layout="finance" arrange={({ month, money }) => <>{month}{money}</>} settlement client={client} now={now} scopeKey={scopeKey} businessCurrency="DOP" review={{ count: 0 }} />
        <ToastProbe />
      </I18nextProvider>,
    ));
    for (let index = 0; index < 5; index += 1) await act(async () => { await Promise.resolve(); });
  };
  const settle = async () => { for (let index = 0; index < 5; index += 1) await act(async () => { await Promise.resolve(); }); };
  const unmount = async () => { await act(async () => root.unmount()); host.remove(); clearToasts(); };
  return { act, host, render, settle, unmount };
}

test("Business A's failed read and Retry do not remain after switching to B", async () => {
  const inner = createMockMonthCloseClient({ now: new Date(2026, 9, 18) });
  const scopes: string[] = [];
  const client: MonthCloseClient = {
    ...inner,
    async load(month, scope) { scopes.push(scope ?? "none"); if (scope === "A") throw new Error("offline"); return inner.load(month, scope); },
    async openItems(scope) { return scope === "B" ? openItemsFrom([], "2026-10-18") : inner.openItems(scope); },
  };
  const view = await renderScopes(client);
  try {
    await view.render("A");
    assert.equal(view.host.querySelector('[data-testid="home-month-body"]')?.getAttribute("data-state"), "error");
    assert.ok(view.host.querySelector('[role="alert"] button'));
    await view.render("B");
    assert.equal(view.host.querySelector('[data-testid="home-month-body"]')?.getAttribute("data-state"), "ready");
    assert.equal(view.host.querySelector('[role="alert"]'), null);
    assert.ok(view.host.querySelector('[data-testid="month-close-nothing-open"]'));
    assert.deepEqual(scopes, ["A", "B"]);
  } finally { await view.unmount(); }
});

test("late Business A reads cannot replace B's figures, rows or toasts", async () => {
  const inner = createMockMonthCloseClient({ now: new Date(2026, 9, 18) });
  let resolveMonth!: (snapshot: MonthCloseSnapshot) => void;
  let resolveOpen!: (items: Awaited<ReturnType<MonthCloseClient["openItems"]>>) => void;
  const client: MonthCloseClient = {
    ...inner,
    async load(month, scope) {
      if (scope === "A") return new Promise(resolve => { resolveMonth = resolve; });
      const snapshot = await inner.load(month, scope);
      return { ...snapshot, figures: snapshot.figures.map(block => ({ ...block, income_before_itbis: "42.00" })) };
    },
    async openItems(scope) { return scope === "A" ? new Promise(resolve => { resolveOpen = resolve; }) : openItemsFrom([], "2026-10-18"); },
  };
  const view = await renderScopes(client);
  try {
    await view.render("A");
    await view.render("B");
    await view.act(async () => { resolveMonth(await inner.load("2026-10", "A")); resolveOpen(await inner.openItems("A")); });
    await view.settle();
    assert.equal(view.host.querySelector('[data-testid="home-month-income"]')?.getAttribute("data-amount"), "42.00");
    assert.ok(view.host.querySelector('[data-testid="month-close-nothing-open"]'));
    assert.equal(view.host.querySelector('[data-testid="month-close-row"]'), null);
    assert.equal(view.host.querySelector('[data-testid="scope-toasts"]')?.textContent, "");
  } finally { await view.unmount(); }
});
