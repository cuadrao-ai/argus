import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessExpense, BusinessExpenseDetail } from "@/lib/business-api";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// Every saved record opens the one dossier: the receipt or draft behind it. A record opened by its own id
// only names that record; it never draws a view of its own.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
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

async function mountRecord(source: BusinessDataSource, grantId: string | null = null) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(grantId);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  let workspace: ReturnType<typeof useChatWorkspace>;
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    workspace = useChatWorkspace();
    return <BusinessPanel />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><Probe /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>);
  });
  return {
    open: (next: BusinessPanelState) => api!.openPanel(next),
    chosen: () => api!.chosen,
    search: (query: string) => workspace!.search.find(query),
    async close() {
      await act(async () => root.unmount());
      host.remove();
      document.body.innerHTML = "";
      setChosenGrant(null);
    },
  };
}

describe("the sample's saved records", () => {
  test("each opens its dossier, with its facts, from Registros' own id", async () => {
    const { act } = await import("react");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const source = createFixtureBusinessDataSource({ chatAvailable: true });
    const saved: BusinessExpense[] = await source.expenses("2000-01-01", null);
    assert.ok(saved.length >= 4, "the sample has saved records");
    const page = await mountRecord(source);
    const facts = () => document.querySelector('[data-testid="receipt-current-facts"]');
    const title = () => document.querySelector("#receipt-review-title")?.textContent ?? null;
    try {
      for (const record of saved) {
        await act(async () => page.open({ kind: "expense", expenseId: record.id }));
        for (let i = 0; i < 80 && !(facts() && title() === record.merchant); i += 1) {
          await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
        }
        assert.ok(facts(), `${record.id} opens its dossier: ${document.body.textContent?.slice(0, 300)}`);
        assert.equal(title(), record.merchant, record.id);
        assert.deepEqual(oldRecordView(document.querySelector<HTMLElement>('[data-testid="business-record-review"]')!), [], record.id);
      }
    } finally {
      await page.close();
    }
  });
});

