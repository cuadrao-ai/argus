import assert from "node:assert/strict";
import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { Banknote, FileText, ImageIcon } from "lucide-react";

import type { WorkspaceSearch, WorkspaceSearchGroup } from "../components/chat/ChatWorkspace";
import { WorkspaceSearchResults } from "../components/sidebar/command-palette/WorkspaceSearchResults";
import type { BusinessDataSource } from "../components/business-app/business-data";
import { periodContaining } from "../components/business-app/business-format";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { useBusinessSearch } from "../components/business-app/useBusinessSearch";
import type { BusinessPanelState } from "../components/business-app/BusinessWorkspace";
import type { BusinessCapture } from "../lib/business-api";
import type { BusinessSearchResult } from "../lib/business-search-api";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

const COPY: WorkspaceSearch["copy"] = {
  placeholder: "Search a merchant, amount or note",
  noResultsHint: "Search by merchant, amount, category, account or a note's text.",
  region: "Business records",
  loading: "Searching this business",
  failed: "We couldn't search this business.",
  retry: "Try searching again",
  recent: "Recent searches",
  showMore: (count) => `See more (${count})`,
  showLess: "See less",
  loadMore: "Load more",
  loadMoreFailed: "We couldn't load more results.",
  retryLoad: "Retry",
  removeRecent: (query) => `Remove ${query}`,
  clearRecents: "Clear all",
  noMatch: (query) => `Nothing matched “${query}”.`,
  keepTyping: "Type at least 3 letters to search your records.",
  readError: "We couldn't load your chats.",
  loadMoreError: "We couldn't load more chats.",
  ask: "Ask in a new chat",
  close: "Close",
};
const noop = () => undefined;
const search: WorkspaceSearch = { copy: COPY, find: async () => [], shortcuts: [], recents: { key: "cuadrao:business_recent_searches:v1", scope: "own" } };

function rendered(state: Parameters<typeof WorkspaceSearchResults>[0]["state"]) {
  return renderToStaticMarkup(
    <WorkspaceSearchResults search={search} state={state} retry={noop} onOpened={noop} />,
  );
}

describe("workspace results in the omnisearch", () => {
  test("idle and empty answers render nothing, so conversation states stay as they are", () => {
    expect(rendered({ status: "idle" })).toBe("");
    expect(rendered({ status: "ready", groups: [] })).toBe("");
  });

  test.each([
    ["en", "Searching this business", "We couldn't search this business.", "Try searching again"],
    ["es-419", "Buscando en este negocio", "No pudimos buscar en este negocio.", "Intentar la búsqueda de nuevo"],
  ] as const)("loading and failure say the app's own words in %s, in place, and failure offers a retry", async (language, loading, failed, retry) => {
    // The hook's copy, read through the shipped locale files: the words a person sees, not a copy of them.
    const { search: real } = await businessSearch({}, [], language);
    const shown = (state: Parameters<typeof WorkspaceSearchResults>[0]["state"]) =>
      renderToStaticMarkup(<WorkspaceSearchResults search={real} state={state} retry={noop} onOpened={noop} />).replaceAll("&#x27;", "'");
    expect(shown({ status: "loading" })).toContain(`>${loading}</div>`);
    expect(shown({ status: "loading" })).toContain('role="status"');
    const failure = shown({ status: "failed" });
    expect(failure).toContain('role="alert"');
    expect(failure).toContain(failed);
    expect(failure).toContain(`>${retry}</button>`);
  });

  test("hits render under their group with title, detail and amount", () => {
    const groups: WorkspaceSearchGroup[] = [
      {
        id: "expenses",
        label: "Expenses",
        hits: [
          { id: "e1", icon: Banknote, title: "Ferretería La Esquina", detail: "Oct 6, 2026 · Caja", amount: "RD$ 3,450.00", badge: "Expense", open: noop },
        ],
      },
    ];
    const html = rendered({ status: "ready", groups });
    expect(html).toContain('aria-label="Business records"');
    expect(html).toContain('aria-label="Expenses"');
    expect(html).toContain("data-workspace-hit");
    expect(html).toContain(">Ferretería La Esquina</span>");
    expect(html).toContain(">Oct 6, 2026 · Caja</span>");
    expect(html).toContain(">RD$ 3,450.00</span>");
    expect(html).toContain(">Expense</span>");
  });

  test("a group shows three rows and Ver más reveals the rest it already holds", () => {
    const hits = ["a", "b", "c", "d", "e"].map((id) => ({ id, icon: Banknote, title: `Row ${id}`, detail: "", amount: null, badge: "Expense", open: noop }));
    const html = rendered({ status: "ready", groups: [{ id: "expenses", label: "Expenses", hits }] });
    expect(html).toContain(">Row c</span>");
    expect(html).not.toContain(">Row d</span>");
    expect(html).toContain("See more (2)");
  });

  test("a hit with nowhere to open is shown, not offered as a button", () => {
    const html = rendered({ status: "ready", groups: [{ id: "accounts", label: "Accounts", hits: [{ id: "acct", icon: Banknote, title: "Caja chica", detail: "DOP", amount: null, badge: "Account" }] }] });
    expect(html).toContain(">Caja chica</span>");
    expect(html).toContain('data-testid="workspace-hit-static"');
    expect(html).not.toContain("<button");
  });
});

