import type { BusinessAccount, BusinessExpense, ReceiptSummary } from "@/lib/business-api";
import {
  SEARCH_INVALID_CURSOR,
  SEARCH_STALE_CURSOR,
  type BusinessSearchEmail,
  type BusinessSearchKind,
  type BusinessSearchRecent,
  type BusinessSearchResult,
  type BusinessSearchSender,
} from "@/lib/business-search-api";
import type { BusinessDataSource } from "./business-data";

/**
 * The sample's Business search: the same lists, cursors, recents and opens as
 * the API, over invented records, for the local preview and the browser tests.
 */

const PAGE = 5;
const RECENTS = 10;

const day = (days: number) => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
};

/** Sales: `merchant` holds the client, as the API lists it. All share the word "cliente" so one search pages. */
export const SAMPLE_VENTAS: BusinessExpense[] = [
  ["Colmado Peña", "18500.00", 1],
  ["Taller Rodríguez", "42000.00", 2],
  ["Estudio Mejía", "9800.00", 3],
  ["Hotel Costa Azul", "125000.00", 5],
  ["Distribuidora Ureña", "33250.00", 6],
  ["Panadería Santana", "4200.00", 8],
  ["Boutique Ariel", "7650.00", 9],
].map(([client, amount, ago], index) => ({
  id: `venta-${index + 1}`,
  merchant: `Cliente ${client}`,
  amount: String(amount),
  currency: "DOP",
  category_id: null,
  account_id: "acct-ops",
  occurred_on: day(Number(ago)),
  receipt_id: null,
  draft_id: null,
}));

export const SAMPLE_SENDERS: BusinessSearchSender[] = [
  { id: "sender-ferreteria", kind: "address", value: "ventas@ferreterialaesquina.example", status: "authorized" },
  { id: "sender-colmado", kind: "domain", value: "colmadoelprimo.example", status: "authorized" },
  { id: "sender-boletin", kind: "address", value: "noticias@proveedor.example", status: "blocked" },
];

type Env = Readonly<{
  expenses: () => readonly BusinessExpense[];
  receipts: () => readonly ReceiptSummary[];
  accounts: () => readonly BusinessAccount[];
  emails: () => readonly BusinessSearchEmail[];
  matches: (query: string, text: string) => boolean;
  delay: () => Promise<unknown>;
  /** A write error a test asked for, if one is waiting. */
  injected: () => Error | null;
}>;

type Search = Pick<BusinessDataSource, "search" | "searchMore" | "searchRecents" | "addSearchRecent" | "removeSearchRecent" | "clearSearchRecents" | "recordSearchOpen">;

const EMPTY: BusinessSearchResult = { expenses: [], ventas: [], receipts: [], accounts: [], email_deliveries: [], email_senders: [], next_cursors: {} };

/**
 * A test or a person in the preview can make the next load-more page fail:
 * `globalThis.__businessFixtureFailNextSearchMore = "business_search_stale_cursor"`
 * (409), `"business_search_invalid_cursor"` (422) or `"network"` (500).
 */
function injectedPageError(): Error | null {
  const holder = globalThis as { __businessFixtureFailNextSearchMore?: string };
  const code = holder.__businessFixtureFailNextSearchMore;
  if (!code) return null;
  delete holder.__businessFixtureFailNextSearchMore;
  const status = code === SEARCH_STALE_CURSOR ? 409 : code === SEARCH_INVALID_CURSOR ? 422 : 500;
  return Object.assign(new Error(code), { status, code });
}

export function createFixtureSearch(env: Env): Search {
  let recents: BusinessSearchRecent[] = [];
  const opened = new Map<BusinessSearchKind, string[]>();
  let counter = 0;

  /** Opened records first, in the order they were opened last. */
  const ranked = <T extends { id: string }>(kind: BusinessSearchKind, items: T[]): T[] => {
    const order = opened.get(kind) ?? [];
    const rank = (item: T) => {
      const at = order.indexOf(item.id);
      return at < 0 ? order.length : at;
    };
    return items.map((item, index) => ({ item, index })).sort((a, b) => rank(a.item) - rank(b.item) || a.index - b.index).map(({ item }) => item);
  };

  const lists = (query: string): Omit<BusinessSearchResult, "next_cursors"> => {
    const text = query.trim();
    const found = env.expenses().filter((item) => env.matches(text, [item.merchant, item.category_id, item.amount].join(" "))).sort((a, b) => b.occurred_on.localeCompare(a.occurred_on));
    const listed = new Set(found.map((item) => item.id));
    return {
      expenses: found,
      ventas: SAMPLE_VENTAS.filter((item) => env.matches(text, [item.merchant, item.amount].join(" "))),
      receipts: env.receipts().filter((item) => !listed.has(item.expense_id ?? "")).filter((item) => env.matches(text, [item.merchant, item.filename, item.amount].join(" "))) as ReceiptSummary[],
      accounts: env.accounts().filter((item) => env.matches(text, [item.nickname, item.type, item.currency].join(" "))) as BusinessAccount[],
      email_deliveries: env.emails().filter((item) => env.matches(text, [item.subject, item.sender].join(" "))) as BusinessSearchEmail[],
      email_senders: SAMPLE_SENDERS.filter((item) => env.matches(text, item.value)),
    };
  };

  const page = (query: string, only: BusinessSearchKind | null, offset: number): BusinessSearchResult => {
    const all = lists(query);
    const out: BusinessSearchResult = { ...EMPTY, next_cursors: {} };
    for (const kind of Object.keys(all) as BusinessSearchKind[]) {
      if (only && kind !== only) continue;
      const rows = ranked(kind, all[kind] as { id: string }[]);
      (out[kind] as unknown[]) = rows.slice(offset, offset + PAGE);
      out.next_cursors[kind] = offset + PAGE < rows.length ? `offset:${offset + PAGE}` : null;
    }
    return out;
  };

  return {
    search: async (query) => {
      await env.delay();
      const failure = env.injected();
      if (failure) throw failure;
      return page(query, null, 0);
    },
    searchMore: async (query, kind, cursor) => {
      await env.delay();
      const failure = injectedPageError();
      if (failure) throw failure;
      const match = /^offset:(\d+)$/.exec(cursor);
      if (!match) throw Object.assign(new Error(SEARCH_INVALID_CURSOR), { status: 422, code: SEARCH_INVALID_CURSOR });
      return page(query, kind, Number(match[1]));
    },
    searchRecents: async () => {
      await env.delay();
      return recents.map((item) => ({ ...item }));
    },
    addSearchRecent: async (query) => {
      const text = query.trim();
      if (!text) return;
      recents = [{ id: `recent-${++counter}`, q: text, searched_at: new Date().toISOString() }, ...recents.filter((item) => item.q.toLowerCase() !== text.toLowerCase())].slice(0, RECENTS);
    },
    removeSearchRecent: async (id) => {
      recents = recents.filter((item) => item.id !== id);
    },
    clearSearchRecents: async () => {
      recents = [];
    },
    recordSearchOpen: async (kind, id) => {
      opened.set(kind, [id, ...(opened.get(kind) ?? []).filter((item) => item !== id)]);
    },
  };
}
