import { describe, expect, test } from "bun:test";
import { SIGNUP_CONSENT_VERSION } from "../lib/forms/config";
import { WindowLimiter } from "../lib/forms/rate-limit";
import { handleSignup, SIGNUP_TABLE } from "../lib/forms/signup";
import { emailDigest } from "../lib/forms/validation";
import { CONFIG, captureLogs, jsonRequest, recordingFetch } from "./forms-support";

const stored = () => new Response(null, { status: 201 });

function deps(respond = stored, config = CONFIG) {
  const store = recordingFetch(respond);
  const now = () => 1_000_000;
  return {
    store,
    deps: {
      config,
      fetch: store.fetch,
      perClient: new WindowLimiter(8, 600_000, now),
      overall: new WindowLimiter(300, 3_600_000, now),
    },
  };
}

const signup = (overrides: Record<string, unknown> = {}) =>
  jsonRequest("/api/signups", {
    email: " Ana@Example.INVALID ",
    locale: "es",
    website: "",
    ...overrides,
  });

describe("signup storage", () => {
  test("registers only after the database accepts the row", async () => {
    const { store, deps: d } = deps();
    const response = await handleSignup(signup(), d);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "registered" });
    expect(store.calls).toHaveLength(1);
    const [call] = store.calls;
    expect(call.url).toBe(
      `https://project.supabase.test/rest/v1/${SIGNUP_TABLE}?on_conflict=email_digest`,
    );
    const headers = call.init.headers as Record<string, string>;
    expect(headers.Prefer).toBe("resolution=ignore-duplicates,return=minimal");
    expect(headers.apikey).toBe("service-role-test-key");
    expect(JSON.parse(String(call.init.body))).toEqual({
      email_digest: emailDigest("ana@example.invalid"),
      email: "ana@example.invalid",
      language: "es",
      consent_version: SIGNUP_CONSENT_VERSION,
      source: "personal-page",
    });
  });

  test("a new, a repeated and a removed address get the same answer", async () => {
    // The database ignores the conflicting row and still answers 201, so the
    // route cannot tell the three cases apart and neither can the visitor.
    const answers: unknown[] = [];
    for (const email of ["new@example.invalid", "new@example.invalid", "removed@example.invalid"]) {
      const { deps: d } = deps();
      const response = await handleSignup(signup({ email }), d);
      answers.push([response.status, await response.json()]);
    }
    expect(new Set(answers.map((answer) => JSON.stringify(answer))).size).toBe(1);
  });

  test("a database error is unavailable, never registered", async () => {
    const { deps: d } = deps(() => new Response("{}", { status: 500 }));
    const response = await handleSignup(signup(), d);
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "unavailable" });
  });

  test("a network failure is unavailable", async () => {
    const { deps: d } = deps(() => {
      throw new TypeError("fetch failed");
    });
    expect((await handleSignup(signup(), d)).status).toBe(503);
  });

  test("missing configuration is unavailable and calls nothing", async () => {
    const { store, deps: d } = deps(stored, { ...CONFIG, supabaseServiceKey: null });
    expect((await handleSignup(signup(), d)).status).toBe(503);
    expect(store.calls).toHaveLength(0);
  });

  test("the credential never appears in a response", async () => {
    const { deps: d } = deps();
    const response = await handleSignup(signup(), d);
    expect(JSON.stringify([...response.headers])).not.toContain("service-role-test-key");
    expect(await response.text()).not.toContain("service-role-test-key");
  });
});

describe("signup input handling", () => {
  test("invalid input returns 400 and calls nothing", async () => {
    const { store, deps: d } = deps();
    const response = await handleSignup(signup({ email: "nope" }), d);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid", fields: ["email"] });
    expect(store.calls).toHaveLength(0);
  });

  test("a filled honeypot looks registered but stores nothing", async () => {
    const { store, deps: d } = deps();
    const response = await handleSignup(signup({ website: "https://spam.invalid" }), d);
    expect(response.status).toBe(200);
    expect(store.calls).toHaveLength(0);
  });

  test("rejects another origin", async () => {
    const { deps: d } = deps();
    const response = await handleSignup(
      jsonRequest("/api/signups", { email: "a@example.invalid", locale: "es" }, { origin: "https://evil.invalid" }),
      d,
    );
    expect(response.status).toBe(403);
  });

  test("limits a client after eight attempts", async () => {
    const { deps: d } = deps();
    const statuses: number[] = [];
    for (let attempt = 0; attempt < 9; attempt += 1) {
      statuses.push((await handleSignup(signup({ email: `p${attempt}@example.invalid` }), d)).status);
    }
    expect(statuses.slice(0, 8).every((status) => status === 200)).toBe(true);
    expect(statuses[8]).toBe(429);
  });
});

describe("signup shared allowance", () => {
  const from = (ip: string, body: Record<string, unknown>) =>
    jsonRequest("/api/signups", { locale: "es", ...body }, { "x-forwarded-for": ip });

  test("invalid and honeypot requests do not spend the shared allowance", async () => {
    const { deps: d } = deps();
    const tight = { ...d, overall: new WindowLimiter(1, 3_600_000, () => 1_000_000) };
    for (let attempt = 0; attempt < 6; attempt += 1) {
      await handleSignup(from(`192.0.2.${attempt}`, { email: "nope" }), tight);
      await handleSignup(from(`198.51.100.${attempt}`, { email: "a@example.invalid", website: "x" }), tight);
    }
    expect((await handleSignup(from("203.0.113.1", { email: "one@example.invalid" }), tight)).status).toBe(200);
    expect((await handleSignup(from("203.0.113.2", { email: "two@example.invalid" }), tight)).status).toBe(429);
  });
});

describe("signup logging", () => {
  test("never writes the address", async () => {
    const logs = captureLogs();
    try {
      await handleSignup(signup(), deps().deps);
      await handleSignup(signup(), deps(() => new Response("", { status: 500 })).deps);
    } finally {
      logs.restore();
    }
    const written = logs.lines.join("\n");
    expect(written).toContain("signup_stored");
    expect(written).not.toContain("example.invalid");
    expect(written).not.toContain(emailDigest("ana@example.invalid"));
  });
});
