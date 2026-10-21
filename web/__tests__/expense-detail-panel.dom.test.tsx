import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessExpense, BusinessExpenseDetail } from "@/lib/business-api";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// A real DOM: the workspace shows one panel at a time, so closing the detail
// unmounts it and mounts Transacciones' saved records, as the app does.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const expense = (over: Partial<BusinessExpenseDetail>): BusinessExpenseDetail =>
  ({ id: "exp-gas", merchant: "Estación Ruta 3", amount: "2100.00", currency: "DOP", category_id: "transport", account_id: "acct-ops", occurred_on: "2026-10-09", receipt_id: null, draft_id: null, recorded_at: "2026-10-09T15:00:00Z", revision: 1, ...over } as BusinessExpenseDetail);

const LIST: BusinessExpense[] = [
  { id: "exp-hosting", merchant: "Nube Hosting", amount: "24.00", currency: "USD", category_id: "other", account_id: "acct-card", occurred_on: "2026-10-07", receipt_id: "rcpt-confirmed", draft_id: null } as BusinessExpense,
  { id: "exp-gas", merchant: "Estación Ruta 3", amount: "2100.00", currency: "DOP", category_id: "transport", account_id: "acct-ops", occurred_on: "2026-10-09", receipt_id: null, draft_id: null } as BusinessExpense,
];

async function mountWorkspace(options: { detail: BusinessExpenseDetail | (() => Promise<BusinessExpenseDetail>); list?: BusinessExpense[] }) {
  const { act, useRef, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: ExpenseDetailPanel } = await import("@/components/business-app/ExpenseDetailPanel");
  const { default: TransaccionesPanel } = await import("@/components/business-app/transacciones/TransaccionesPanel");
  const { TransaccionesSourceOverride } = await import("@/components/business-app/transacciones/useTransacciones");
  const { createRecordsTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const opened: BusinessPanelState[] = [];
  let setPanelOutside: (next: BusinessPanelState) => void = () => undefined;
  let reloadOutside: () => void = () => undefined;
  function Workspace() {
    const [panel, setPanel] = useState<BusinessPanelState>({ kind: "expense", expenseId: "exp-gas" });
    const [revision, setRevision] = useState(0);
    setPanelOutside = setPanel;
    reloadOutside = () => setRevision((value) => value + 1);
    // The source is one object for the life of the workspace, as the app's is; openPanel is built inline, so
    // every re-render hands the panels a fresh one (the hazard the detail panel must shrug off).
    const source = useRef({
      expense: typeof options.detail === "function" ? options.detail : async () => options.detail as BusinessExpenseDetail,
      expenses: async () => options.list ?? LIST,
    }).current;
    const saved = useRef(createRecordsTransaccionesSource({
      expenses: source.expenses,
      overview: async () => ({ from: "2026-10-01", to: "2026-10-20", today: "2026-10-20", totals: [], last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null }),
      workspace: async () => ({ accounts: [] }),
      month: async (month) => ({ month, from: `${month}-01`, to: `${month}-28`, currency: "DOP", closed_at: null, earliest_month: null, documents: [] }),
      ownerFunds: "Dinero del dueño",
    })).current;
    const value = {
      source,
      records: { workspace: { accounts: [{ id: "acct-ops", nickname: "Cuenta corriente", type: "bank", currency: "DOP" }] }, overview: null },
      revision,
      period: { key: "this_month", from: "2026-10-01", to: null },
      setPeriod: () => undefined,
      panel,
      openPanel: (next: BusinessPanelState) => { opened.push(next); setPanel(next); },
      actions: { create: [] },
    } as unknown as BusinessContextValue;
    return (
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={value}>
          {panel.kind === "expense" ? <ExpenseDetailPanel expenseId={panel.expenseId} /> : <TransaccionesSourceOverride source={saved}><TransaccionesPanel /></TransaccionesSourceOverride>}
        </BusinessContext.Provider>
      </I18nextProvider>
    );
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<Workspace />); });
  const settle = () => act(async () => { for (let tick = 0; tick < 8; tick += 1) await Promise.resolve(); });
  await settle();
  return { act, root, host, opened, settle, setPanel: (next: BusinessPanelState) => act(async () => setPanelOutside(next)), reload: () => act(async () => reloadOutside()) };
}

