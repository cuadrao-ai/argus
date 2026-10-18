import assert from "node:assert/strict";
import { mock } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createBrowserClient } from "@supabase/ssr";

GlobalRegistrator.register({ url: "http://localhost" });

const user = (id: string) => ({
  id,
  aud: "authenticated",
  email: `${id}@example.test`,
  app_metadata: {},
  user_metadata: {},
  created_at: "2026-10-01T00:00:00Z",
});
const jwt = (id: string) =>
  `${Buffer.from(JSON.stringify({ alg: "HS256" })).toString("base64url")}.${Buffer.from(JSON.stringify({ sub: id, exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url")}.test-signature`;

globalThis.fetch = async (input) => {
  const url = String(input);
  if (url.endsWith("/auth/v1/user")) return Response.json(user("confirmed-owner"));
  if (url.includes("/auth/v1/logout")) return new Response(null, { status: 204 });
  throw new Error(`Unexpected fixture request ${new URL(url).pathname}`);
};

let cookies: { name: string; value: string }[] = [];
const client = createBrowserClient("https://fixture.supabase.co", "fixture-anon", {
  isSingleton: false,
  auth: { detectSessionInUrl: false, autoRefreshToken: false },
  cookies: {
    getAll: () => cookies,
    setAll: (updates) => {
      for (const update of updates) {
        cookies = cookies.filter((cookie) => cookie.name !== update.name);
        if (update.value) cookies.push({ name: update.name, value: update.value });
      }
    },
  },
});
const setSessionCalls: Array<{ access_token: string; refresh_token: string }> = [];
const originalSetSession = client.auth.setSession.bind(client.auth);
client.auth.setSession = async (currentSession) => {
  setSessionCalls.push(currentSession);
  return originalSetSession(currentSession);
};

mock.module("@/lib/supabase-client", () => ({ getSupabaseClient: () => client }));
mock.module("@/lib/argus-api", () => ({
  logoutFromApi: async () => {
    await client.auth.signOut({ scope: "local" });
    return { revocation: "complete", cookieSync: "cleared" };
  },
}));

const { completeAuthVerification } = await import("@/lib/auth-verification");

const accessToken = jwt("confirmed-owner");
window.history.replaceState(
  null,
  "",
  `/#access_token=${accessToken}&refresh_token=signup-refresh&type=signup`,
);
assert.equal(await completeAuthVerification(), "verified");
assert.equal(window.location.hash, "");
assert.equal(setSessionCalls.length, 1);
assert.equal(setSessionCalls[0]?.access_token, accessToken);
assert.equal(setSessionCalls[0]?.refresh_token, "signup-refresh");
assert.equal((await client.auth.getSession()).data.session?.user.id, "confirmed-owner");

for (const type of ["recovery", "magiclink", "invite", "email_change"]) {
  const before = setSessionCalls.length;
  window.history.replaceState(
    null,
    "",
    `/#access_token=${jwt("other-owner")}&refresh_token=other-refresh&type=${type}`,
  );
  assert.equal(await completeAuthVerification(), "failed", type);
  assert.equal(setSessionCalls.length, before, type);
  assert.equal(window.location.hash, "", type);
  assert.equal((await client.auth.getSession()).data.session, null, type);
}

window.history.replaceState(null, "", "/");
assert.equal(await completeAuthVerification(), "none");

await client.auth.stopAutoRefresh();
await GlobalRegistrator.unregister();
process.exit(0);
