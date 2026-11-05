// Run in a fresh process so Supabase module mocks cannot affect other suites.
import { mock } from "bun:test";
import assert from "node:assert/strict";
let session: { user: { id: string }; access_token: string } | null = null;
let waitForSession: Promise<void> = Promise.resolve();
mock.module("../../../lib/supabase-client", () => ({ getSupabaseClient: () => ({ auth: { getSession: async () => { await waitForSession; return { data: { session }, error: null }; } } }) }));
const { createConversation, streamChatMessage } = await import("../../../lib/argus-api");
process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
const requests: RequestInit[] = [];
globalThis.fetch = (async (_url: unknown, init: RequestInit) => {
  requests.push(init);
  return new Response('data: [DONE]\n\n', { status: 200 });
}) as typeof fetch;
for (const send of [
  (signal?: AbortSignal) => createConversation("en", { expectedUserId: "account-a", signal }),
  (signal?: AbortSignal) => streamChatMessage("conversation-a", "private draft", "en", () => {}, [], { expectedUserId: "account-a", signal }),
]) {
  for (const next of [null, { user: { id: "account-b" }, access_token: "b-token" }]) {
    session = next;
    await assert.rejects(send(), { name: "ChatAccountChangedError" });
    assert.equal(requests.length, 0);
  }
  session = { user: { id: "account-a" }, access_token: "refreshed-a-token" };
  await send().catch(error => { if (!(error instanceof SyntaxError)) throw error; });
  assert.equal(requests.length, 1);
  assert.equal(new Headers(requests[0].headers).get("Authorization"), "Bearer refreshed-a-token");
  assert.equal(requests[0].credentials, "omit");
  requests.length = 0;
  let release!: () => void;
  waitForSession = new Promise(resolve => { release = resolve; });
  const abort = new AbortController();
  const pending = send(abort.signal);
  abort.abort();
  release();
  await assert.rejects(pending);
  assert.equal(requests.length, 0);
  waitForSession = Promise.resolve();
}
console.log("create and stream identity mismatch, logout, refresh, delayed abort passed");
