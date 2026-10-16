import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
let listener: (event: string, session: { user: { id: string } } | null) => void = () => {};
let releaseInitial!: (result: unknown) => void;
mock.module("@/lib/supabase-client", () => ({ getSupabaseClient: () => ({ auth: {
  onAuthStateChange: (next: typeof listener) => { listener = next; return { data: { subscription: { unsubscribe: () => {} } } }; },
  getSession: () => new Promise(resolve => { releaseInitial = resolve; }),
} }) }));
mock.module("@/components/business-app/BusinessWorkspace", () => ({ BusinessWorkspaceProvider: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/business-app/BusinessNamingProvider", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/chat/ChatInterface", () => ({ default: () => <input aria-label="Account draft" defaultValue="" /> }));
mock.module("@/components/chat/ConversationShellGuard", () => ({ default: () => null }));
mock.module("@/components/business-app/ConversationUnavailableNotice", () => ({ default: () => null }));
beforeAll(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(() => GlobalRegistrator.unregister());
test("account changes discard the old workspace, and late initial session cannot restore it", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<BusinessApp />));
  assert.equal(host.querySelector("input"), null);
  await act(async () => listener("SIGNED_IN", { user: { id: "old" } }));
  const oldInput = host.querySelector("input")!;
  oldInput.value = "Old private draft";
  await act(async () => listener("TOKEN_REFRESHED", { user: { id: "old" } }));
  assert.equal(host.querySelector("input"), oldInput);
  await act(async () => listener("SIGNED_IN", { user: { id: "new" } }));
  const newInput = host.querySelector("input")!;
  assert.notEqual(newInput, oldInput);
  assert.equal(newInput.value, "");
  await act(async () => releaseInitial({ data: { session: { user: { id: "old" } } }, error: null }));
  assert.equal(host.querySelector("input"), newInput);
  await act(async () => listener("SIGNED_OUT", null));
  assert.equal(host.querySelector("input"), null);
  await act(async () => root.unmount());
});