describe("the expense detail panel", () => {
  test("an expense entered by hand shows its detail, labelled by a title that exists, takes focus, and says no receipt is attached", async () => {
    const page = await mountWorkspace({ detail: expense({}) });
    const section = page.host.querySelector('[data-testid="business-expense-detail"]')!;
    assert.equal(section.getAttribute("aria-labelledby"), "expense-detail-title");
    assert.equal(page.host.querySelector("#expense-detail-title")!.textContent, "Estación Ruta 3");
    assert.equal(document.activeElement, section);
    assert.ok(page.host.textContent?.includes("Sin recibo adjunto"));
    assert.deepEqual(page.opened, []);
    await page.act(async () => page.root.unmount());
  });

  test("closing returns to Transacciones naming the expense; after the real remount the list focuses that row", async () => {
    const page = await mountWorkspace({ detail: expense({}) });
    const back = page.host.querySelector('[data-testid="business-expense-detail"] button')!;
    await page.act(async () => { (back as HTMLButtonElement).click(); });
    assert.deepEqual(page.opened, [{ kind: "transactions", expenseId: "exp-gas" }]);
    await page.settle();
    assert.equal(page.host.querySelector('[data-testid="business-expense-detail"]'), null, "the detail panel is gone");
    const row = page.host.querySelector('[data-record-id="exp-gas"]');
    assert.ok(row, "Transacciones rendered the row");
    assert.equal(document.activeElement, row);
    await page.act(async () => page.root.unmount());
  });

  test("focus returns to the row once per arrival: a background reload re-renders the list without taking focus back", async () => {
    const page = await mountWorkspace({ detail: expense({}) });
    const back = page.host.querySelector('[data-testid="business-expense-detail"] button')!;
    await page.act(async () => { (back as HTMLButtonElement).click(); });
    await page.settle();
    const row = page.host.querySelector('[data-record-id="exp-gas"]') as HTMLElement;
    assert.equal(document.activeElement, row);
    // The person moves on to another row.
    const other = page.host.querySelector('[data-record-id="exp-hosting"]') as HTMLElement;
    await page.act(async () => { other.focus(); });
    assert.equal(document.activeElement, other);
    // Two background reloads re-fetch and re-render the list; focus stays where the person put it.
    await page.reload();
    await page.settle();
    await page.reload();
    await page.settle();
    assert.equal(document.activeElement, other);
    assert.ok(page.host.querySelector('[data-record-id="exp-gas"]'), "the list is still there");
    await page.act(async () => page.root.unmount());
  });

  test("a row outside the listed period cannot take focus, so the screen itself does (the documented fallback)", async () => {
    const page = await mountWorkspace({ detail: expense({}), list: [LIST[0]] });
    const back = page.host.querySelector('[data-testid="business-expense-detail"] button')!;
    await page.act(async () => { (back as HTMLButtonElement).click(); });
    await page.settle();
    assert.equal(document.activeElement, page.host.querySelector('[data-testid="transacciones"]'));
    await page.act(async () => page.root.unmount());
  });

  test("while loading, the labelled element already exists with the panel's title; a failed load offers Reintentar, which fetches again", async () => {
    let calls = 0;
    const page = await mountWorkspace({ detail: async () => { calls += 1; if (calls === 1) throw new Error("boom"); return expense({}); } });
    assert.ok(page.host.textContent?.includes("No pudimos abrir este gasto"));
    assert.equal(page.host.querySelector("#expense-detail-title")?.textContent, "Gasto guardado");
    const retry = page.host.querySelector('[data-testid="expense-detail-retry"]') as HTMLButtonElement;
    assert.equal(retry.textContent, "Reintentar");
    await page.act(async () => { retry.click(); });
    await page.settle();
    assert.equal(calls, 2);
    assert.equal(page.host.querySelector("#expense-detail-title")?.textContent, "Estación Ruta 3");
    await page.act(async () => page.root.unmount());
  });

  test("a workspace re-render that hands out a new openPanel does not fetch the expense again", async () => {
    let calls = 0;
    const page = await mountWorkspace({ detail: async () => { calls += 1; return expense({}); } });
    assert.equal(calls, 1);
    // Each reload re-renders the provider with a fresh openPanel (as this harness builds it inline).
    await page.reload();
    await page.settle();
    await page.reload();
    await page.settle();
    assert.equal(calls, 1, "the record was asked for once");
    assert.equal(page.host.querySelector("#expense-detail-title")?.textContent, "Estación Ruta 3");
    await page.act(async () => page.root.unmount());
  });

  test("an expense that names a receipt opens that receipt's record instead; one from a draft opens the draft", async () => {
    const withReceipt = await mountWorkspace({ detail: expense({ id: "exp-hosting", receipt_id: "rcpt-confirmed" }) });
    assert.deepEqual(withReceipt.opened, [{ kind: "receipt", receiptId: "rcpt-confirmed", list: "transactions" }]);
    assert.ok(!withReceipt.host.querySelector('[data-testid="business-expense-detail"]')?.textContent?.includes("Sin recibo adjunto"));
    await withReceipt.act(async () => withReceipt.root.unmount());
    const fromDraft = await mountWorkspace({ detail: expense({ id: "exp-note", draft_id: "draft-7" }) });
    assert.deepEqual(fromDraft.opened, [{ kind: "draft", draftId: "draft-7", list: "transactions" }]);
    await fromDraft.act(async () => fromDraft.root.unmount());
  });
});
