import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createContext, type ReactNode } from "react";
let lifecycleMode: "open" | "off" | "closed" = "open";
let listener: (event: string, session: { user: { id: string } } | null) => void = () => {};
let releaseInitial!: (result: unknown) => void;
mock.module("@/lib/supabase-client", () => ({ getSupabaseClient: () => ({ auth: {
  onAuthStateChange: (next: typeof listener) => { listener = next; return { data: { subscription: { unsubscribe: () => {} } } }; },
  getSession: () => new Promise(resolve => { releaseInitial = resolve; }),
} }) }));
mock.module("@/lib/business-api", () => ({ getBusinessDirectory: async () => { if (lifecycleMode === "off") throw { code: "business_unavailable" }; return { spaces: lifecycleMode === "open" ? [{ role: "owner" }] : [], closed_spaces: lifecycleMode === "closed" ? [{ role: "owner" }] : [] }; } }));
mock.module("@/components/business-app/BusinessWorkspace", () => ({
  BusinessContext: createContext(null),
  BusinessWorkspaceProvider: ({ children }: { children: ReactNode }) => children,
}));
mock.module("@/components/business-app/BusinessNamingProvider", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/business-app/BusinessLifecycleControls", () => ({ default: () => <p>Closed controls</p> }));
mock.module("@/components/business-app/BusinessLifecycleEntry", () => ({ default: () => null }));
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
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  Object.assign(liveBusinessDataSource, { consent: async (version: string) => ({ version, accepted_at: "2026-10-18T12:00:00.000Z" }) });
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<BusinessApp />));
  assert.equal(host.querySelector("input"), null);
  await act(async () => listener("SIGNED_IN", { user: { id: "old" } }));
  await act(async () => { await new Promise((done) => setTimeout(done, 50)); });
  const oldInput = host.querySelector("input")!;
  oldInput.value = "Old private draft";
  await act(async () => listener("TOKEN_REFRESHED", { user: { id: "old" } }));
  assert.equal(host.querySelector("input"), oldInput);
  await act(async () => listener("SIGNED_IN", { user: { id: "new" } }));
  await act(async () => { await new Promise((done) => setTimeout(done, 50)); });
  const newInput = host.querySelector("input")!;
  assert.notEqual(newInput, oldInput);
  assert.equal(newInput.value, "");
  await act(async () => releaseInitial({ data: { session: { user: { id: "old" } } }, error: null }));
  assert.equal(host.querySelector("input"), newInput);
  await act(async () => listener("SIGNED_OUT", null));
  assert.equal(host.querySelector("input"), null);
  await act(async () => root.unmount());
});

test("readiness denial keeps normal Business mounted; closed-only owner never starts workspace bootstrap", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  lifecycleMode = "off";
  await act(async () => root.render(<BusinessApp key="off" />));
  assert.ok(host.querySelector("input"));
  lifecycleMode = "closed";
  await act(async () => root.render(<BusinessApp key="closed" />));
  assert.equal(host.querySelector("input"), null);
  assert.ok(host.textContent?.includes("Closed controls"));
  await act(async () => root.unmount()); host.remove();
});

test("a wake check failure retires the workspace and offers a real retry", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  lifecycleMode = "open";
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  Object.assign(liveBusinessDataSource, { consent: async (version: string) => ({ version, accepted_at: "2026-10-18T12:00:00.000Z" }) });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<BusinessApp />));
  try {
    await act(async () => listener("SIGNED_IN", { user: { id: "old" } }));
    assert.ok(host.querySelector("input"), "the signed-in workspace is mounted");
    const initial = releaseInitial;
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    assert.notEqual(releaseInitial, initial, "waking the Business workspace checks the session");
    await act(async () => releaseInitial({ data: { session: null }, error: new Error("offline") }));
    assert.equal(host.querySelector("input"), null, "an unverifiable session retires the private workspace");
    const retry = host.querySelector("button");
    assert.ok(retry, "the recovery screen offers retry");
    const failed = releaseInitial;
    await act(async () => { retry.click(); });
    assert.notEqual(releaseInitial, failed, "retry actually checks the session");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
