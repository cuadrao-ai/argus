import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessExpense, BusinessExpenseDetail } from "@/lib/business-api";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// Every saved record opens the one dossier: the receipt or draft behind it. A record opened by its own id
// only names that record; it never draws a view of its own.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const expense = (over: Partial<BusinessExpenseDetail>): BusinessExpenseDetail =>
  ({ id: "exp-gas", merchant: "Estación Ruta 3", amount: "2100.00", currency: "DOP", category_id: "transport", account_id: "acct-ops", occurred_on: "2026-10-09", receipt_id: null, draft_id: null, recorded_at: "2026-10-09T15:00:00Z", revision: 1, ...over } as BusinessExpenseDetail);

/** The old record view's marks: its Comprobante card, its Montos card, and its words. */
function oldRecordView(host: HTMLElement): string[] {
  const text = host.textContent ?? "";
  return [
    host.querySelector('[data-testid="record-facts-comprobante"]') ? "Comprobante card" : null,
    host.querySelector('[data-testid="record-facts-montos"]') ? "Montos card" : null,
    /Pagado desde|Sin recibo adjunto|Registrado el|Guardado como un gasto|Ver gastos|Gasto guardado/.exec(text)?.[0] ?? null,
  ].filter((mark): mark is string => mark !== null);
}

/** A record opened by its id, in a workspace that shows one panel at a time, as a phone does. */
async function openById(detail: () => Promise<BusinessExpenseDetail>) {
  const { act, useRef, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: ReceiptReviewPanel } = await import("@/components/business-app/ReceiptReviewPanel");
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
    // One source for the life of the workspace, as the app's is; openPanel is built inline, so every re-render
    // hands the panel a fresh one.
    const source = useRef({ expense: detail }).current;
    const value = {
      source,
      records: { workspace: { accounts: [] }, overview: null },
      revision,
      panel,
      openPanel: (next: BusinessPanelState) => { opened.push(next); setPanel(next); },
      actions: { create: [] },
    } as unknown as BusinessContextValue;
    return (
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={value}>
          {panel.kind === "expense" ? <ReceiptReviewPanel key={panel.expenseId} target={{ kind: "expense", id: panel.expenseId }} detailsCard={panel.detailsCard} /> : <p data-testid="elsewhere">{panel.kind}</p>}
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
  return {
    act, host, opened, settle,
    setPanel: (next: BusinessPanelState) => act(async () => setPanelOutside(next)),
    reload: () => act(async () => reloadOutside()),
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

describe("a record opened by its own id", () => {
  test("from a receipt opens that receipt's dossier; from a draft, the draft's", async () => {
    for (const [link, target] of [
      [{ receipt_id: "rcpt-confirmed" }, { kind: "receipt", receiptId: "rcpt-confirmed", list: "transactions" }],
      [{ draft_id: "draft-7" }, { kind: "draft", draftId: "draft-7", list: "transactions" }],
      [{ receipt_id: "rcpt-confirmed", draft_id: "draft-7" }, { kind: "receipt", receiptId: "rcpt-confirmed", list: "transactions" }],
    ] as const) {
      const page = await openById(async () => expense(link));
      assert.deepEqual(page.opened, [target]);
      assert.deepEqual(oldRecordView(page.host), []);
      await page.close();
    }
  });

  test("with neither a receipt nor a draft has no dossier: it closes onto Registros and never draws the old record view", async () => {
    const page = await openById(async () => expense({}));
    assert.deepEqual(page.opened, [{ kind: "transactions" }]);
    assert.equal(page.host.querySelector('[data-testid="business-record-review"]'), null, "no record frame of its own");
    assert.deepEqual(oldRecordView(page.host), []);
    await page.close();
  });

  for (const [link, target] of [
    [{ receipt_id: "linked-receipt" }, { kind: "receipt", receiptId: "linked-receipt" }],
    [{ draft_id: "linked-draft" }, { kind: "draft", draftId: "linked-draft" }],
  ] as const) test(`keeps the supporting files destination when resolved to its ${target.kind}`, async () => {
    const page = await openById(async () => expense(link));
    page.opened.length = 0;
    await page.setPanel({ kind: "transactions" });
    await page.setPanel({ kind: "expense", expenseId: "exp-gas", detailsCard: "support" });
    await page.settle();
    assert.deepEqual(page.opened, [{ ...target, list: "transactions", detailsCard: "support" }]);
    await page.close();
  });

  test("a re-render that hands out a new openPanel while it asks does not ask again", async () => {
    let calls = 0;
    const page = await openById(() => { calls += 1; return new Promise<BusinessExpenseDetail>(() => undefined); });
    await page.reload();
    await page.settle();
    await page.reload();
    await page.settle();
    assert.equal(calls, 1, "the record was asked for once");
    assert.deepEqual(oldRecordView(page.host), []);
    await page.close();
  });

  test("a failed load offers Reintentar, which asks again and opens the record behind it", async () => {
    let calls = 0;
    const page = await openById(async () => { calls += 1; if (calls === 1) throw new Error("boom"); return expense({ draft_id: "draft-7" }); });
    const card = page.host.querySelector('[data-testid="receipt-load-error"]')!;
    assert.ok(card.querySelector('[role="alert"]')?.textContent?.includes("No pudimos actualizar."));
    const retry = [...card.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await page.act(async () => { retry.click(); });
    await page.settle();
    assert.equal(calls, 2);
    assert.deepEqual(page.opened, [{ kind: "draft", draftId: "draft-7", list: "transactions" }]);
    await page.close();
  });
});

describe("the sample's saved records", () => {
  test("each opens its dossier, with its facts, from Registros' own id", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
    const { setChosenGrant } = await import("@/lib/business-grant");
    setChosenGrant(null);
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const source = createFixtureBusinessDataSource({ chatAvailable: true });
    const saved: BusinessExpense[] = await source.expenses("2000-01-01", null);
    assert.ok(saved.length >= 4, "the sample has saved records");
    let api: ReturnType<typeof useBusiness> | null = null;
    function Probe() {
      api = useBusiness();
      return <BusinessPanel />;
    }
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><Probe /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>);
    });
    const facts = () => document.querySelector('[data-testid="receipt-current-facts"]');
    const title = () => document.querySelector("#receipt-review-title")?.textContent ?? null;
    try {
      for (const record of saved) {
        await act(async () => api!.openPanel({ kind: "expense", expenseId: record.id }));
        for (let i = 0; i < 80 && !(facts() && title() === record.merchant); i += 1) {
          await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
        }
        assert.ok(facts(), `${record.id} opens its dossier: ${document.body.textContent?.slice(0, 300)}`);
        assert.equal(title(), record.merchant, record.id);
        assert.deepEqual(oldRecordView(document.querySelector<HTMLElement>('[data-testid="business-record-review"]')!), [], record.id);
      }
    } finally {
      await act(async () => root.unmount());
      host.remove();
      document.body.innerHTML = "";
    }
  });
});
