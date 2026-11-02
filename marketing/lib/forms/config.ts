import { parseMailbox } from "./validation.ts";

export type FormsConfig = {
  resendApiKey: string | null;
  resendApiUrl: string;
  inquiryFrom: string | null;
  inquiryTo: string | null;
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
    trustedClientIpHeader: value(env.CUADRAO_TRUSTED_CLIENT_IP_HEADER),
  };
}

export const PROVIDER_TIMEOUT_MS = 10_000;
