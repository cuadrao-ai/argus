import { afterEach, expect, mock, test } from "bun:test";
import { browserAuthGeneration, invalidateBrowserAuth, observeBrowserAuth } from "@/lib/browser-auth-generation";
let session: { user: { id: string }; access_token: string } | null = { user: { id: "owner-a" }, access_token: "a-token" };
let readSession = async () => ({ data: { session }, error: null });
mock.module("@/lib/supabase-client", () => ({ getSupabaseClient: () => ({ auth: { getSession: () => readSession() } }) }));
const originalFetch = globalThis.fetch;
const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
afterEach(() => { globalThis.fetch = originalFetch; process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });
test("late workspace and conversation responses are rejected after account changes", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  const { apiFetch } = await import("@/lib/argus-api-transport");
  for (const path of ["/business/workspace", "/conversations?surface=business"]) {
    let release!: (response: Response) => void;
    globalThis.fetch = mock(() => new Promise<Response>(resolve => { release = resolve; })) as typeof fetch;
    const pending = apiFetch(path);
    await new Promise(resolve => setTimeout(resolve, 0));
    invalidateBrowserAuth();
    release(Response.json({ old: true }));
    await expect(pending).rejects.toThrow("Browser session changed");
  }
});
test("same-owner token refresh does not invalidate reads", () => {
  observeBrowserAuth("owner-a");
  const generation = browserAuthGeneration();
  observeBrowserAuth("owner-a");
  expect(browserAuthGeneration()).toBe(generation);
});
test("a signed-out browser cannot fall back to stale API cookies", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  session = null;
  globalThis.fetch = mock(async (_input, init) => {
    expect(init?.credentials).toBe("omit");
    return Response.json({ code: "unauthorized" }, { status: 401 });
  }) as typeof fetch;
  const { apiFetch } = await import("@/lib/argus-api-transport");
  await expect(apiFetch("/me")).rejects.toMatchObject({ status: 401 });
});
test("a real forbidden response remains forbidden", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  session = { user: { id: "owner-b" }, access_token: "b-token" };
  globalThis.fetch = mock(async () => Response.json({ code: "business_owner_required" }, { status: 403 })) as typeof fetch;
  const { apiFetch } = await import("@/lib/argus-api-transport");
  await expect(apiFetch("/conversations?surface=business")).rejects.toMatchObject({ status: 403, code: "business_owner_required" });
});

test("an identity switch during session lookup cannot dispatch old headers", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  const previous = readSession;
  let release!: (value: Awaited<ReturnType<typeof readSession>>) => void;
  readSession = () => new Promise(resolve => { release = resolve; });
  let dispatched = false;
  globalThis.fetch = mock(async () => { dispatched = true; return Response.json({}); }) as typeof fetch;
  const { apiFetch } = await import("@/lib/argus-api-transport");
  const request = apiFetch("/business/workspace");
  invalidateBrowserAuth();
  release({ data: { session: { user: { id: "old" }, access_token: "old-token" } }, error: null });
  await expect(request).rejects.toThrow("Browser session changed");
  expect(dispatched).toBe(false);
  readSession = previous;
});
