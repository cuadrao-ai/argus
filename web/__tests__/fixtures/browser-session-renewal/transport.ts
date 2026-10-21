// Fresh process isolates the real SDK client and transport module imports.
import assert from "node:assert/strict";
import { mock } from "bun:test";
import { createBrowserClient } from "@supabase/ssr";

process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
process.env.NEXT_PUBLIC_CUADRAO_API_URL = "http://127.0.0.1:9/api/v1";
const user = { id: "11111111-1111-4111-8111-111111111111", aud: "authenticated", email: "fixture@example.com", app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" };
const jwt = (expiry: number) => `${Buffer.from(JSON.stringify({ alg: "HS256" })).toString("base64url")}.${Buffer.from(JSON.stringify({ sub: user.id, exp: expiry })).toString("base64url")}.synthetic`;
const currentToken = jwt(Math.floor(Date.now() / 1000) + 3600);
const oldSession = { access_token: jwt(1), refresh_token: "persisted-refresh", expires_at: 1, expires_in: 3600, token_type: "bearer", user };
const savedCookies = [{ name: "sb-fixture-auth-token", value: `base64-${Buffer.from(JSON.stringify(oldSession)).toString("base64url")}` }];
// Persisted cookies are the only state carried across browser reconstruction.
let cookies = savedCookies.map(cookie => ({ ...cookie }));
let rejectRefresh = false;
let refreshes = 0;
let apiCalls = 0;
globalThis.fetch = async (input, init) => {
  const url = String(input);
  if (url.includes("/auth/v1/token?grant_type=refresh_token")) {
    refreshes++;
    assert.equal(JSON.parse(String(init?.body)).refresh_token, "persisted-refresh");
    return Response.json(rejectRefresh ? { error: "invalid_grant", error_description: "Invalid refresh token" } : { access_token: currentToken, refresh_token: "rotated-refresh", expires_in: 3600, token_type: "bearer", user }, { status: rejectRefresh ? 400 : 200 });
  }
  assert.equal(url, "http://127.0.0.1:9/api/v1/me");
  apiCalls++;
  assert.equal(new Headers(init?.headers).get("Authorization"), `Bearer ${currentToken}`);
  assert.equal(init?.credentials, "include");
  return Response.json({ id: user.id });
};
const rebuild = () => createBrowserClient("https://fixture.supabase.co", "synthetic-anon", {
  isSingleton: false,
  auth: { detectSessionInUrl: false, autoRefreshToken: false },
  cookies: {
    getAll: () => cookies,
    setAll: updates => { for (const update of updates) { cookies = cookies.filter(cookie => cookie.name !== update.name); if (update.value) cookies.push({ name: update.name, value: update.value }); } },
  },
});
let client = rebuild();
mock.module("../../../lib/supabase-client", () => ({ getSupabaseClient: () => client }));
const { apiFetch } = await import("../../../lib/argus-api-transport");
assert.deepEqual(await apiFetch("/me"), { id: user.id });
assert.equal(refreshes, 1);
assert.notDeepEqual(cookies, savedCookies);
client = rebuild();
assert.deepEqual(await apiFetch("/me"), { id: user.id });
assert.equal(refreshes, 1);
assert.equal(apiCalls, 2);
await client.auth.stopAutoRefresh();
cookies = savedCookies.map(cookie => ({ ...cookie }));
rejectRefresh = true;
client = rebuild();
await assert.rejects(apiFetch("/me"));
assert.equal(apiCalls, 2);
assert.equal(cookies.length, 0);
await client.auth.stopAutoRefresh();
