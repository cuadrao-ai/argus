import assert from "node:assert/strict";
import { mock, test } from "bun:test";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";

type Listener = (event: string, session: { user: { id: string } } | null) => void;
let notify!: Listener;
mock.module("@supabase/ssr", () => ({
  createBrowserClient: () => ({ auth: {
    onAuthStateChange: (listener: Listener) => { notify = listener; },
    getSession: async () => ({ data: { session: null }, error: null }),
  } }),
}));

test("only confirmed identity changes clear the selected Business", async () => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "http://localhost";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "test";
  const { getSupabaseClient } = await import("@/lib/supabase-client");
  getSupabaseClient();
  notify("SIGNED_IN", { user: { id: "current" } });
  setChosenGrant("test-grant");
  const current = browserAuthGeneration();
  notify("INITIAL_SESSION", null);
  notify("INITIAL_SESSION", { user: { id: "older" } });
  assert.equal(getChosenGrant(), "test-grant");
  assert.doesNotThrow(() => requireBrowserAuthGeneration(current));
  notify("SIGNED_OUT", null);
  assert.equal(getChosenGrant(), "test-grant", "an event during a failed refresh must not erase the remembered Business");
  assert.throws(() => requireBrowserAuthGeneration(current), /Browser session changed/);
  const { authenticatedRequestHeaders } = await import("@/lib/chat-auth-ownership");
  await authenticatedRequestHeaders();
  assert.equal(getChosenGrant(), null, "a settled missing session clears the remembered Business");
  notify("SIGNED_IN", { user: { id: "current" } });
  setChosenGrant("test-grant");
  notify("SIGNED_IN", { user: { id: "different" } });
  assert.equal(getChosenGrant(), null, "a confirmed different user clears the remembered Business");
});
