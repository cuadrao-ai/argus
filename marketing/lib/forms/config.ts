import { parseMailbox } from "./validation.ts";

export type FormsConfig = {
  resendApiKey: string | null;
  resendApiUrl: string;
  inquiryFrom: string | null;
  inquiryTo: string | null;
  supabaseUrl: string | null;
  supabaseServiceKey: string | null;
  trustedClientIpHeader: string | null;
};

function value(raw: string | undefined): string | null {
  const trimmed = raw?.trim();
  return trimmed ? trimmed : null;
}

export function readFormsConfig(env: Record<string, string | undefined>): FormsConfig {
  return {
    resendApiKey: value(env.RESEND_API_KEY),
    resendApiUrl: value(env.RESEND_API_URL) ?? "https://api.resend.com",
    inquiryFrom: value(env.CUADRAO_INQUIRY_FROM),
    inquiryTo: parseMailbox(env.CUADRAO_INQUIRY_TO),
    supabaseUrl: value(env.SUPABASE_URL),
    supabaseServiceKey: value(env.SUPABASE_SERVICE_ROLE_KEY),
    trustedClientIpHeader: value(env.CUADRAO_TRUSTED_CLIENT_IP_HEADER),
  };
}

// The consent text the visitor saw is versioned by this string. Change it when
// the signup or privacy copy changes meaning, so a stored row says what it agreed to.
export const SIGNUP_CONSENT_VERSION = "early-access-2026-10";

export const PROVIDER_TIMEOUT_MS = 10_000;
