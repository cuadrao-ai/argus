import { describe, expect, test } from "bun:test";

import {
  classifyFailure,
  emailRetrySeconds,
  nextQuietRetryMs,
  QUIET_UNAVAILABLE_MS,
  referenceCode,
  serverRequestReference,
  runQuietRetries,
  sessionEndedLoginPath,
  sessionEndedNotice,
} from "@/lib/failure-screen";

describe("classifyFailure", () => {
  test("reads each status once", () => {
    expect(classifyFailure({ status: 401 })).toBe("session_ended");
    expect(classifyFailure({ status: 403 })).toBe("closed");
    expect(classifyFailure({ status: 403, code: "business_grant_not_live" })).toBe("removed");
    expect(classifyFailure({ status: 429 })).toBe("rate_limited");
    expect(classifyFailure({ status: 503 })).toBe("unavailable");
    expect(classifyFailure({ status: 500 })).toBe("server");
    expect(classifyFailure(new TypeError("Failed to fetch"), { fetch: true })).toBe("offline");
    expect(classifyFailure(new Error("nope"), { online: false })).toBe("offline");
    expect(classifyFailure(new Error("nope"))).toBe("other");
  });
});

describe("referenceCode", () => {
  test("keeps a safe digest and never the thrown message", () => {
    expect(referenceCode({ digest: "abc123" })).toBe("abc123");
    expect(referenceCode({ digest: "provider said no" })).toMatch(/^c[0-9a-f]{8}$/);
    expect(referenceCode(new Error("framework blew up"))).not.toContain("framework");
  });
});

describe("emailRetrySeconds", () => {
  test("uses the header and falls back to a minute", () => {
    expect(emailRetrySeconds("45")).toBe(45);
    expect(emailRetrySeconds(null)).toBe(60);
    expect(emailRetrySeconds("nope")).toBe(60);
  });
});

describe("sessionEndedLoginPath", () => {
  test("sends the person to login with the return path and the notice", () => {
    const path = sessionEndedLoginPath("/biz", "?receipt=r1");
    const params = new URLSearchParams(path.slice(2));
    expect(path.startsWith("/?")).toBe(true);
    expect(params.get("auth")).toBe("login");
    expect(params.get("notice")).toBe("session_ended");
    expect(params.get("return_to")).toBe("/biz?receipt=r1");
    expect(sessionEndedNotice(path.slice(1))).toBe(true);
    expect(sessionEndedNotice("?auth=login")).toBe(false);
  });

  test("does not invent a return path for a page that cannot be returned to", () => {
    const path = sessionEndedLoginPath("/account/security", "");
    expect(new URLSearchParams(path.slice(2)).has("return_to")).toBe(false);
  });
});

describe("runQuietRetries", () => {
  test("retries a 503 until the budget ends, then throws, and does not retry anything else", async () => {
    let now = 0;
    const waits: number[] = [];
    const clock = {
      now: () => now,
      sleep: async (ms: number) => {
        waits.push(ms);
        now += ms;
      },
    };
    let calls = 0;
    await expect(runQuietRetries(async () => {
      calls += 1;
      throw Object.assign(new Error("down"), { status: 503 });
    }, clock)).rejects.toMatchObject({ status: 503 });
    expect(calls).toBeGreaterThan(1);
    expect(now).toBeGreaterThanOrEqual(QUIET_UNAVAILABLE_MS);
    expect(waits.every((wait) => wait > 0 && wait <= 2_000)).toBe(true);

    let other = 0;
    await expect(runQuietRetries(async () => {
      other += 1;
      throw Object.assign(new Error("no"), { status: 401 });
    }, clock)).rejects.toMatchObject({ status: 401 });
    expect(other).toBe(1);
  });

  test("returns as soon as a retry succeeds", async () => {
    let now = 0;
    const clock = {
      now: () => now,
      sleep: async (ms: number) => {
        now += ms;
      },
    };
    let calls = 0;
    const value = await runQuietRetries(async () => {
      calls += 1;
      if (calls === 1) throw Object.assign(new Error("down"), { status: 503 });
      return "ok";
    }, clock);
    expect(value).toBe("ok");
    expect(calls).toBe(2);
    expect(now).toBeLessThan(QUIET_UNAVAILABLE_MS);
  });

  test("the budget is about 30 seconds", () => {
    expect(nextQuietRetryMs(0, 0)).toBe(2_000);
    expect(nextQuietRetryMs(0, QUIET_UNAVAILABLE_MS - 500)).toBe(500);
    expect(nextQuietRetryMs(0, QUIET_UNAVAILABLE_MS)).toBeNull();
  });
});


test("a lifecycle close is distinct from removed access and general Business restrictions", () => {
  expect(classifyFailure({ status: 403, code: "business_closed" })).toBe("business_closed");
  expect(classifyFailure({ status: 403, code: "business_grant_not_live" })).toBe("removed");
  expect(classifyFailure({ status: 403 })).toBe("closed");
});


test("lifecycle errors show only an actual safe server request reference", () => {
  expect(serverRequestReference({ requestId: "4ea79978-ce17-4853-b232-b2a72f4c9ce7" })).toBe("4ea79978-ce17-4853-b232-b2a72f4c9ce7");
  expect(serverRequestReference({ digest: "abc123" })).toBeNull();
  expect(serverRequestReference(new Error("offline"))).toBeNull();
  expect(serverRequestReference({ requestId: "unsafe server text" })).toBeNull();
});
