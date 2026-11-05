import { getSupabaseClient } from "./supabase-client";
import { acquirePasswordAuthCaptchaToken } from "./guest-captcha";
import { parseRetryAfterDelaySeconds } from "./retry-after";

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

export class EmailOtpError extends Error {
  constructor(
    readonly code: "otp_rejected" | "otp_expired" | "otp_transient" | "too_many_requests" | "captcha_unavailable",
    readonly retryAfterSeconds?: number,
  ) {
    super(code);
    this.name = "EmailOtpError";
  }
}

export class EmailOtpRejectedError extends EmailOtpError {
  constructor() {
    super("otp_rejected");
    this.name = "EmailOtpRejectedError";
  }
}

type ServiceError = {
  message: string;
  code?: string;
  status?: number;
  retryAfterSeconds?: number;
};

function safeError(error: unknown): EmailOtpError {
  if (error instanceof EmailOtpError) return error;
  if (typeof error !== "object" || error === null) return new EmailOtpError("otp_transient");
  const code = "code" in error ? error.code : undefined;
  const status = "status" in error && typeof error.status === "number" ? error.status : undefined;
  if (code === "captcha_unavailable" || code === "captcha_failed") return new EmailOtpError("captcha_unavailable");
  if (status === 429 || code === "over_email_send_rate_limit" || code === "over_request_rate_limit") {
    const delay = "retryAfterSeconds" in error ? error.retryAfterSeconds : undefined;
    return new EmailOtpError("too_many_requests", typeof delay === "number" && Number.isFinite(delay) && delay >= 0 ? delay : undefined);
  }
  if (code === "otp_expired") return new EmailOtpError("otp_expired");
  if (status && status >= 400 && status < 500) return new EmailOtpRejectedError();
  return new EmailOtpError("otp_transient");
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
) => Promise<{ error: ServiceError | null }>;

function isEmailOtpKind(value: string): value is EmailOtpKind {
  return (EMAIL_OTP_TYPES as readonly string[]).includes(value);
}

type EmailSessionReader = {
  getSession: () => Promise<{ data: { session: unknown }; error: unknown }>;
  getUser: () => Promise<{ data: { user: { email?: string; email_confirmed_at?: string } | null }; error: unknown }>;
};
type EmailOtpAuth = EmailSessionReader & { verifyOtp: EmailOtpVerifier };

export async function hasConfirmedEmailSession(email: string, auth: EmailSessionReader): Promise<boolean> {
  try {
    const session = await auth.getSession();
    if (session.error || !session.data.session) return false;
    const { data, error } = await auth.getUser();
    return !error && Boolean(data.user?.email_confirmed_at)
      && data.user?.email?.toLowerCase() === email.trim().toLowerCase();
  } catch {
    return false;
  }
}

export async function verifyWithSupabase(
  input: EmailOtpVerifyInput,
  suppliedAuth?: EmailOtpAuth,
): Promise<{ error: ServiceError | null }> {
  const auth = suppliedAuth ?? getSupabaseClient()?.auth;
  if (!auth) throw new EmailOtpError("otp_transient");
  const { error } = await auth.verifyOtp(input);
  if (input.type === "signup" && error && ["otp_rejected", "otp_expired"].includes(safeError(error).code)
    && await hasConfirmedEmailSession(input.email, auth)) return { error: null };
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
  let result: { error: ServiceError | null };
  try {
    result = await verify({ email, token, type: input.type });
  } catch (error) {
    throw safeError(error);
  }
  if (result.error) throw safeError(result.error);
}

export type EmailResendAcceptance = { retryAfterSeconds?: number };
type SignupResender = (input: { email: string; type: "signup" }) => Promise<EmailResendAcceptance & { error: ServiceError | null }>;

async function sendSignupConfirmation(input: { email: string; type: "signup" }): Promise<EmailResendAcceptance & { error: ServiceError | null }> {
  const origin = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!origin || !key) throw new EmailOtpError("otp_transient");
  const captchaToken = await acquirePasswordAuthCaptchaToken();
  const response = await fetch(`${origin.replace(/\/$/, "")}/auth/v1/resend`, {
    method: "POST",
    headers: { apikey: key, "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, gotrue_meta_security: { captcha_token: captchaToken } }),
    credentials: "omit",
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  const parsedDelay = parseRetryAfterDelaySeconds(response.headers.get("Retry-After"));
  const retryAfterSeconds = parsedDelay !== null && parsedDelay >= 0 ? parsedDelay : undefined;
  if (response.ok) return { error: null, retryAfterSeconds };
  const body: unknown = await response.json().catch(() => null);
  const code = body && typeof body === "object" && "code" in body && typeof body.code === "string" ? body.code : undefined;
  return { error: { message: "confirmation_request_failed", status: response.status, code, retryAfterSeconds } };
}

export async function resendSignupEmail(
  input: { email: string },
  send: SignupResender = sendSignupConfirmation,
): Promise<EmailResendAcceptance> {
  const email = input.email.trim();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new EmailOtpRejectedError();
  try {
    const result = await send({ email, type: "signup" });
    if (result.error) throw safeError(result.error);
    return { retryAfterSeconds: result.retryAfterSeconds };
  } catch (error) {
    throw safeError(error);
  }
}
