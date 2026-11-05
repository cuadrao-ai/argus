import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  disclosedCookieConcept,
  undisclosedCookies,
} from "../lib/browser-cookies";

const REPO_ROOT = join(import.meta.dir, "..", "..");

/** The name @supabase/ssr derives, built the way the library builds it. */
function supabaseCookieName(projectUrl: string): string {
  return `sb-${new URL(projectUrl).hostname.split(".")[0]}-auth-token`;
}

function backendCookieRegistry(): Record<string, string> {
  const source = readFileSync(
    join(REPO_ROOT, "src", "argus", "api", "browser_cookies.py"),
    "utf-8",
  );
  const block = source.match(
    /COOKIE_REGISTRY:\s*Final\[dict\[str,\s*str\]\]\s*=\s*\{([\s\S]*?)\n\}/,
  );
  if (!block) throw new Error("COOKIE_REGISTRY not found in the backend module");
  const registry: Record<string, string> = {};
  for (const entry of block[1].matchAll(/"([^"]+)"\s*:\s*"([^"]+)"/g)) {
    registry[entry[1]] = entry[2];
  }
  return registry;
}

describe("web cookie disclosure rules", () => {
  test("covers the name Supabase actually derives, including chunks", () => {
    // Chunking appends .0/.1 for sessions too large for one cookie
    // (@supabase/ssr chunker), so both shapes have to be covered.
    const base = supabaseCookieName("https://lgdhvepyrzbnscqssgqq.supabase.co");
    expect(base).toBe("sb-lgdhvepyrzbnscqssgqq-auth-token");
    expect(disclosedCookieConcept(base)).toBe("sign_in");
    expect(disclosedCookieConcept(`${base}.0`)).toBe("sign_in");
    expect(disclosedCookieConcept(`${base}.1`)).toBe("sign_in");
  });

  test("covers Cloudflare bot and challenge cookies", () => {
    for (const name of ["__cf_bm", "cf_clearance", "cf_chl_rc_i"]) {
      expect(disclosedCookieConcept(name), name).toBe("security");
    }
  });

  test("reports a cookie no rule covers, without throwing", () => {
    // A predicate, not a guard. A stale disclosure must never be able to break
    // sign-in, so this reports and CI fails instead of the request path.
    expect(disclosedCookieConcept("argus-undisclosed")).toBeNull();
    expect(undisclosedCookies(["sb-abc-auth-token", "argus-undisclosed"])).toEqual([
      "argus-undisclosed",
    ]);
  });

  test("covers every cookie the backend registry declares", () => {
    // The two registries describe one browser. A name the backend sets that no
    // web rule covers would pass the server adapter and fail observation.
    for (const name of Object.keys(backendCookieRegistry())) {
      expect(disclosedCookieConcept(name), name).not.toBeNull();
    }
  });

  test("covers the name this deployment's Supabase project will actually use", () => {
    // The previous version of this test only checked a hardcoded example ref,
    // so a naming change or a configured cookieOptions.name would not have
    // been caught before production. Derive from the configured URL instead.
    const configured = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const urls = [
      configured,
      // Refs seen in the wild: plain, and the hyphenated form.
      "https://lgdhvepyrzbnscqssgqq.supabase.co",
      "https://abc-def-123.supabase.co",
    ].filter((url): url is string => Boolean(url));

    for (const url of urls) {
      const name = supabaseCookieName(url);
      expect(disclosedCookieConcept(name), `${url} -> ${name}`).toBe("sign_in");
      expect(disclosedCookieConcept(`${name}.0`), `${url} chunk`).toBe(
        "sign_in",
      );
      expect(undisclosedCookies([name]), name).toEqual([]);
    }
  });

  test("accepts every name shape the auth libraries can derive", () => {
    // Enumerated from the packages rather than guessed: @supabase/ssr chunks
    // with `${key}.${i}`, and @supabase/auth-js derives
    // `${storageKey}-code-verifier` for PKCE. Missing the verifier once broke
    // password reset outright, back when this check could throw.
    const base = supabaseCookieName("https://lgdhvepyrzbnscqssgqq.supabase.co");
    for (const name of [
      base,
      `${base}.0`,
      `${base}-code-verifier`,
      `${base}-code-verifier.0`,
    ]) {
      expect(disclosedCookieConcept(name), name).toBe("sign_in");
      expect(undisclosedCookies([name]), name).toEqual([]);
    }
  });

  test("the password-reset path's cookies are all disclosed", () => {
    // app/api/auth/recovery/route.ts calls createClient(), then
    // resetPasswordForEmail, which writes the PKCE verifier. The disclosure
    // has to cover every name that flow produces.
    const route = readFileSync(
      join(import.meta.dir, "..", "app", "api", "auth", "recovery", "route.ts"),
      "utf-8",
    );
    expect(route).toContain("@/lib/supabase-server");

    const configured =
      process.env.NEXT_PUBLIC_SUPABASE_URL ??
      "https://lgdhvepyrzbnscqssgqq.supabase.co";
    const verifier = `${supabaseCookieName(configured)}-code-verifier`;
    expect(undisclosedCookies([verifier])).toEqual([]);
  });

  test("no code customizes the Supabase cookie name behind the registry's back", () => {
    // cookieOptions.name would replace the derived name entirely, so the
    // patterns above would stop describing reality. If this ever becomes
    // intentional, the chosen name has to join COOKIE_DISCLOSURE_RULES.
    for (const file of ["supabase-client.ts", "supabase-server.ts"]) {
      const source = readFileSync(
        join(import.meta.dir, "..", "lib", file),
        "utf-8",
      );
      expect(source, file).not.toContain("cookieOptions");
    }
  });

  test("the auth path carries no disclosure check that could break it", () => {
    // The regression this pins: asserting inside the adapter put a
    // documentation check on the critical path, and a missing rule broke
    // password reset. Enforcement belongs in CI, not in a user's request.
    const source = readFileSync(
      join(import.meta.dir, "..", "lib", "supabase-server.ts"),
      "utf-8",
    );
    expect(source).not.toContain("assertDisclosedCookie");
    expect(source).not.toContain("browser-cookies");
  });
});
