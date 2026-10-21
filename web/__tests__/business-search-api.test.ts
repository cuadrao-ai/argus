import { afterEach, beforeEach, describe, expect, test } from "bun:test";

import { liveBusinessDataSource } from "@/components/business-app/business-data";
import {
  addBusinessSearchRecent,
  BUSINESS_SEARCH_KINDS,
  clearBusinessSearchRecents,
  isInvalidSearchCursor,
  isStaleSearchCursor,
  listBusinessSearchRecents,
  normalizeSearchQuery,
  parseBusinessSearch,
  recordBusinessSearchOpen,
  removeBusinessSearchRecent,
  searchBusiness,
  searchBusinessMore,
} from "@/lib/business-search-api";

type Call = { url: string; method: string; body: unknown };
type Reply = { status: number; body?: unknown; headers?: Record<string, string> };

function respond(...replies: Reply[]): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    const reply = replies.shift();
    if (!reply) throw new Error("Unexpected request");
    if (reply.body === undefined) return new Response(null, { status: reply.status, headers: reply.headers });
    return new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json", ...reply.headers } });
  }) as typeof fetch;
  return calls;
}

const params = (call: Call) => Object.fromEntries(new URL(call.url).searchParams);

describe("Business search client", () => {
  const originalFetch = globalThis.fetch;
  const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  beforeEach(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  });

  test("reads every list the backend sends, with each list's cursor", async () => {
    const body = {
      expenses: [{ id: "e1" }],
      ventas: [{ id: "v1", merchant: "Cliente Peña" }],
      receipts: [{ id: "r1" }],
      accounts: [{ id: "a1" }],
      email_deliveries: [{ id: "m1", sender: null, subject: null, received_at: "2026-10-01T10:00:00Z", state: "received", inbox_group: null }],
      email_senders: [{ id: "s1", kind: "domain", value: "proveedor.example", status: "blocked" }],
      next_cursors: { expenses: "c-e", ventas: null, email_senders: "c-s" },
    };
    const calls = respond({ status: 200, body });
    const found = await searchBusiness("peña");
    expect(params(calls[0])).toEqual({ q: "peña", limit: "5" });
    for (const kind of BUSINESS_SEARCH_KINDS) expect(found[kind].length).toBe(1);
    expect(found.email_deliveries[0].subject).toBeNull();
    expect(found.next_cursors).toEqual({ expenses: "c-e", email_senders: "c-s" });
  });

  test("a backend that predates the new lists answers with them empty", async () => {
    respond({ status: 200, body: { expenses: [{ id: "e1" }], receipts: [], accounts: [] } });
    const found = await searchBusiness("hosting");
    expect(found.expenses.length).toBe(1);
    expect([found.ventas, found.email_deliveries, found.email_senders, found.next_cursors]).toEqual([[], [], [], {}]);
    expect(parseBusinessSearch(null).expenses).toEqual([]);
    expect(parseBusinessSearch({ expenses: "no", next_cursors: [] }).next_cursors).toEqual({});
  });

  test.each(BUSINESS_SEARCH_KINDS)("load more for %s asks for that list alone with the same query and limit", async (kind) => {
    const calls = respond({ status: 200, body: { [kind]: [{ id: "x" }], next_cursors: { [kind]: null } } });
    const page = await searchBusinessMore("cliente", kind, "cursor-1");
    expect(params(calls[0])).toEqual({ q: "cliente", limit: "5", kind, cursor: "cursor-1" });
    expect(page[kind].length).toBe(1);
    expect(page.next_cursors[kind]).toBeUndefined();
  });

  test("a 409 is a stale cursor and a 422 with its code is an invalid one", async () => {
    respond(
      { status: 409, body: { code: "business_search_stale_cursor" } },
      { status: 422, body: { code: "business_search_invalid_cursor" } },
    );
    const stale = await searchBusinessMore("a b", "ventas", "old").catch((error) => error);
    const invalid = await searchBusinessMore("a b", "ventas", "bad").catch((error) => error);
    expect([isStaleSearchCursor(stale), isInvalidSearchCursor(stale)]).toEqual([true, false]);
    expect([isStaleSearchCursor(invalid), isInvalidSearchCursor(invalid)]).toEqual([false, true]);
  });

  test("an amount typed with thousands separators and no decimals is sent as digits", async () => {
    expect(normalizeSearchQuery("3,450")).toBe("3450");
    expect(normalizeSearchQuery(" 1,234,567 ")).toBe("1234567");
    expect(normalizeSearchQuery("RD$ 3,450")).toBe("RD$ 3450");
    expect(normalizeSearchQuery("$3,450")).toBe("$3450");
    for (const kept of ["3450", "3,450.00", "12,5", "1,23", "ferretería 3,450", "3,45", "-3,450", "3,450 pesos"]) expect(normalizeSearchQuery(kept)).toBe(kept.trim());
    const calls = respond({ status: 200, body: {} }, { status: 200, body: {} }, { status: 200, body: {} });
    await searchBusiness("3,450");
    await searchBusiness("3,450.00");
    await searchBusinessMore("3,450", "expenses", "c");
    expect(calls.map((call) => params(call).q)).toEqual(["3450", "3,450.00", "3450"]);
  });

  test("the live source applies it, so every caller of search and load more gets it", async () => {
    const calls = respond({ status: 200, body: {} }, { status: 200, body: {} });
    await liveBusinessDataSource.search("3,450");
    await liveBusinessDataSource.searchMore!("3,450", "receipts", "c1");
    expect(calls.map((call) => params(call).q)).toEqual(["3450", "3450"]);
  });

  test("recents list, add, remove and clear use the recents routes, and empty answers do not break", async () => {
    const calls = respond(
      { status: 200, body: { items: [{ id: "r1", q: "ferretería", searched_at: "2026-10-01T10:00:00Z" }, { nope: true }] } },
      { status: 201, body: {}, headers: { "content-length": "0" } },
      { status: 201 },
      { status: 204 },
      { status: 204 },
    );
    expect(await listBusinessSearchRecents()).toEqual([{ id: "r1", q: "ferretería", searched_at: "2026-10-01T10:00:00Z" }]);
    await addBusinessSearchRecent("peña");
    await addBusinessSearchRecent("peña");
    await removeBusinessSearchRecent("r 1");
    await clearBusinessSearchRecents();
    expect(calls.map((call) => [call.method, new URL(call.url).pathname.replace(/^.*\/business/, "/business"), call.body])).toEqual([
      ["GET", "/business/search/recents", null],
      ["POST", "/business/search/recents", { q: "peña" }],
      ["POST", "/business/search/recents", { q: "peña" }],
      ["DELETE", "/business/search/recents/r%201", null],
      ["DELETE", "/business/search/recents", null],
    ]);
  });

  test("an open is posted with its list and id and needs no body back", async () => {
    const calls = respond({ status: 204 });
    await recordBusinessSearchOpen("email_deliveries", "m1");
    expect([calls[0].method, new URL(calls[0].url).pathname.endsWith("/business/search/opens"), calls[0].body]).toEqual(["POST", true, { kind: "email_deliveries", id: "m1" }]);
  });

  test("a backend without the recents routes answers 404 and the call rejects for the caller to degrade", async () => {
    respond({ status: 404, body: { detail: "Not Found" } });
    const error = await listBusinessSearchRecents().catch((failure) => failure);
    expect((error as { status: number }).status).toBe(404);
  });
});
