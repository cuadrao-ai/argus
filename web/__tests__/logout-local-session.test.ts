import { describe, expect, test } from "bun:test";
import { createBrowserClient } from "@supabase/ssr";

import { revokeLocalProviderSession } from "../lib/argus-api";

describe("revokeLocalProviderSession", () => {
  test("a failed provider sign-out still drops the stored session, once", async () => {
    let signOuts = 0;
    let removed = 0;
    const result = await revokeLocalProviderSession({
      signOut: async () => {
        signOuts += 1;
        return { error: new Error("provider unavailable") };
      },
      stopAutoRefresh: async () => undefined,
      _removeSession: async () => {
        removed += 1;
      },
    });

    expect(result.error).toBeInstanceOf(Error);
    expect(signOuts).toBe(1);
    expect(removed).toBe(1);
  });

  test("a sign-out that throws still drops the stored session, once", async () => {
    let signOuts = 0;
    let removed = 0;
    const result = await revokeLocalProviderSession({
      signOut: async () => {
        signOuts += 1;
        throw new Error("network");
      },
      _removeSession: async () => {
        removed += 1;
      },
    });

    expect(result.error).toBeInstanceOf(Error);
    expect(signOuts).toBe(1);
    expect(removed).toBe(1);
  });

  test("a completed sign-out does not remove the session again", async () => {
    let removed = 0;
    const result = await revokeLocalProviderSession({
      signOut: async () => ({ error: null }),
      _removeSession: async () => {
        removed += 1;
      },
    });

    expect(result.error).toBeNull();
    expect(removed).toBe(0);
  });

  test("a rejected provider logout leaves no session the next page can read", async () => {
    const user = {
      id: "owner-1",
      aud: "authenticated",
      email: "owner-1@example.test",
      app_metadata: {},
      user_metadata: {},
      created_at: "2026-10-01T00:00:00.000Z",
    };
    const accessToken = [
      Buffer.from(JSON.stringify({ alg: "HS256" })).toString("base64url"),
      Buffer.from(JSON.stringify({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url"),
      "test-signature",
    ].join(".");
    let cookies: { name: string; value: string }[] = [];
    let logoutCalls = 0;
    const client = createBrowserClient("https://fixture.supabase.co", "fixture-anon", {
      isSingleton: false,
      auth: { detectSessionInUrl: false, autoRefreshToken: false, persistSession: true },
      global: {
        fetch: async (input) => {
          const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
          if (url.endsWith("/auth/v1/user")) return Response.json(user);
          if (url.includes("/auth/v1/logout")) {
            logoutCalls += 1;
            return new Response("unavailable", { status: 500 });
          }
          throw new Error(`Unexpected provider request ${url}`);
        },
      },
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

    const installed = await client.auth.setSession({
      access_token: accessToken,
      refresh_token: "refresh-token",
    });
    expect(installed.error).toBeNull();
    expect(cookies.length).toBeGreaterThan(0);

    const result = await revokeLocalProviderSession(client.auth);
    expect(result.error).toBeTruthy();
    expect(logoutCalls).toBe(1);
    expect((await client.auth.getSession()).data.session).toBeNull();
    expect(cookies).toEqual([]);
  });
});
