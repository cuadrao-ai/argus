import assert from "node:assert/strict";
import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { Banknote, FileText, ImageIcon } from "lucide-react";

import type { WorkspaceSearch, WorkspaceSearchGroup } from "../components/chat/ChatWorkspace";
import { HOVER_PREVIEW_MS, WorkspaceSearchResults } from "../components/sidebar/command-palette/WorkspaceSearchResults";
import type { BusinessDataSource } from "../components/business-app/business-data";
import { periodContaining } from "../components/business-app/business-format";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { useBusinessSearch } from "../components/business-app/useBusinessSearch";
import type { BusinessPanelState } from "../components/business-app/BusinessWorkspace";
import type { BusinessCapture, BusinessSearchResult } from "../lib/business-api";

const COPY: WorkspaceSearch["copy"] = {
  placeholder: "Search expenses, receipts and chats",
  noResultsHint: "Try a merchant or a file name.",
  region: "Business records",
  loading: "Searching your business",
  failed: "We couldn't search your business.",
  retry: "Try searching again",
};
const noop = () => undefined;
const search: WorkspaceSearch = { copy: COPY, find: async () => [] };

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

  test("loading and failure each say so in place, and failure offers a retry", () => {
    expect(rendered({ status: "loading" })).toContain(">Searching your business</div>");
    expect(rendered({ status: "loading" })).toContain('role="status"');
    const failed = rendered({ status: "failed" });
    expect(failed).toContain('role="alert"');
    expect(failed).toContain("We couldn&#x27;t search your business.");
    expect(failed).toContain(">Try searching again</button>");
  });

  test("hits render under their group with title, detail and amount", () => {
    const groups: WorkspaceSearchGroup[] = [
      {
        id: "expenses",
        label: "Expenses",
        hits: [
          { id: "e1", icon: Banknote, title: "Ferretería La Esquina", detail: "Oct 6, 2026 · Caja", amount: "RD$ 3,450.00", open: noop },
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

async function businessSearch(found: BusinessSearchResult, notes: BusinessCapture[] | Error = []) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", resources: {} });
  const opened: BusinessPanelState[] = [];
  const periods: string[] = [];
  const source = { search: async () => found, captures: async () => { if (notes instanceof Error) throw notes; return notes; } } as unknown as BusinessDataSource;
  let built: WorkspaceSearch | null = null;
  function Probe() {
    built = useBusinessSearch({
      source,
      chatAvailable: true,
      accounts: [{ id: "acct-1", nickname: "Caja", type: "cash", currency: "DOP" }],
      openPanel: (panel) => opened.push(panel),
      setPeriod: (key) => periods.push(key),
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
    hit.open();
    expect(opened).toEqual([{ kind: "receipt", receiptId: "rcpt-1" }]);
  });

  test("an expense without a receipt opens the draft that recorded it, or its own detail", async () => {
    const recorded = { ...expense, id: "exp-2", receipt_id: null, draft_id: "draft-2" };
    const byHand = { ...expense, id: "exp-3", receipt_id: null };
    const { groups, opened, periods } = await businessSearch({ expenses: [recorded, byHand], receipts: [], accounts: [] });
    groups[0].hits[0].open();
    groups[0].hits[1].open();
    expect(periods).toEqual([]);
    expect(opened).toEqual([{ kind: "draft", draftId: "draft-2" }, { kind: "expense", expenseId: "exp-3" }]);
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
      ["IMG_2214.jpg", ImageIcon, null],
      ["factura.pdf", FileText, null],
    ]);
    expect(receipts.hits[0].detail).toContain("Ready to review");
    receipts.hits[0].open();
    expect(opened).toEqual([{ kind: "receipt", receiptId: "rcpt-2" }]);
  });
});


describe("original note search", () => {
  test("distinct sources sharing a draft open only the canonical draft", async () => {
    const note: BusinessCapture = { draft_id: "draft-1", version: 3, revision: 3, source_id: "source-1", text: "  pintura sin recibo  ", received_at: "2026-10-10T14:00:00Z", review_state: "open" };
    const { groups, opened } = await businessSearch({ expenses: [], receipts: [], accounts: [] }, [note, { ...note, source_id: "source-2", text: "Agrego el pago" }]);
    const captures = groups.find((group) => group.id === "captures")!;
    assert.deepEqual(captures.hits.map((hit) => [hit.id, hit.title, hit.amount]), [["source-1", note.text, null], ["source-2", "Agrego el pago", null]]);
    captures.hits[1].open();
    assert.deepEqual(opened, [{ kind: "draft", draftId: "draft-1" }]);
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

type Element = { type: unknown; props: { children?: unknown; onMouseEnter?: () => void; onMouseLeave?: () => void; onFocus?: () => void; onClick?: (event: { detail: number }) => void; "aria-pressed"?: boolean } };
function buttonsOf(node: unknown, found: Element[] = []): Element[] {
  if (Array.isArray(node)) { node.forEach((child) => buttonsOf(child, found)); return found; }
  if (!node || typeof node !== "object") return found;
  const element = node as Element;
  if (element.type === "button") found.push(element);
  buttonsOf(element.props?.children, found);
  return found;
}

describe("record preview in the results", () => {
  const hit = { id: "exp-1", icon: Banknote, title: "Ferretería", detail: "", amount: null, open: () => undefined };
  const groups: WorkspaceSearchGroup[] = [{ id: "expenses", label: "Expenses", hits: [{ ...hit, preview: <p>record</p> }, { ...hit, id: "exp-2" }] }];

  function rowsWith(handlers: { onPreview?: (group: string, item: { id: string }) => void; onSelect?: (group: string, item: { id: string }) => void; onOpened?: () => void }) {
    let tree: unknown = null;
    function Probe() {
      tree = WorkspaceSearchResults({ search, state: { status: "ready", groups }, retry: noop, onOpened: handlers.onOpened ?? noop, onPreview: handlers.onPreview, onSelect: handlers.onSelect, selectedKey: "expenses:exp-1" });
      return null;
    }
    renderToStaticMarkup(<Probe />);
    return buttonsOf(tree);
  }

  test("focus previews at once; a single click selects; Enter and a double click open the record", () => {
    const previews: string[] = [];
    const selections: string[] = [];
    let opened = 0;
    const [withPreview, withoutPreview] = rowsWith({ onOpened: () => { opened += 1; }, onPreview: (group, item) => previews.push(`${group}:${item.id}`), onSelect: (group, item) => selections.push(`${group}:${item.id}`) });
    withPreview.props.onFocus?.();
    assert.deepEqual(previews, ["expenses:exp-1"]);
    withPreview.props.onClick?.({ detail: 1 });
    assert.deepEqual(selections, ["expenses:exp-1"]);
    assert.equal(opened, 0);
    assert.equal(withPreview.props["aria-pressed"], true);
    withPreview.props.onClick?.({ detail: 0 });
    withPreview.props.onClick?.({ detail: 2 });
    assert.equal(opened, 2);
    assert.equal(withoutPreview.props.onMouseEnter, undefined);
    withoutPreview.props.onClick?.({ detail: 1 });
    assert.equal(opened, 3);
  });

  test("hover previews after a short delay and a leave before it cancels", async () => {
    const previews: string[] = [];
    const [row] = rowsWith({ onPreview: (group, item) => previews.push(`${group}:${item.id}`) });
    row.props.onMouseEnter?.();
    row.props.onMouseLeave?.();
    await new Promise((resolve) => setTimeout(resolve, HOVER_PREVIEW_MS + 50));
    assert.deepEqual(previews, []);
    row.props.onMouseEnter?.();
    assert.deepEqual(previews, []);
    await new Promise((resolve) => setTimeout(resolve, HOVER_PREVIEW_MS + 50));
    assert.deepEqual(previews, ["expenses:exp-1"]);
  });

  test("without a preview handler a click opens the record as before", () => {
    let opened = 0;
    const [row] = rowsWith({ onOpened: () => { opened += 1; } });
    row.props.onClick?.({ detail: 1 });
    assert.equal(opened, 1);
  });

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
