import assert from "node:assert/strict";
import { mock } from "bun:test";

const calls: Array<{ email: string; token: string; type: string }> = [];

mock.module("@/lib/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: {
      verifyOtp: async (params: { email: string; token: string; type: string }) => {
        calls.push(params);
        return { data: { user: { id: "user-1" }, session: {} }, error: null };
      },
    },
  }),
}));

const { EMAIL_OTP_TYPES, verifyEmailOtp } = await import("@/lib/email-otp");

for (const type of EMAIL_OTP_TYPES) {
  await verifyEmailOtp({ email: "person@example.com", token: "654 321", type });
}

assert.deepEqual(
  calls,
  EMAIL_OTP_TYPES.map((type) => ({
    email: "person@example.com",
    token: "654321",
    type,
  })),
);

await assert.rejects(
  () => verifyEmailOtp({ email: "person@example.com", token: "nope", type: "signup" }),
  (error: unknown) => {
    assert.equal((error as { code?: string }).code, "otp_rejected");
    return true;
  },
);
assert.equal(calls.length, EMAIL_OTP_TYPES.length);

process.exit(0);
