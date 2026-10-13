import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessExpenseDetail } from "@/lib/business-api";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// A real DOM for focus and unmount; registered for this file only.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const expense = (over: Partial<BusinessExpenseDetail>): BusinessExpenseDetail =>
  ({ id: "exp-1", merchant: "Estación Ruta 3", amount: "2100.00", currency: "DOP", category_id: "transport", account_id: "acct-ops", occurred_on: "2026-10-09", receipt_id: null, draft_id: null, recorded_at: "2026-10-09T15:00:00Z", revision: 1, ...over } as BusinessExpenseDetail);

async function mount(detail: BusinessExpenseDetail) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: ExpenseDetailPanel } = await import("@/components/business-app/ExpenseDetailPanel");
  const opened: BusinessPanelState[] = [];
  const value = {
    source: { expense: async () => detail },
    records: { workspace: { accounts: [{ id: "acct-ops", nickname: "Operating account", type: "bank", currency: "DOP" }] } },
    openPanel: (panel: BusinessPanelState) => { opened.push(panel); },
  } as unknown as BusinessContextValue;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  // The opener: the Expenses row that had focus before the panel appeared.
  const opener = document.createElement("button");
  opener.textContent = "Estación Ruta 3";
  document.body.appendChild(opener);
  opener.focus();
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={value}>
          <ExpenseDetailPanel expenseId={detail.id} />
        </BusinessContext.Provider>
      </I18nextProvider>,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { act, root, host, opener, opened };
}

describe("the expense detail panel", () => {
  test("an expense entered by hand shows its detail, labelled by a title that exists, takes focus, and says no receipt is attached", async () => {
    const page = await mount(expense({}));
    const section = page.host.querySelector("section")!;
    assert.equal(section.getAttribute("aria-labelledby"), "expense-detail-title");
    const title = page.host.querySelector("#expense-detail-title")!;
    assert.ok(title, "the labelled element exists");
    assert.equal(title.textContent, "Estación Ruta 3");
    assert.equal(document.activeElement, section);
    assert.ok(page.host.textContent?.includes("Sin recibo adjunto"));
    assert.deepEqual(page.opened, []);
    // Closing gives focus back to the opener.
    await page.act(async () => page.root.unmount());
    assert.equal(document.activeElement, page.opener);
  });

  test("while loading, the labelled element already exists with the panel's title", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: ExpenseDetailPanel } = await import("@/components/business-app/ExpenseDetailPanel");
    const value = { source: { expense: () => new Promise(() => undefined) }, records: { workspace: null }, openPanel: () => undefined } as unknown as BusinessContextValue;
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><ExpenseDetailPanel expenseId="exp-slow" /></BusinessContext.Provider></I18nextProvider>);
    });
    assert.equal(host.querySelector("#expense-detail-title")?.textContent, "Gasto guardado");
    await act(async () => root.unmount());
  });

  test("an expense that names a receipt opens that receipt's record instead, and never says no receipt is attached", async () => {
    const page = await mount(expense({ id: "exp-hosting", receipt_id: "rcpt-confirmed" }));
    assert.deepEqual(page.opened, [{ kind: "receipt", receiptId: "rcpt-confirmed" }]);
    assert.ok(!page.host.textContent?.includes("Sin recibo adjunto"));
    await page.act(async () => page.root.unmount());
  });

  test("an expense recorded from a draft with no receipt opens that draft", async () => {
    const page = await mount(expense({ id: "exp-note", draft_id: "draft-7" }));
    assert.deepEqual(page.opened, [{ kind: "draft", draftId: "draft-7" }]);
    assert.ok(!page.host.textContent?.includes("Sin recibo adjunto"));
    await page.act(async () => page.root.unmount());
  });
});
