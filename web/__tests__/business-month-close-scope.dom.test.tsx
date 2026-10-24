import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createMockMonthCloseClient, openItemsFrom, type MonthCloseClient, type MonthCloseDocument } from "../lib/business-month-close";
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
        <BusinessMonthCloseView client={client} now={now} scopeKey={scopeKey} businessCurrency="DOP" review={{ count: 0, detail: null, open() {} }} />
        <ToastProbe />
      </I18nextProvider>,
    ));
    for (let index = 0; index < 5; index += 1) await act(async () => { await Promise.resolve(); });
  };
  const mark = async () => {
    const button = host.querySelector<HTMLButtonElement>('[data-document-id="inv-taller"] button[data-testid="month-close-mark-cobrado"]');
    assert.ok(button, "A pending invoice is visible");
    await act(async () => { button.click(); });
  };
  const settle = async () => { for (let index = 0; index < 5; index += 1) await act(async () => { await Promise.resolve(); }); };
  const unmount = async () => { await act(async () => root.unmount()); host.remove(); clearToasts(); };
  return { act, host, render, mark, settle, unmount };
}

test("Business A's failed mark and Retry do not remain after switching to B", async () => {
  const inner = createMockMonthCloseClient({ now: new Date(2026, 9, 18), failIds: ["inv-taller"] });
  const scopes: string[] = [];
  const client: MonthCloseClient = {
    ...inner,
    async openItems(scope) { return scope === "B" ? openItemsFrom([], "2026-10-18") : inner.openItems(scope); },
    async markCobrado(id, scope, settlement) { scopes.push(scope ?? "none"); return inner.markCobrado(id, scope, settlement); },
  };
  const view = await renderScopes(client);
  try {
    await view.render("A");
    await view.mark();
    assert.equal(view.host.querySelectorAll('[data-testid="month-close-work-problem"]').length, 1);
    await view.render("B");
    assert.equal(view.host.querySelectorAll('[data-testid="month-close-work-problem"]').length, 0);
    assert.ok(view.host.querySelector('[data-testid="month-close-nothing-open"]'), "B has no open items");
    assert.deepEqual(scopes, ["A"], "B never retries A's activity id");
  } finally { await view.unmount(); }
});

test("a late Business A success cannot publish A's counterparty toast under B", async () => {
  const inner = createMockMonthCloseClient({ now: new Date(2026, 9, 18) });
  let resolveMark!: (document: MonthCloseDocument) => void;
  const pending = new Promise<MonthCloseDocument>((resolve) => { resolveMark = resolve; });
  const scopes: string[] = [];
  const client: MonthCloseClient = {
    ...inner,
    async openItems(scope) { return scope === "B" ? openItemsFrom([], "2026-10-18") : inner.openItems(scope); },
    async markCobrado(_id, scope) { scopes.push(scope ?? "none"); return pending; },
  };
  const view = await renderScopes(client);
  try {
    await view.render("A");
    await view.mark();
    await view.render("B");
    const invoice = (await inner.openItems("A")).cuentas_por_cobrar.items.find((item) => item.id === "inv-taller");
    assert.ok(invoice);
    await view.act(async () => { resolveMark({ ...invoice, status: "cobrado" }); await pending; });
    await view.settle();
    assert.equal(view.host.querySelectorAll('[data-testid="month-close-work-problem"]').length, 0);
    assert.doesNotMatch(view.host.querySelector('[data-testid="scope-toasts"]')?.textContent ?? "", /Taller Hermanos Peña/);
    assert.deepEqual(scopes, ["A"]);
  } finally { await view.unmount(); }
});
