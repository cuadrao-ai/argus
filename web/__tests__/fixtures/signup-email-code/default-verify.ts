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
  await verifyEmailOtp({ email: "person@example.com", token: "00654321", type });
}

assert.deepEqual(
  calls,
  EMAIL_OTP_TYPES.map((type) => ({
    email: "person@example.com",
    token: "00654321",
    type,
  })),
);

for (const token of ["0065 4321", "00654321 ", "00654321\n"]) {
  await verifyEmailOtp({ email: "person@example.com", token, type: "signup" });
  assert.deepEqual(calls.at(-1), { email: "person@example.com", token: "00654321", type: "signup" });
}

for (const token of ["nope", "654 321"]) {
  await assert.rejects(
    () => verifyEmailOtp({ email: "person@example.com", token, type: "signup" }),
    (error: unknown) => {
      assert.equal((error as { code?: string }).code, "otp_rejected");
      return true;
    },
  );
}
assert.equal(calls.length, EMAIL_OTP_TYPES.length + 3);

process.exit(0);
