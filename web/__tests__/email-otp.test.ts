import { describe, expect, test } from "bun:test";

import {
  EMAIL_OTP_TYPES,
  EmailOtpRejectedError,
  verifyEmailOtp,
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

  test("hides provider failures behind otp_rejected", async () => {
    await expect(
      verifyEmailOtp({ email, token: "123456", type: "magiclink" }, async () => ({
        error: { message: "Token has expired or is invalid" },
      })),
    ).rejects.toBeInstanceOf(EmailOtpRejectedError);

    await expect(
      verifyEmailOtp({ email, token: "123456", type: "recovery" }, async () => {
        throw new Error("network down");
      }),
    ).rejects.toMatchObject({ code: "otp_rejected", message: "otp_rejected" });
  });
});