describe("a manual expense opens in the period that holds it", () => {
  const now = new Date(2026, 9, 8, 12);
  test("this month, then last month, then the last 30 days, else none", () => {
    expect(periodContaining("2026-10-02", now)).toBe("this_month");
    expect(periodContaining("2026-09-20", now)).toBe("last_month");
    expect(periodContaining("2026-08-01", now)).toBeNull();
  });
});

describe("the sample source answers like the API", () => {
  test("a confirmed receipt is found through its expense, never twice", async () => {
    const source = createFixtureBusinessDataSource();
    const hosting = await source.search("nube hosting");
    expect(hosting.expenses.map((e) => [e.id, e.receipt_id])).toEqual([["exp-hosting", "rcpt-confirmed"]]);
    expect(hosting.receipts).toEqual([]);
    const ferreteria = await source.search("ferreteria");
    expect(ferreteria.receipts.map((r) => r.id)).toEqual(["rcpt-ferreteria"]);
    expect((await source.search("papeleria-oct")).receipts.map((r) => r.id)).toEqual(["rcpt-papeleria"]);
  });
});

const NO_RESULTS: BusinessSearchResult = { expenses: [], ventas: [], receipts: [], accounts: [], email_deliveries: [], email_senders: [], next_cursors: {} };

async function businessSearch(partial: Partial<BusinessSearchResult>, notes: BusinessCapture[] | Error = [], language?: "en" | "es-419") {
  const i18n = i18next.createInstance();
  // Without a language the hook's built-in fallbacks speak; with one, the shipped locale file does.
  await i18n.init(language
    ? { lng: language, fallbackLng: false, interpolation: { escapeValue: false }, resources: { en: { translation: en }, "es-419": { translation: es419 } } }
    : { lng: "en", resources: {} });
  const found = { ...NO_RESULTS, ...partial };
  const opened: BusinessPanelState[] = [];
  const periods: string[] = [];
  const source = { search: async () => found, captures: async () => { if (notes instanceof Error) throw notes; return { items: notes }; } } as unknown as BusinessDataSource;
  const actions = { create: [{ id: "upload_receipt" as const, label: "Add", icon: Banknote, run: noop }], composer: [], starterEntries: [] };
  let built: WorkspaceSearch | null = null;
  function Probe() {
    built = useBusinessSearch({
      source,
      accounts: [{ id: "acct-1", nickname: "Caja", type: "cash", currency: "DOP" }],
      openPanel: (panel) => opened.push(panel),
      actions,
      owner: true,
      scope: "own",
      canExport: true,
      openExport: noop,
    });
    return null;
  }
  renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <Probe />
    </I18nextProvider>,
  );
  const groups = await (built as unknown as WorkspaceSearch).find("ferreteria");
  return { groups, opened, periods, search: built as unknown as WorkspaceSearch };
}

const expense = {
  id: "exp-1",
  merchant: "Ferretería La Esquina",
  amount: "3450.00",
  currency: "DOP",
  category_id: null,
  account_id: "acct-1",
  occurred_on: "2026-10-06",
  receipt_id: "rcpt-1",
};

