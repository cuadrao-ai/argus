import { afterEach, describe, expect, test } from "bun:test";
import { unauthenticatedApiFetch } from "@/lib/argus-api-transport";
import { referenceCode } from "@/lib/failure-screen";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

function failWith(status: number, body: unknown, headers: Record<string, string> = {}) {
  globalThis.fetch = (async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } })) as unknown as typeof fetch;
}

async function caught(run: () => Promise<unknown>): Promise<unknown> {
  try { await run(); } catch (error) { return error; }
  throw new Error("expected a failure");
}

describe("a failed API call carries the server's request id", () => {
  test("the reference a person sees is the server's X-Request-Id", async () => {
    failWith(503, { code: "business_bank_unavailable" }, { "X-Request-Id": "req_7f3a9c" });
    const error = await caught(() => unauthenticatedApiFetch("/business/bank/movements"));
    expect(referenceCode(error)).toBe("req_7f3a9c");
  });

  test("the body's request_id is used when the header is missing", async () => {
    failWith(500, { code: "internal_error", request_id: "req_body42" });
    const error = await caught(() => unauthenticatedApiFetch("/me"));
    expect(referenceCode(error)).toBe("req_body42");
  });

  test("an unsafe id is never shown; a local code stands in", async () => {
    failWith(500, { code: "internal_error" }, { "X-Request-Id": "provider said no" });
    const error = await caught(() => unauthenticatedApiFetch("/me"));
    expect(referenceCode(error)).toMatch(/^c[0-9a-f]{8}$/);
  });
});
