import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessExpense, BusinessExpenseDetail, BusinessWorkspaceInfo } from "@/lib/business-api";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// A record with no draft opens the one dossier, read only. The workspace shows one
// panel at a time here, as a phone does.
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
  { id: "exp-hosting", merchant: "Nube Hosting", amount: "24.00", currency: "DOP", category_id: "other", account_id: "acct-card", occurred_on: "2026-10-07", receipt_id: "rcpt-confirmed", draft_id: null } as BusinessExpense,
  { id: "exp-gas", merchant: "Estación Ruta 3", amount: "2100.00", currency: "DOP", category_id: "transport", account_id: "acct-ops", occurred_on: "2026-10-09", receipt_id: null, draft_id: null } as BusinessExpense,
];

async function mountWorkspace(options: { detail: BusinessExpenseDetail | (() => Promise<BusinessExpenseDetail>); list?: BusinessExpense[] }) {
  const { act, useRef, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: ReceiptReviewPanel } = await import("@/components/business-app/ReceiptReviewPanel");
  const { default: TransaccionesPanel } = await import("@/components/business-app/transacciones/TransaccionesPanel");
  const { TransaccionesSourceOverride } = await import("@/components/business-app/transacciones/useTransacciones");
  const { createRecordsTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const workspace: Pick<BusinessWorkspaceInfo, "accounts" | "records_default_currency"> = {
    accounts: [{ id: "acct-ops", nickname: "Cuenta corriente", type: "bank", currency: "DOP" }],
    records_default_currency: "DOP",
  };
  const opened: BusinessPanelState[] = [];
  let setPanelOutside: (next: BusinessPanelState) => void = () => undefined;
  let reloadOutside: () => void = () => undefined;
  function Workspace() {
    const [panel, setPanel] = useState<BusinessPanelState>({ kind: "expense", expenseId: "exp-gas" });
    const [revision, setRevision] = useState(0);
    setPanelOutside = setPanel;
    reloadOutside = () => setRevision((value) => value + 1);
    // The source is one object for the life of the workspace, as the app's is; openPanel is built inline, so
    // every re-render hands the panels a fresh one (the hazard the dossier must shrug off).
    const source = useRef({
      expense: typeof options.detail === "function" ? options.detail : async () => options.detail as BusinessExpenseDetail,
      expenses: async () => options.list ?? LIST,
      workspace: async () => workspace,
    }).current;
    const saved = useRef(createRecordsTransaccionesSource({
      expenses: source.expenses,
      ventas: async () => [],
      overview: async () => ({ from: "2026-10-01", to: "2026-10-20", today: "2026-10-20", totals: [], last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null }),
      workspace: source.workspace,
      month: async (month) => ({ month, from: `${month}-01`, to: `${month}-28`, currency: "DOP", closed_at: null, earliest_month: null, documents: [] }),
      ownerFunds: "Dinero del dueño",
    })).current;
    const value = {
      source,
      records: { workspace, overview: null },
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
          {panel.kind === "expense" ? <ReceiptReviewPanel key={panel.expenseId} target={{ kind: "expense", id: panel.expenseId }} detailsCard={panel.detailsCard} /> : <TransaccionesSourceOverride source={saved}><TransaccionesPanel /></TransaccionesSourceOverride>}
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

const dossier = (host: HTMLElement) => host.querySelector<HTMLElement>('[data-testid="business-record-review"]');
const title = (host: HTMLElement) => host.querySelector("#receipt-review-title")?.textContent ?? null;
const fact = (host: HTMLElement, row: string) => host.querySelector(`[data-fact="${row}"] [data-row-value]`)?.textContent ?? null;

describe("a record with no draft", () => {
  test("opens the one dossier, read only, with the facts the server has and nothing to act on", async () => {
    const page = await mountWorkspace({ detail: expense({}) });
    const frame = dossier(page.host)!;
    assert.ok(frame, "the v2 dossier frame");
    assert.equal(title(page.host), "Estación Ruta 3");
    assert.equal(fact(page.host, "occurred_on"), "9 Oct 2026");
    assert.equal(fact(page.host, "account"), "Cuenta corriente");
    assert.ok(fact(page.host, "amount")?.includes("2,100.00"), fact(page.host, "amount") ?? "");
    assert.deepEqual([...frame.querySelectorAll('[role="tab"]')].map((tab) => tab.textContent), ["General", "Detalles", "Historial"]);
    assert.ok(frame.querySelector('[data-tab-panel="detalles"]')?.textContent?.includes("Sin recibo adjunto"));
    assert.ok(frame.querySelector('[data-tab-panel="historial"]')?.textContent?.includes("Registrado el"));
    assert.equal(frame.querySelector('[data-testid="receipt-review-footer"]'), null, "no Aceptar, no footer");
    assert.equal(frame.querySelector('[data-testid="dossier-status"]'), null, "no pill");
    assert.deepEqual([...frame.querySelectorAll('[data-tab-panel] button, [data-tab-panel] input, [data-tab-panel] select')], [], "nothing to edit");
    assert.equal(page.host.querySelector('[data-testid="business-expense-detail"]'), null, "never the old panel");
    assert.ok(!/Revisi[oó]n\s+\d/i.test(page.host.textContent ?? ""), "no revision number");
    assert.ok(!page.host.textContent?.includes("Gasto guardado"));
    assert.deepEqual(page.opened, []);
    await page.act(async () => page.root.unmount());
  });

  test("a record the money read gives no time for has no Historial tab", async () => {
    const page = await mountWorkspace({ detail: expense({ recorded_at: null }) });
    assert.deepEqual([...dossier(page.host)!.querySelectorAll('[role="tab"]')].map((tab) => tab.textContent), ["General", "Detalles"]);
    await page.act(async () => page.root.unmount());
  });

  for (const [link, target] of [
    [{ receipt_id: "linked-receipt" }, { kind: "receipt", receiptId: "linked-receipt" }],
    [{ draft_id: "linked-draft" }, { kind: "draft", draftId: "linked-draft" }],
  ] as const) test(`an expense link keeps the supporting files destination when resolved to its ${target.kind}`, async () => {
    let pass = false;
    const page = await mountWorkspace({ detail: async () => expense(pass ? link : {}) });
    pass = true;
    await page.setPanel({ kind: "transactions" });
    await page.setPanel({ kind: "expense", expenseId: "exp-gas", detailsCard: "support" });
    await page.settle();
    assert.deepEqual(page.opened, [{ ...target, list: "transactions", detailsCard: "support" }]);
    await page.act(async () => page.root.unmount());
  });

  test("shows its Tipo de gasto as Registros does, and no Categoría", async () => {
    const services = { code: "02", label: "Gastos por trabajos, suministros y servicios" };
    const cases: [BusinessExpenseDetail["dgii_606"], string][] = [
      [{ expense_type: services, payment_form: null }, services.label],
      [{ expense_type: null, payment_form: null }, "Falta"],
      [null, "No aplica"],
    ];
    for (const [dgii_606, word] of cases) {
      const page = await mountWorkspace({ detail: expense({ dgii_606 }) });
      assert.equal(page.host.querySelector('[data-fact="category"]'), null);
      const answer = page.host.querySelector('[data-fact="expense_type"] [data-row-value]');
      assert.ok(answer?.textContent?.includes(word) || answer?.innerHTML.includes(word), `${word} in ${answer?.innerHTML}`);
      await page.act(async () => page.root.unmount());
    }
  });

  test("the way back returns to Registros and names the record, so its row takes focus", async () => {
    const page = await mountWorkspace({ detail: expense({}) });
    const back = dossier(page.host)!.querySelector("header button")!;
    await page.act(async () => { (back as HTMLButtonElement).click(); });
    assert.deepEqual(page.opened, [{ kind: "transactions", cameFrom: { kind: "expense", expenseId: "exp-gas" } }]);
    await page.settle();
    assert.equal(dossier(page.host), null, "the dossier is gone");
    const row = page.host.querySelector<HTMLElement>('[data-record-id="exp-gas"]');
    assert.ok(row, "Registros rendered the row");
    assert.ok(document.activeElement === row || document.activeElement === row.querySelector("button"), "the row that opened the record has focus");
    await page.act(async () => page.root.unmount());
  });

  test("a failed load offers Reintentar, which fetches again", async () => {
    let calls = 0;
    const page = await mountWorkspace({ detail: async () => { calls += 1; if (calls === 1) throw new Error("boom"); return expense({}); } });
    const card = page.host.querySelector('[data-testid="receipt-load-error"]')!;
    assert.ok(card.querySelector('[role="alert"]')?.textContent?.includes("No pudimos actualizar."));
    const retry = [...card.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await page.act(async () => { retry.click(); });
    await page.settle();
    assert.equal(calls, 2);
    assert.equal(title(page.host), "Estación Ruta 3");
    await page.act(async () => page.root.unmount());
  });

  test("a workspace re-render that hands out a new openPanel does not fetch the record again", async () => {
    let calls = 0;
    const page = await mountWorkspace({ detail: async () => { calls += 1; return expense({}); } });
    assert.equal(calls, 1);
    await page.reload();
    await page.settle();
    await page.reload();
    await page.settle();
    assert.equal(calls, 1, "the record was asked for once");
    assert.equal(title(page.host), "Estación Ruta 3");
    await page.act(async () => page.root.unmount());
  });

  test("an expense that names a receipt opens that receipt's record instead; one from a draft opens the draft", async () => {
    const withReceipt = await mountWorkspace({ detail: expense({ id: "exp-hosting", receipt_id: "rcpt-confirmed" }) });
    assert.deepEqual(withReceipt.opened, [{ kind: "receipt", receiptId: "rcpt-confirmed", list: "transactions" }]);
    assert.equal(dossier(withReceipt.host), null, "no read-only frame for a record that has a receipt");
    await withReceipt.act(async () => withReceipt.root.unmount());
    const fromDraft = await mountWorkspace({ detail: expense({ id: "exp-note", draft_id: "draft-7" }) });
    assert.deepEqual(fromDraft.opened, [{ kind: "draft", draftId: "draft-7", list: "transactions" }]);
    await fromDraft.act(async () => fromDraft.root.unmount());
  });
});
