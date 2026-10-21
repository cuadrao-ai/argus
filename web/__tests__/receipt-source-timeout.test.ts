import assert from "node:assert/strict";
import { afterAll, afterEach, describe, test } from "bun:test";
import { fetchBusinessReceiptSource, RECEIPT_SOURCE_TIMEOUT_MS } from "@/lib/business-api";

const realFetch = globalThis.fetch;
const realMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
// Mock auth: the request carries no session header, which is not what these tests are about.
process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
afterEach(() => {
  globalThis.fetch = realFetch;
});
afterAll(() => {
  if (realMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = realMockAuth;
});

describe("the receipt source fetch", () => {
  test("a request that never answers is given up after the timeout, so the preview can fail and offer a retry", async () => {
    globalThis.fetch = ((_: unknown, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(init.signal?.reason ?? new Error("aborted")));
      })) as typeof fetch;
    const started = Date.now();
    await assert.rejects(fetchBusinessReceiptSource("rcpt-1", { timeoutMs: 40 }), (error: unknown) => error instanceof Error && error.name === "TimeoutError");
    assert.ok(Date.now() - started < 2000);
    assert.equal(RECEIPT_SOURCE_TIMEOUT_MS, 30_000);
  });

  test("an answer that arrives in time is returned as its bytes; a non-2xx answer is an API error", async () => {
    globalThis.fetch = (async () => new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { "content-type": "application/pdf" } })) as typeof fetch;
    const blob = await fetchBusinessReceiptSource("rcpt-1", { timeoutMs: 1000 });
    assert.equal(blob.size, 3);
    globalThis.fetch = (async () => new Response("", { status: 404 })) as typeof fetch;
    await assert.rejects(fetchBusinessReceiptSource("rcpt-1", { timeoutMs: 1000 }), /API error 404/);
  });
});
