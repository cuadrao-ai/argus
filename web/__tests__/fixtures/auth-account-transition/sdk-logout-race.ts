import assert from "node:assert/strict";
import { mock } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createBrowserClient } from "@supabase/ssr";
import { observeBrowserAuth } from "@/lib/browser-auth-generation";
GlobalRegistrator.register({ url: "http://localhost" });
process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
const user = (id: string) => ({ id, aud: "authenticated", email: `${id}@example.test`, app_metadata: {}, user_metadata: {}, created_at: "2026-10-01T00:00:00Z" });
const jwt = (id: string) => `${Buffer.from(JSON.stringify({ alg: "HS256" })).toString("base64url")}.${Buffer.from(JSON.stringify({ sub: id, exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url")}.test-signature`;
let cookies: { name: string; value: string }[] = [];
let apiCookie = "old-api-cookie";
let release!: () => void;
let announce!: () => void;
let waitForUser: Promise<void> | null = null;
let waitForCookieClear: Promise<void> | null = null;
globalThis.fetch = async (input) => {
  const url = String(input);
  if (url.endsWith("/auth/v1/user")) {
    if (waitForUser) { announce(); await waitForUser; }
    return Response.json(user("new-owner"));
  }
  if (url.includes("/auth/v1/logout?scope=local")) return new Response(null, { status: 204 });
  if (url.endsWith("/auth/logout")) {
    const pendingClear = waitForCookieClear;
    waitForCookieClear = null;
    if (pendingClear) { announce(); await pendingClear; }
    apiCookie = ""; return Response.json({ success: true });
  }
  throw new Error(`Unexpected fixture request ${new URL(url).pathname}`);
};
const client = createBrowserClient("https://fixture.supabase.co", "fixture-anon", {
  isSingleton: false,
  auth: { detectSessionInUrl: false, autoRefreshToken: false },
  cookies: {
    getAll: () => cookies,
    setAll: updates => { for (const update of updates) { cookies = cookies.filter(cookie => cookie.name !== update.name); if (update.value) cookies.push({ name: update.name, value: update.value }); } },
  },
});
client.auth.onAuthStateChange((_event, session) => observeBrowserAuth(session?.user.id ?? null));
mock.module("@/lib/supabase-client", () => ({ getSupabaseClient: () => client }));
const { persistBrowserSession, logoutFromApi } = await import("@/lib/argus-api");
const { completeAuthVerification } = await import("@/lib/auth-verification");
for (const mode of ["login", "verification"]) {
  waitForUser = null;
  await client.auth.setSession({ access_token: jwt("old-owner"), refresh_token: "old-refresh" });
  apiCookie = "old-api-cookie";
  const started = new Promise<void>(resolve => { announce = resolve; });
  waitForUser = new Promise<void>(resolve => { release = resolve; });
  window.history.replaceState(null, "", mode === "verification" ? `/#access_token=${jwt("new-owner")}&refresh_token=new-refresh&type=signup` : "/");
  const install = mode === "verification" ? completeAuthVerification() : persistBrowserSession({ user: user("new-owner"), session: { access_token: jwt("new-owner"), refresh_token: "new-refresh" } } as never);
  await started;
  const logout = logoutFromApi();
  release();
  const [installation, signedOut] = await Promise.allSettled([install, logout]);
  assert.equal(signedOut.status, "fulfilled");
  if (mode === "login") assert.equal(installation.status, "rejected");
  else assert.deepEqual(installation, { status: "fulfilled", value: "failed" });
  assert.equal((await client.auth.getSession()).data.session, null, mode);
  assert.equal(cookies.length, 0, mode);
  assert.equal(apiCookie, "", mode);
}
waitForUser = null;
await client.auth.setSession({ access_token: jwt("old-owner"), refresh_token: "old-refresh" });
const clearing = new Promise<void>(resolve => { announce = resolve; });
waitForCookieClear = new Promise<void>(resolve => { release = resolve; });
window.history.replaceState(null, "", `/#access_token=${jwt("new-owner")}&refresh_token=new-refresh&type=signup`);
const verification = completeAuthVerification();
await clearing;
await logoutFromApi();
release();
assert.equal(await verification, "failed", "later logout cancels verification before SDK installation");
assert.equal((await client.auth.getSession()).data.session, null);
assert.equal(cookies.length, 0);
assert.equal(apiCookie, "");
await client.auth.stopAutoRefresh();
await GlobalRegistrator.unregister();

process.exit(0);
