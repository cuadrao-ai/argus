import assert from "node:assert/strict";
import { afterAll, beforeAll, beforeEach, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

// The real hook against a Supabase client whose auth events this test fires.
// Logging out signs out before the view clears, so the SIGNED_OUT the client
// reports while a conversion is pending must not be read as "your account changed".
type AuthListener = (event: string, session: { user: { id: string } } | null) => void;
let listener: AuthListener | null = null;
let currentSession: { user: { id: string } } | null = { user: { id: "user-1" } };
mock.module("@/lib/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: {
      onAuthStateChange: (next: AuthListener) => {
        listener = next;
        return { data: { subscription: { unsubscribe: () => { listener = null; } } } };
      },
      getSession: async () => ({ data: { session: currentSession }, error: null }),
    },
  }),
}));

// The session and the subscription are module state that the cases mutate: a
// case that ends signed out leaves the next one starting as a stranger.
beforeEach(() => {
  listener = null;
  currentSession = { user: { id: "user-1" } };
});

beforeAll(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount() {
  const React = await import("react");
  const { act } = React;
  const { createRoot } = await import("react-dom/client");
  const { useChatAccountBoundary } = await import("@/components/chat/useChatAccountBoundary");
  const scopes: (string | null)[] = [];
  let cleared = 0;
  let boundary: ReturnType<typeof useChatAccountBoundary> | null = null;
  const requests = { synchronizeAccountScope: (id: string | null) => { scopes.push(id); } } as unknown as Parameters<typeof useChatAccountBoundary>[1];
  function Harness() {
    boundary = useChatAccountBoundary("user-1", requests, () => { cleared += 1; });
    return React.createElement("p", { "data-testid": "state" }, boundary.expired ? "expired" : "live");
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(React.createElement(Harness)); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  assert.ok(listener, "the hook subscribed to auth changes");
  const fire = (session: { user: { id: string } } | null) => act(async () => { currentSession = session; listener?.(session ? "SIGNED_IN" : "SIGNED_OUT", session); });
  const state = () => host.querySelector('[data-testid="state"]')?.textContent;
  return { act, root, fire, state, scopes, cleared: () => cleared, boundary: () => boundary! };
}

describe("the account boundary around a sign-out the page itself started", () => {
  test("SIGNED_OUT after beginConversion is ignored; finishing with the next user re-scopes; a later stranger sign-out still invalidates", async () => {
    const page = await mount();
    assert.equal(page.state(), "live");
    await page.act(async () => { page.boundary().beginConversion(); });
    assert.deepEqual(page.scopes, [null], "the conversion itself drops the scope");
    await page.fire(null);
    assert.equal(page.state(), "live", "the sign-out this page started is not an account change");
    assert.equal(page.cleared(), 0);
    await page.act(async () => { page.boundary().finishConversion("user-2"); });
    assert.deepEqual(page.scopes, [null, "user-2"]);
    assert.equal(page.state(), "live");
    // With no conversion pending, a session that is not the owner's ends the view once.
    await page.fire({ user: { id: "user-3" } });
    assert.equal(page.state(), "expired");
    assert.equal(page.cleared(), 1);
    assert.deepEqual(page.scopes, [null, "user-2", null]);
    await page.fire(null);
    assert.equal(page.cleared(), 1, "invalidation happens once");
    await page.act(async () => page.root.unmount());
  });

  test("without a conversion, SIGNED_OUT invalidates: scope dropped, view cleared, expired shown", async () => {
    currentSession = { user: { id: "user-1" } };
    const page = await mount();
    await page.fire(null);
    assert.equal(page.state(), "expired");
    assert.equal(page.cleared(), 1);
    assert.deepEqual(page.scopes, [null]);
    await page.act(async () => page.root.unmount());
  });

  test("a conversion that ends without a user invalidates, as a failed sign-in must", async () => {
    currentSession = { user: { id: "user-1" } };
    const page = await mount();
    await page.act(async () => { page.boundary().beginConversion(); });
    await page.act(async () => { page.boundary().finishConversion(null); });
    assert.equal(page.state(), "expired");
    assert.equal(page.cleared(), 1);
    await page.act(async () => page.root.unmount());
  });
});
