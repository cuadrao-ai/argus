import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { signupWithEmail } from "../lib/argus-api";
import { bootstrapGuest, resetGuestBootstrapRuntime } from "../lib/guest-session";
import { captureLandingIntent } from "../lib/landing-intent";

const root = join(import.meta.dir, "..");
const originalFetch = globalThis.fetch;

function installStorage() {
  const local = new Map<string, string>();
  const session = new Map<string, string>();
  (globalThis as { window?: unknown }).window = {
    localStorage: {
      getItem: (key: string) => local.get(key) ?? null,
      setItem: (key: string, value: string) => {
        local.set(key, value);
      },
      removeItem: (key: string) => {
        local.delete(key);
      },
    },
    sessionStorage: {
      getItem: (key: string) => session.get(key) ?? null,
      setItem: (key: string, value: string) => {
        session.set(key, value);
      },
      removeItem: (key: string) => {
        session.delete(key);
      },
    },
    location: { search: "", pathname: "/" },
    dispatchEvent: () => true,
  };
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  resetGuestBootstrapRuntime();
  delete (globalThis as { window?: unknown }).window;
});

beforeEach(() => {
  installStorage();
});

describe("landing attribution on auth requests", () => {
  test("guest bootstrap and signup send the stored object and omit it when empty", async () => {
    const bodies: Record<string, unknown>[] = [];
    globalThis.fetch = (async (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return new Response(
        JSON.stringify({ authenticated: true, account_kind: "guest", user: { id: "g1" } }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;

    await bootstrapGuest({ captcha_token: "token", language: "en" });
    expect(bodies[0]).toEqual({ captcha_token: "token", language: "en" });
    expect(bodies[0]).not.toHaveProperty("age_confirmed_at");
    expect(bodies[0]).not.toHaveProperty("attribution");

    captureLandingIntent("utm_campaign=x&starter=backtest", "/");
    await bootstrapGuest({ captcha_token: "token", language: "en" });
    expect(bodies[1]).toEqual({
      captcha_token: "token",
      language: "en",
      attribution: {
        utm_campaign: "x",
        starter: "backtest",
        landing_path: "/",
      },
    });

    globalThis.fetch = (async (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return new Response(JSON.stringify({ user: { id: "u1" }, session: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    await signupWithEmail({
      email: "alpha@example.com",
      password: "password123",
      language: "en",
      age_confirmed_at: "2026-10-17T12:00:00.000Z",
    });
    expect(bodies.at(-1)).toMatchObject({
      email: "alpha@example.com",
      attribution: {
        utm_campaign: "x",
        starter: "backtest",
        landing_path: "/",
      },
    });
  });

  test("a shared-thread landing path survives into bootstrap and signup", async () => {
    const bodies: Record<string, unknown>[] = [];
    globalThis.fetch = (async (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return new Response(
        JSON.stringify({ authenticated: true, account_kind: "guest", user: { id: "g1" } }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;

    captureLandingIntent("utm_campaign=x", "/r/abcdefghijklmnopqrstuvwx");
    await bootstrapGuest({ captcha_token: "token", language: "en" });
    expect(bodies[0]).toMatchObject({
      attribution: {
        utm_campaign: "x",
        landing_path: "/r/abcdefghijklmnopqrstuvwx",
      },
    });

    globalThis.fetch = (async (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return new Response(JSON.stringify({ user: { id: "u1" }, session: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    await signupWithEmail({
      email: "shared@example.com",
      password: "password123",
      language: "en",
      age_confirmed_at: "2026-10-17T12:00:00.000Z",
    });
    expect(bodies.at(-1)).toMatchObject({
      attribution: {
        utm_campaign: "x",
        landing_path: "/r/abcdefghijklmnopqrstuvwx",
      },
    });
  });

  test("guest account signup keeps extra=forbid by not attaching attribution", () => {
    const guestApi = readFileSync(join(root, "lib/guest-api.ts"), "utf-8");
    expect(guestApi).toContain('"/auth/guest/signup"');
    expect(guestApi).not.toContain("attributionPayload");
    expect(guestApi).not.toContain("attribution");
  });
});
