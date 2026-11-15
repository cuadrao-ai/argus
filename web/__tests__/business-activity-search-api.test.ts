import { afterEach, beforeEach, expect, test } from "bun:test";
import { getBusinessActivity, searchBusinessActivity } from "@/lib/business-activity-api";

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeEach(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; });
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
});

function respond(...pages: { items: unknown[]; next_cursor: string | null }[]) {
  const asked: Record<string, string>[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    expect(url.pathname.endsWith("/business/activity")).toBe(true);
    asked.push(Object.fromEntries(url.searchParams));
    const page = pages.shift();
    if (!page) throw new Error("Unexpected request");
    return Response.json(page);
  }) as typeof fetch;
  return asked;
}

const row = { id: "a1", occurred_at: "2026-11-10T14:00:00Z", actor: { display_name: "Lucía Peña", kind: "member" }, action: "receipt_upload", object: null };

test("the feed sends a query only when it has one", async () => {
  const asked = respond({ items: [], next_cursor: null }, { items: [row], next_cursor: null });
  await getBusinessActivity(null);
  await searchBusinessActivity("Lucía");
  expect(asked).toEqual([{ limit: "25" }, { limit: "25", q: "Lucía" }]);
});

test("a search follows the server's cursor past an answer that found nothing yet", async () => {
  const asked = respond({ items: [], next_cursor: "c1" }, { items: [], next_cursor: "c2" }, { items: [row], next_cursor: "c3" });
  const page = await searchBusinessActivity("Lucía");
  expect(asked.map((query) => query.cursor)).toEqual([undefined, "c1", "c2"]);
  expect(page).toEqual({ items: [row], next_cursor: "c3" });
});

test("a search that reaches the end with nothing answers an empty page", async () => {
  respond({ items: [], next_cursor: "c1" }, { items: [], next_cursor: null });
  expect(await searchBusinessActivity("nadie", "c0")).toEqual({ items: [], next_cursor: null });
});
