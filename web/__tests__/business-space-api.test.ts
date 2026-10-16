import { afterEach, describe, expect, test } from "bun:test";

import { startBusinessSpace } from "@/lib/business-api";
import { invalidateBrowserAuth } from "@/lib/browser-auth-generation";
import { setChosenGrant } from "@/lib/business-grant";
import { liveBusinessDataSource, withBusinessSpace } from "@/components/business-app/business-data";

type Call = { url: string; method: string; body: unknown };
const space = { id: "space-1", name: "Mi negocio" };
const missing = { status: 404, body: { code: "business_space_missing" } };

function respond(...replies: { status: number; body: unknown }[]): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    const reply = replies.shift();
    if (!reply) throw new Error("Unexpected request");
    return new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  return calls;
}

describe("starting the Business space", () => {
  const originalFetch = globalThis.fetch;
  const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    setChosenGrant(null);
    if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  });

  test("each page reload reads an existing owner space without a POST", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const calls = respond({ status: 200, body: space }, { status: 200, body: space });
    for (let page = 0; page < 2; page++) {
      const source = withBusinessSpace(liveBusinessDataSource, () => "es-419");
      expect(await source.ensureSpace("es-419")).toEqual(space);
    }
    expect(calls.map((call) => call.method)).toEqual(["GET", "GET"]);
    expect(calls.every((call) => call.url.endsWith("/business/space"))).toBe(true);
  });

  test.each([201, 200])("concurrent first-load readers share one creation, including a server race returning %i", async (status) => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const calls = respond(missing, { status, body: space });
    const source = withBusinessSpace(liveBusinessDataSource, () => "es-419");
    expect(await Promise.all([source.ensureSpace("es-419"), source.ensureSpace("es-419")])).toEqual([space, space]);
    expect(await source.ensureSpace("en")).toEqual(space);
    expect(calls.map((call) => call.method)).toEqual(["GET", "POST"]);
    expect(calls[1].body).toEqual({ language: "es-419" });
  });

  test.each([
    [403, "business_grant_not_live"],
    [403, "business_permission_denied"],
    [500, "internal_error"],
    [404, "business_unavailable"],
  ])("a read refusal %i %s never creates a space", async (status, code) => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const calls = respond({ status, body: { code } });
    await expect(startBusinessSpace("en")).rejects.toMatchObject({ status, code });
    expect(calls.map((call) => call.method)).toEqual(["GET"]);
  });

  test("a selected accountant Business bypasses owner creation when switching back and forth", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const calls = respond({ status: 200, body: space });
    const source = withBusinessSpace(liveBusinessDataSource, () => "en");
    setChosenGrant("00000000-0000-4000-8000-000000000001");
    await source.ensureSpace("en");
    expect(calls).toHaveLength(0);
    setChosenGrant(null);
    expect(await source.ensureSpace("en")).toEqual(space);
    setChosenGrant("00000000-0000-4000-8000-000000000001");
    await source.ensureSpace("en");
    expect(calls.map((call) => call.method)).toEqual(["GET"]);
  });

  test("a new signed-in account reads its own space instead of reusing the old bootstrap", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const other = { id: "space-2", name: "Other business" };
    const calls = respond({ status: 200, body: space }, missing, { status: 201, body: other });
    const source = withBusinessSpace(liveBusinessDataSource, () => "en");
    expect(await source.ensureSpace("en")).toEqual(space);
    invalidateBrowserAuth();
    expect(await source.ensureSpace("en")).toEqual(other);
    expect(calls.map((call) => call.method)).toEqual(["GET", "GET", "POST"]);
  });

  test("logout during the absence read prevents creation for the next account", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const calls = respond(missing);
    const fetchReply = globalThis.fetch;
    globalThis.fetch = (async (...args: Parameters<typeof fetch>) => {
      const reply = await fetchReply(...args);
      invalidateBrowserAuth();
      return reply;
    }) as typeof fetch;
    await expect(startBusinessSpace("en")).rejects.toThrow("Browser session changed");
    expect(calls.map((call) => call.method)).toEqual(["GET"]);
  });
});