describe("Business hits open the panel that holds them", () => {
  test("an expense with a receipt opens that receipt, where its original downloads", async () => {
    const { groups, opened } = await businessSearch({ expenses: [expense], receipts: [], accounts: [] });
    const [hit] = groups[0].hits;
    expect([groups[0].label, hit.title, hit.amount, hit.icon]).toEqual([
      "Expenses",
      "Ferretería La Esquina",
      "RD$ 3,450.00",
      Banknote,
    ]);
    expect(hit.detail).toContain("Caja");
    expect(hit.badge).toBe("Expense");
    hit.open?.();
    expect(opened).toEqual([{ kind: "receipt", receiptId: "rcpt-1", list: "transactions" }]);
  });

  test("an expense without a receipt opens the draft that recorded it, or its own detail", async () => {
    const recorded = { ...expense, id: "exp-2", receipt_id: null, draft_id: "draft-2" };
    const byHand = { ...expense, id: "exp-3", receipt_id: null };
    const { groups, opened, periods } = await businessSearch({ expenses: [recorded, byHand], receipts: [], accounts: [] });
    groups[0].hits[0].open?.();
    groups[0].hits[1].open?.();
    expect(periods).toEqual([]);
    expect(opened).toEqual([{ kind: "draft", draftId: "draft-2", list: "transactions" }, { kind: "expense", expenseId: "exp-3" }]);
  });

  test("a receipt opens its review and shows the file type it is", async () => {
    const receipt = {
      id: "rcpt-2",
      channel: "whatsapp" as const,
      filename: "IMG_2214.jpg",
      media_type: "image/jpeg",
      size_bytes: 1,
      received_at: "2026-10-07T14:00:00Z",
      status: "review_ready" as const,
      error_code: null,
      expense_id: null,
      merchant: null,
      occurred_on: null,
      amount: null,
      currency: null,
      category_id: null,
      account_id: null,
    };
    const pdf = { ...receipt, id: "rcpt-3", media_type: "application/pdf", filename: "factura.pdf" };
    const { groups, opened } = await businessSearch({ expenses: [], receipts: [receipt, pdf], accounts: [] });
    const receipts = groups.find((group) => group.id === "receipts")!;
    expect(receipts.hits.map((hit) => [hit.title, hit.icon, hit.amount])).toEqual([
      ["IMG_2214.jpg", ImageIcon, "-"],
      ["factura.pdf", FileText, "-"],
    ]);
    expect(receipts.hits[0].detail).toContain("Ready to review");
    expect(receipts.hits[0].badge).toBe("Receipt");
    receipts.hits[0].open?.();
    expect(opened).toEqual([{ kind: "receipt", receiptId: "rcpt-2", list: "inbox" }]);
  });
});


describe("original note search", () => {
  test("distinct sources sharing a draft open only the canonical draft", async () => {
    const note: BusinessCapture = { draft_id: "draft-1", version: 3, revision: 3, source_id: "source-1", text: "  pintura sin recibo  ", received_at: "2026-10-10T14:00:00Z", review_state: "open" };
    const { groups, opened } = await businessSearch({ expenses: [], receipts: [], accounts: [] }, [note, { ...note, source_id: "source-2", text: "Agrego el pago" }]);
    const captures = groups.find((group) => group.id === "captures")!;
    assert.deepEqual(captures.hits.map((hit) => [hit.id, hit.title, hit.amount]), [["source-1", note.text, null], ["source-2", "Agrego el pago", null]]);
    assert.equal(captures.hits[1].badge, "Note");
    captures.hits[1].open?.();
    assert.deepEqual(opened, [{ kind: "draft", draftId: "draft-1", list: "inbox" }]);
  });
  test("notes outage preserves real records and a safe error without fake hits", async () => {
    const { groups } = await businessSearch({ expenses: [expense], receipts: [], accounts: [] }, new Error("private server details"));
    assert.equal(groups[0].hits[0].id, expense.id);
    assert.deepEqual(groups.find((group) => group.id === "captures")!.hits, []);
    const html = rendered({ status: "ready", groups });
    assert.ok(html.includes('role="alert"'));
    assert.ok(html.includes("Notes are unavailable"));
    assert.ok(html.includes(expense.merchant));
    assert.ok(!html.includes("private server details"));
  });
});

describe("record preview in the results", () => {
  test("every Business hit carries a preview that shows what the hit already knows", async () => {
    const note: BusinessCapture = { draft_id: "draft-1", version: 5, revision: 2, source_id: "source-1", text: "pintura sin recibo", received_at: "2026-10-10T14:00:00Z", review_state: "open" };
    const receipt = { id: "rcpt-9", channel: "web" as const, filename: "factura-9.pdf", media_type: "application/pdf", size_bytes: 1, received_at: "2026-10-07T14:00:00Z", status: "review_ready" as const, error_code: null, expense_id: null, merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null, attention: null, preparable: false, enterable: false };
    const { groups: found, search: built } = await businessSearch({ expenses: [expense], receipts: [receipt], accounts: [] }, [note]);
    assert.equal(built.previewAvailable, true);
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "en", resources: {} });
    const html = (group: string) => renderToStaticMarkup(<I18nextProvider i18n={i18n}>{found.find((item) => item.id === group)!.hits[0].preview}</I18nextProvider>);
    assert.ok(html("expenses").includes("Ferretería La Esquina") && html("expenses").includes("RD$"));
    assert.ok(html("receipts").includes("factura-9.pdf"));
    assert.ok(html("captures").includes("pintura sin recibo") && html("captures").includes("Revision 2"));
  });
});