test("receipt, draft, expense, search and deep links show the dossier's own origin and title", async () => {
  const { act } = await import("react");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { formatTimestamp } = await import("@/components/business-app/business-format");
  const { dossierFileSize } = await import("@/components/business-app/dossier/DossierAnnotations");
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const record = (await fixture.expenses("2000-01-01", null)).find(row => row.draft_id && row.receipt_id)!;
  const receipt = { ...await fixture.receipt(record.receipt_id!), channel: "email" as const };
  const expense = await fixture.expense(record.id);
  const draftId = record.draft_id!;
  // Give the receipt row and source evidence different values: reading either must fail on every route.
  const origin = {
    channel: "web" as const,
    sent_by: { kind: "member" as const, id: "member:origin", person: { shown_as: "name" as const, display_name: "María Solís" } },
    filename: "comprobante-original.pdf",
    received_at: "2026-10-11T14:36:00Z",
    size_bytes: 18700,
  };
  const title = "Suministros de muestra";
  const found = { receipts: [receipt], expenses: [record], ventas: [], accounts: [], email_deliveries: [], email_senders: [], next_cursors: {} };
  const note = (await fixture.captures()).items[0];
  const spaces = await fixture.spaces();
  const dossier = await fixture.dossier(draftId);
  const owner = spaces.find(space => space.space_id === dossier.space_id && space.role === "owner");
  assert.ok(owner);
  assert.ok(owner.capabilities.includes("approve"));
  const file = new Blob(["%PDF-1.4\nsynthetic receipt"], { type: "application/pdf" });
  const original = dossier.sources.find(item => item.kind === "attachment" && item.connection_id === receipt.id);
  assert.ok(original?.kind === "attachment");
  const other = { ...original, id: "source-other", connection_id: "receipt-other", filename: "later.pdf" };
  const served = {
    ...dossier, title, origin, original_connection_id: original.connection_id, delete_available: true,
    sources: [other, ...dossier.sources.map(item => item.id === original.id ? { ...original, channel: "whatsapp" as const } : item)],
  };
  const asked: string[] = [];
  const source: BusinessDataSource = {
    ...fixture,
    dossier: async id => {
      asked.push(id);
      return id === draftId ? served : fixture.dossier(id);
    },
    receipt: async id => id === receipt.id ? receipt : fixture.receipt(id),
    expense: async id => id === expense.id ? expense : fixture.expense(id),
    receiptSource: async id => id === receipt.id ? file : new Blob(["another file"]),
    search: async () => found,
    spaces: async () => spaces,
    captures: async () => ({ items: [{ ...note, draft_id: draftId }] }),
    deleteDocument: async () => { throw new Error("Only the preview is opened"); },
  };
  const expectedBytes = Buffer.from(await file.arrayBuffer()).toString("base64");
  const links = { receipt: receipt.id, draft: draftId, expense: record.id };
  const routes = ["receipt", "draft", "expense", "search-receipts", "search-expenses", "search-captures", "?receipt", "?draft", "?expense"] as const;
  for (const route of routes) {
    asked.length = 0;
    const query = route.startsWith("?") ? route.slice(1) as keyof typeof links : null;
    window.history.replaceState(null, "", query ? `/biz?${query}=${links[query]}` : "/biz");
    const page = await mountRecord(source, owner.grant_id);
    try {
      assert.equal(page.chosen()?.grant_id, owner.grant_id, route);
      await act(async () => {
        if (route === "receipt") page.open({ kind: "receipt", receiptId: receipt.id, list: "inbox" });
        if (route === "draft") page.open({ kind: "draft", draftId, list: "transactions" });
        if (route === "expense") page.open({ kind: "expense", expenseId: record.id });
        if (route.startsWith("search-")) {
          const groups = await page.search(title);
          const hit = groups.find(group => group.id === route.slice("search-".length))?.hits[0];
          assert.ok(hit?.open, route);
          hit.open();
        }
      });
      for (let i = 0; i < 80 && !document.querySelector('[data-testid="dossier-document-foot"] a[download]'); i++) {
        await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)); });
      }
      assert.deepEqual([...new Set(asked)], [draftId], route);
      const foot = document.querySelector('[data-testid="dossier-document-foot"]');
      assert.equal(foot?.querySelector("[title]")?.getAttribute("title"), origin.filename, route);
      const download = foot?.querySelector<HTMLAnchorElement>("a[download]");
      assert.equal(download?.download, origin.filename, route);
      assert.equal(foot?.querySelector('[data-testid="receipt-source-channel"]')?.textContent, "Carga web", route);
      assert.equal(download?.getAttribute("href"), `data:application/pdf;base64,${expectedBytes}`, route);
      const details = document.querySelector<HTMLButtonElement>('[role="tab"][data-tab="detalles"]');
      assert.ok(details, route);
      await act(async () => details.click());
      const value = (fact: string) => document.querySelector(`[data-testid="dossier-details"] [data-fact="${fact}"] > :nth-child(3)`)?.textContent;
      assert.deepEqual([document.querySelector("#receipt-review-title")?.textContent, ...["channel", "sent_by", "received_at", "filename", "size"].map(value)],
        [title, "Carga web", origin.sent_by.person.display_name, formatTimestamp(origin.received_at, "es-419"), origin.filename, dossierFileSize(origin.size_bytes, "es-419")], route);
      const click = async (selector: string) => {
        const button = document.querySelector<HTMLButtonElement>(selector);
        assert.ok(button, selector);
        await act(async () => button.click());
      };
      await click('[data-testid="receipt-more"] > button');
      await click('[data-testid="delete-document-menu"]');
      const fileRow = [...document.querySelectorAll('[role="alertdialog"] dl > div')].find(row => row.querySelector("dt")?.textContent === "Archivo");
      assert.equal(fileRow?.querySelector("dd")?.textContent, origin.filename, route);
      const dialog = document.querySelector('[role="alertdialog"]');
      assert.equal(dialog?.querySelector("#argus-confirm-title")?.textContent, "¿Eliminar este documento?", route);
      assert.equal(dialog?.querySelector('[data-testid="document-delete-facts"]')?.getAttribute("aria-label"), title, route);
    } finally {
      await page.close();
      window.history.replaceState(null, "", "/biz");
    }
  }
});
