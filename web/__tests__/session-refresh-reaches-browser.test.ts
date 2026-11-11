import { describe, expect, test } from "bun:test";
import { NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

import { proxy } from "../proxy";

const AUTH_URL = "http://project.example.test";
const ANON_KEY = "anon-key";
const STORAGE_KEY = "sb-project-auth-token";
const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  aud: "authenticated",
  role: "authenticated",
};

function jwt(exp: number): string {
  const header = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ sub: USER.id, exp })).toString("base64url");
  return `${header}.${payload}.sig`;
}

function sessionCookie(session: object): string {
  const encoded = `base64-${Buffer.from(JSON.stringify(session), "utf8").toString("base64url")}`;
  return `${STORAGE_KEY}=${encoded}`;
}

function readSession(value: string | undefined): { refresh_token?: string } | null {
  if (!value?.startsWith("base64-")) return null;
  const json = Buffer.from(value.slice("base64-".length), "base64url").toString("utf8");
  return JSON.parse(json) as { refresh_token?: string };
}

function sessionsFromSetCookie(response: Response): Array<{ refresh_token?: string }> {
  const headers = response.headers.getSetCookie?.() ?? [];
  return headers.flatMap((header) => {
    const pair = header.split(";", 1)[0] ?? "";
    const value = pair.slice(pair.indexOf("=") + 1);
    const session = readSession(value);
    return session ? [session] : [];
  });
}

function installAuth(refreshedToken: string) {
  const refreshes: Array<{ refresh_token?: string }> = [];
  const previous = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (url.includes("/token") && url.includes("grant_type=refresh_token")) {
      refreshes.push(JSON.parse(String(init?.body ?? "{}")) as { refresh_token?: string });
      return Response.json({
        access_token: refreshedToken,
        refresh_token: "refresh-new",
        expires_in: 3600,
        token_type: "bearer",
        user: USER,
      });
    }
    if (url.endsWith("/user")) {
      return Response.json(USER);
    }
    return new Response("unexpected auth request", { status: 500 });
  }) as typeof fetch;
  return {
    refreshes,
    restore() {
      globalThis.fetch = previous;
    },
  };
}

describe("server session refresh reaches the browser", () => {
  const previousUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const previousKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const previousMock = process.env.NEXT_PUBLIC_MOCK_AUTH;

  function useAuthEnv() {
    process.env.NEXT_PUBLIC_SUPABASE_URL = AUTH_URL;
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = ANON_KEY;
    delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  }

  function restoreEnv() {
    if (previousUrl === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    else process.env.NEXT_PUBLIC_SUPABASE_URL = previousUrl;
    if (previousKey === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    else process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = previousKey;
    if (previousMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = previousMock;
  }

  test("an expired session is refreshed onto the response and the following render", async () => {
    useAuthEnv();
    const refreshedToken = jwt(Math.floor(Date.now() / 1000) + 3600);
    const auth = installAuth(refreshedToken);
    try {
      const request = new NextRequest("https://app.example.test/biz", {
        headers: {
          cookie: sessionCookie({
            access_token: jwt(1),
            refresh_token: "refresh-old",
            expires_at: 1,
            expires_in: 3600,
            token_type: "bearer",
            user: USER,
          }),
        },
      });

      const response = await proxy(request);

      expect(auth.refreshes).toEqual([{ refresh_token: "refresh-old" }]);
      expect(sessionsFromSetCookie(response).map((session) => session.refresh_token)).toEqual([
        "refresh-new",
      ]);
      expect(readSession(request.cookies.get(STORAGE_KEY)?.value)?.refresh_token).toBe("refresh-new");

      let pageWrites = 0;
      const page = createServerClient(AUTH_URL, ANON_KEY, {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll() {
            pageWrites += 1;
            throw new Error("Cookies can only be modified in a Server Action or Route Handler.");
          },
        },
      });
      const user = await page.auth.getUser();

      expect(user.data.user?.id).toBe(USER.id);
      expect(auth.refreshes).toEqual([{ refresh_token: "refresh-old" }]);
      expect(pageWrites).toBe(0);
    } finally {
      auth.restore();
      restoreEnv();
    }
  });

  test("a current session is not rotated", async () => {
    useAuthEnv();
    const auth = installAuth(jwt(Math.floor(Date.now() / 1000) + 7200));
    try {
      const request = new NextRequest("https://app.example.test/biz", {
        headers: {
          cookie: sessionCookie({
            access_token: jwt(Math.floor(Date.now() / 1000) + 3600),
            refresh_token: "refresh-current",
            expires_at: Math.floor(Date.now() / 1000) + 3600,
            expires_in: 3600,
            token_type: "bearer",
            user: USER,
          }),
        },
      });

      const response = await proxy(request);

      expect(auth.refreshes).toEqual([]);
      expect(sessionsFromSetCookie(response)).toEqual([]);
    } finally {
      auth.restore();
      restoreEnv();
    }
  });
});
