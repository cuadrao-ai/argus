import { describe, expect, test } from "bun:test";

import {
  EMAIL_OTP_TYPES,
  EmailOtpRejectedError,
  EmailOtpError,
  resendSignupEmail,
  hasConfirmedEmailSession,
  verifyEmailOtp,
  verifyWithSupabase,
  type EmailOtpKind,
} from "../lib/email-otp";

const email = "person@example.com";

describe("email confirmation codes", () => {
  test("forwards every email OTP type to verifyOtp with a normalized code", async () => {
    const calls: Array<{ email: string; token: string; type: EmailOtpKind }> = [];

    for (const type of EMAIL_OTP_TYPES) {
      await verifyEmailOtp(
        { email: `  ${email}  `, token: "123 456", type },
        async (input) => {
          calls.push(input);
          return { error: null };
        },
      );
    }

    expect(calls).toEqual(
      EMAIL_OTP_TYPES.map((type) => ({ email, token: "123456", type })),
    );
  });

  test("rejects a code that is not 6 to 10 digits before calling verifyOtp", async () => {
    const rejected = ["12345", "12345678901", "12ab56", "123-456", ""];

    for (const token of rejected) {
      let called = false;
      await expect(
        verifyEmailOtp({ email, token, type: "signup" }, async () => {
          called = true;
          return { error: null };
        }),
      ).rejects.toMatchObject({ code: "otp_rejected" });
      expect(called).toBe(false);
    }
  });

  test("hides rejected provider failures behind otp_rejected", async () => {
    await expect(
      verifyEmailOtp({ email, token: "123456", type: "magiclink" }, async () => ({
        error: { message: "Token has expired or is invalid", status: 403 },
      })),
    ).rejects.toBeInstanceOf(EmailOtpRejectedError);

    await expect(
      verifyEmailOtp({ email, token: "123456", type: "recovery" }, async () => {
        throw new Error("network down");
      }),
    ).rejects.toMatchObject({ code: "otp_transient", message: "otp_transient" });
  });
});


describe("confirmation service outcomes", () => {
  test.each([
    [{ message: "private details", code: "otp_expired", status: 403 }, "otp_expired"],
    [{ message: "private details", code: "over_request_rate_limit", status: 429 }, "too_many_requests"],
    [{ message: "private details", status: 503 }, "otp_transient"],
    [{ message: "private details", status: 400 }, "otp_rejected"],
  ])("maps service error %j to %s", async (error, code) => {
    await expect(verifyEmailOtp({ email, token: "01234567", type: "signup" }, async () => ({ error })))
      .rejects.toMatchObject({ code, message: code });
  });

  test("resend normalizes email and succeeds only after acceptance", async () => {
    const calls: unknown[] = [];
    await resendSignupEmail({ email: `  ${email}  ` }, async (input) => {
      calls.push(input);
      return { error: null };
    });
    expect(calls).toEqual([{ email, type: "signup" }]);
  });

  test("resend preserves a supplied retry delay and hides raw errors", async () => {
    await expect(resendSignupEmail({ email }, async () => ({
      error: { message: "sensitive", status: 429, retryAfterSeconds: 73 },
    }))).rejects.toMatchObject({ code: "too_many_requests", retryAfterSeconds: 73 });
    await expect(resendSignupEmail({ email }, async () => { throw new TypeError("offline"); }))
      .rejects.toBeInstanceOf(EmailOtpError);
  });
});


test("real resend transport includes fresh browser check, reads Retry-After and never sends credentials", async () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const originalKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  process.env.NEXT_PUBLIC_SUPABASE_URL = "http://127.0.0.1:4390";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "synthetic";
  let requests = 0;
  globalThis.fetch = Object.assign(async (input: string | URL | Request, init?: RequestInit) => {
    requests++;
    expect(String(input)).toBe("http://127.0.0.1:4390/auth/v1/resend");
    expect(init?.credentials).toBe("omit");
    expect(JSON.parse(String(init?.body))).toEqual({ email, type: "signup", gotrue_meta_security: { captcha_token: "argus-local-browser-qa" } });
    return Response.json({ code: "over_email_send_rate_limit", message: "private" }, { status: 429, headers: { "Retry-After": "321" } });
  }, { preconnect: originalFetch.preconnect });
  try {
    await expect(resendSignupEmail({ email })).rejects.toMatchObject({ code: "too_many_requests", retryAfterSeconds: 321 });
    expect(requests).toBe(1);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_URL; else process.env.NEXT_PUBLIC_SUPABASE_URL = originalUrl;
    if (originalKey === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY; else process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = originalKey;
  }
});


test.each([
  ["person@example.com", "2026-10-22T00:00:00Z", true],
  ["PERSON@example.com", "2026-10-22T00:00:00Z", true],
  ["other@example.com", "2026-10-22T00:00:00Z", false],
  ["person@example.com", undefined, false],
])("confirmed-session reconciliation checks fresh email and confirmation", async (address, confirmedAt, accepted) => {
  expect(await hasConfirmedEmailSession(email, {
    getSession: async () => ({ data: { session: {} }, error: null }),
    getUser: async () => ({ data: { user: { email: address, email_confirmed_at: confirmedAt } }, error: null }),
  })).toBe(accepted);
});

test("missing, failed or unavailable sessions never reconcile", async () => {
  for (const session of [null, {}]) {
    expect(await hasConfirmedEmailSession(email, {
      getSession: async () => ({ data: { session }, error: null }),
      getUser: async () => ({ data: { user: null }, error: new Error("unavailable") }),
    })).toBe(false);
  }
  expect(await hasConfirmedEmailSession(email, {
    getSession: async () => { throw new Error("unavailable"); },
    getUser: async () => { throw new Error("must not run"); },
  })).toBe(false);
});

test.each(EMAIL_OTP_TYPES)("confirmed signup session does not complete rejected %s verification", async (type) => {
  let identityReads = 0;
  const result = await verifyWithSupabase({ email, token: "01234567", type }, {
    verifyOtp: async () => ({ error: { message: "private rejection", code: "otp_expired", status: 403 } }),
    getSession: async () => ({ data: { session: {} }, error: null }),
    getUser: async () => {
      identityReads++;
      return { data: { user: { email, email_confirmed_at: "2026-10-22T00:00:00Z" } }, error: null };
    },
  });
  expect(result.error).toEqual(type === "signup" ? null : { message: "private rejection", code: "otp_expired", status: 403 });
  expect(identityReads).toBe(type === "signup" ? 1 : 0);
});
