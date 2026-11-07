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

test("Business admission reads only the expected account's grants", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  session = { user: { id: "owner-b" }, access_token: "b-token" };
  const send = mock(async (_input, init) => {
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer b-token");
    expect(init?.credentials).toBe("omit");
    return Response.json({ spaces: [], closed_spaces: [] });
  }) as typeof fetch;
  globalThis.fetch = send;
  const { getBusinessDirectory } = await import("@/lib/business-api");
  await expect(getBusinessDirectory(undefined, "owner-a")).rejects.toThrow("Chat account changed");
  expect(send).not.toHaveBeenCalled();
  await expect(getBusinessDirectory(undefined, "owner-b")).resolves.toEqual({ spaces: [], closed_spaces: [] });
  expect(send).toHaveBeenCalledTimes(1);
});

test("retirement after credentials resolve blocks direct Business dispatch", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  const { captureBusinessNote, markBusinessAccessSeen, uploadBusinessReceipt, fetchBusinessReceiptSource } = await import("@/lib/business-api");
  const send = mock(async () => Response.json({}));
  globalThis.fetch = send as typeof fetch;
  const previous = readSession;
  try {
    for (const dispatch of [
      () => captureBusinessNote({ text: "private note" }, "capture-key"),
      () => markBusinessAccessSeen("old-grant"),
      () => uploadBusinessReceipt(new File(["receipt"], "receipt.pdf", { type: "application/pdf" }), false, "upload-key"),
      () => fetchBusinessReceiptSource("old-receipt"),
    ]) {
      const lookup = Promise.withResolvers<Awaited<ReturnType<typeof readSession>>>();
      readSession = () => lookup.promise;
      const request = dispatch();
      lookup.resolve({ data: { session }, error: null });
      queueMicrotask(invalidateBrowserAuth);
      await expect(request).rejects.toThrow("Browser session changed");
    }
    expect(send).not.toHaveBeenCalled();
  } finally { readSession = previous; }
});
