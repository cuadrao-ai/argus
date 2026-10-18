import { getSupabaseClient } from "./supabase-client";

export const EMAIL_OTP_TYPES = [
  "signup",
  "invite",
  "magiclink",
  "recovery",
  "email_change",
  "email",
] as const;

export type EmailOtpKind = (typeof EMAIL_OTP_TYPES)[number];

const OTP_PATTERN = /^[0-9]{6,10}$/;

export class EmailOtpRejectedError extends Error {
  readonly code = "otp_rejected";

  constructor() {
    super("otp_rejected");
    this.name = "EmailOtpRejectedError";
  }
}

export function normalizeEmailOtp(value: string): string | null {
  const token = value.replace(/\s+/g, "");
  return OTP_PATTERN.test(token) ? token : null;
}

type EmailOtpVerifyInput = {
  email: string;
  token: string;
  type: EmailOtpKind;
};

type EmailOtpVerifier = (
  input: EmailOtpVerifyInput,
) => Promise<{ error: { message: string } | null }>;

function isEmailOtpKind(value: string): value is EmailOtpKind {
  return (EMAIL_OTP_TYPES as readonly string[]).includes(value);
}

async function verifyWithSupabase(
  input: EmailOtpVerifyInput,
): Promise<{ error: { message: string } | null }> {
  const client = getSupabaseClient();
  if (!client) throw new EmailOtpRejectedError();
  const { error } = await client.auth.verifyOtp(input);
  return { error };
}

export async function verifyEmailOtp(
  input: EmailOtpVerifyInput,
  verify: EmailOtpVerifier = verifyWithSupabase,
): Promise<void> {
  const token = normalizeEmailOtp(input.token);
  const email = input.email.trim();
  if (!token || email.length === 0 || !isEmailOtpKind(input.type)) {
    throw new EmailOtpRejectedError();
  }
  let result: { error: { message: string } | null };
  try {
    result = await verify({ email, token, type: input.type });
  } catch (error) {
    if (error instanceof EmailOtpRejectedError) throw error;
    throw new EmailOtpRejectedError();
  }
  if (result.error) throw new EmailOtpRejectedError();
}
